import json
import os
import re
import shutil
import subprocess
import winreg
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
import win32com.client
from rich.console import Console

from config import BACKUP_KEEP, BACKUP_ROOT, DOWNLOAD_DIR, NVIDIA_SIGNER_ORG, SEVEN_ZIP
from driver_history import backups_needed_for_undo, record_install, snapshot_infs
from i18n import tr

console = Console()
NO_WIN = subprocess.CREATE_NO_WINDOW

BACKUP_NAME = re.compile(r"backup_\d{8}_\d{6}")
MANIFEST_NAME = "_drivercore_manifest.json"


def driverstore_fingerprint(inf_dir: Path | None = None) -> list[str]:
    """Impronta dei driver di terze parti installati (oemN.inf con dimensione e data).

    Cambia ogni volta che un driver viene aggiunto, aggiornato o rimosso: serve a capire
    se l'ultimo backup rappresenta ancora lo stato attuale.
    """
    if inf_dir is None:
        inf_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "INF"
    items = []
    for p in inf_dir.glob("oem*.inf"):
        try:
            st = p.stat()
        except OSError:
            continue
        items.append(f"{p.name.lower()}|{st.st_size}|{int(st.st_mtime)}")
    return sorted(items)


def list_backups(root: Path = BACKUP_ROOT) -> list[Path]:
    """Cartelle di backup create da DriverCore, dalla più vecchia alla più recente."""
    if not root.exists():
        return []
    return sorted((d for d in root.iterdir() if d.is_dir() and BACKUP_NAME.fullmatch(d.name)), key=lambda d: d.name)


def backups_to_prune(backups: list[Path], keep: int) -> list[Path]:
    """Funzione pura: i backup più vecchi oltre i `keep` più recenti."""
    return backups[:-keep] if keep > 0 and len(backups) > keep else []


def _read_manifest(backup_dir: Path) -> list[str] | None:
    try:
        return json.loads((backup_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def prune_old_backups(keep: int = BACKUP_KEEP) -> None:
    backups = list_backups()
    prunable = backups_to_prune(backups, keep)
    # Un backup con l'unica copia del driver precedente di un aggiornamento annullabile resta
    needed = backups_needed_for_undo(backups) if prunable else set()  # i più recenti hanno la precedenza
    for old in prunable:
        if old in needed:
            console.print("[dim] -> " + tr("Backup {name} conservato: serve per annullare un aggiornamento.", name=old.name) + "[/dim]")
            continue
        size = sum(f.stat().st_size for f in old.rglob("*") if f.is_file())
        shutil.rmtree(old, ignore_errors=True)
        console.print("[dim] -> " + tr("Rimosso vecchio backup {name} ({value:.1f} GB).", name=old.name, value=size / (1024 ** 3)) + "[/dim]")


def backup_current_drivers() -> bool:
    """Esporta i driver attuali gestendo correttamente la codifica OEM italiana di Windows.

    Se nessun driver è cambiato dall'ultimo backup, quello resta valido e non se ne crea un altro.
    Dopo un backup riuscito si conservano solo gli ultimi BACKUP_KEEP.
    """
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    fingerprint = driverstore_fingerprint()
    existing = [d for d in list_backups() if any(d.iterdir())]

    if existing and fingerprint and _read_manifest(existing[-1]) == fingerprint:
        console.print("[bold green]✔ " + tr("Nessun driver cambiato dall'ultimo backup ({name}): resta valido.", name=existing[-1].name) + "[/bold green]")
        return True

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_dir = BACKUP_ROOT / f"backup_{timestamp}"
    target_dir.mkdir(parents=True, exist_ok=True)

    console.print("\n[bold cyan]" + tr("Avvio backup driver in:[/bold cyan] {target_dir}", target_dir=target_dir))
    try:
        proc = subprocess.Popen(
            ["pnputil", "/export-driver", "*", str(target_dir)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="oem",
            errors="replace",
            creationflags=NO_WIN
        )
        count = 0
        if proc.stdout:
            for line in proc.stdout:
                if ".inf" in line.lower():
                    count += 1
        proc.wait()

        # Il backup è valido solo se pnputil ha finito bene e ha esportato qualcosa
        if proc.returncode not in (0, 3010) or not any(target_dir.iterdir()):
            console.print("[bold red]✖ " + tr("Backup fallito (pnputil codice {returncode}, {count} riferimenti).", returncode=proc.returncode, count=count) + "[/bold red]")
            shutil.rmtree(target_dir, ignore_errors=True)
            return False

        (target_dir / MANIFEST_NAME).write_text(json.dumps(fingerprint), encoding="utf-8")
        console.print("[bold green]✔ " + tr("Backup completato con successo ({count} riferimenti elaborati).", count=count) + "[/bold green]")
        prune_old_backups()
        return True
    except Exception as e:
        console.print("[bold red]✖ " + tr("Errore durante il backup: {e}", e=e) + "[/bold red]")
        shutil.rmtree(target_dir, ignore_errors=True)
        return False


def subject_organization(subject: str) -> str | None:
    """Estrae il campo O= da un Subject X.500 (es. 'CN=..., O=NVIDIA Corporation, L=...')."""
    m = re.search(r'(?:^|,)\s*O=(?:"([^"]*)"|([^,]*))', subject or "")
    if not m:
        return None
    return (m.group(1) if m.group(1) is not None else m.group(2)).strip()


def verify_signature(path: Path, expected_org: str) -> bool:
    """Verifica la firma Authenticode del file e che l'organizzazione firmataria sia esattamente `expected_org`."""
    # Il percorso passa da una variabile d'ambiente: niente quoting/iniezione nel comando PowerShell
    ps = (
        "$s = Get-AuthenticodeSignature -LiteralPath $env:DRIVERCORE_SIG_PATH; "
        "if ($s.Status -ne 'Valid') { Write-Output ('STATUS:' + $s.Status); exit 2 }; "
        "Write-Output $s.SignerCertificate.Subject"
    )
    try:
        res = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, encoding="oem", errors="replace",
            creationflags=NO_WIN, timeout=60, env={**os.environ, "DRIVERCORE_SIG_PATH": str(path)}
        )
    except Exception as e:
        console.print("[bold red]✖ " + tr("Impossibile verificare la firma di {name}: {e}", name=path.name, e=e) + "[/bold red]")
        return False

    out = (res.stdout or "").strip()
    if res.returncode != 0:
        console.print("[bold red]✖ " + tr("Firma digitale non valida per {name} ({value}).", name=path.name, value=out or tr("nessun dettaglio")) + "[/bold red]")
        return False
    org = subject_organization(out)
    if not org or org.lower() != expected_org.lower():
        console.print("[bold red]✖ " + tr("Firmatario inatteso per {name}: {out}", name=path.name, out=out) + "[/bold red]")
        return False
    return True


def download_file(url: str) -> Path | None:
    """Scarica il pacchetto driver mostrando l'avanzamento. Riusa il file se già completo in cache."""
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = Path(urlparse(url).path).name or "driver_download.exe"
    dest_path = DOWNLOAD_DIR / filename
    part_path = dest_path.with_suffix(dest_path.suffix + ".part")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://www.nvidia.com/"
    }

    console.print("\n[bold cyan]" + tr("Download di:[/bold cyan] {filename}", filename=filename))
    try:
        with httpx.Client(follow_redirects=True, timeout=30.0, headers=headers) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                total = int(response.headers.get("Content-Length", 0))

                if dest_path.exists() and total > 0 and dest_path.stat().st_size == total:
                    console.print("[bold green]✔ " + tr("File già scaricato in cache: {dest_path}", dest_path=dest_path) + "[/bold green]")
                    return dest_path

                downloaded = 0
                last_pct = -1
                with open(part_path, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=65536):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = int((downloaded / total) * 100)
                            if pct % 10 == 0 and pct != last_pct:
                                last_pct = pct
                                console.print(" -> " + tr("Avanzamento download: {pct}% ({value} MB / {value2} MB)", pct=pct, value=downloaded // (1024*1024), value2=total // (1024*1024)))

        if total > 0 and downloaded != total:
            raise IOError(tr("download incompleto ({done} di {total} byte)", done=downloaded, total=total))

        part_path.replace(dest_path)
        console.print("[bold green]✔ " + tr("File salvato in:[/bold green] {dest_path}", dest_path=dest_path))
        return dest_path
    except Exception as e:
        part_path.unlink(missing_ok=True)
        console.print("[bold red]✖ " + tr("Errore durante il download: {e}", e=e) + "[/bold red]")
        return None


def install_nvidia_driver(exe_path: Path, clean_install: bool = False, slim_mode: bool = True,
                          gpu: dict | None = None) -> bool:
    """Installa il driver NVIDIA in modalità Slim (stile NVCleanstall) o Standard. Ritorna True se riuscito.

    gpu: i dati di nvidia_info(), per registrare l'installazione nella cronologia (e poterla annullare).
    """
    # Non eseguire mai un installer con firma mancante/non valida o di un altro firmatario
    if not verify_signature(exe_path, NVIDIA_SIGNER_ORG):
        console.print("[bold red]✖ " + tr("Installazione annullata: il pacchetto non risulta firmato da NVIDIA.") + "[/bold red]")
        return False

    target_exe = exe_path
    extract_dir = DOWNLOAD_DIR / "nvidia_slim_temp"

    if slim_mode:
        if not SEVEN_ZIP.exists():
            console.print("[yellow]! " + tr("7-Zip non trovato in C:\\Program Files\\7-Zip\\7z.exe. Passo alla modalità standard.") + "[/yellow]")
        else:
            if extract_dir.exists():
                shutil.rmtree(extract_dir, ignore_errors=True)
            extract_dir.mkdir(parents=True, exist_ok=True)

            console.print("\n[bold cyan]" + tr("Estrazione selettiva pacchetto NVIDIA (Solo Display.Driver, PhysX, HDAudio)...") + "[/bold cyan]")
            components = [
                "Display.Driver",
                "HDAudio",
                "PhysX",
                "NVI2",
                "EULA.txt",
                "ListDevices.txt",
                "setup.cfg",
                "setup.exe"
            ]
            cmd = [str(SEVEN_ZIP), "x", str(exe_path), f"-o{extract_dir}", "-y"] + components
            res7 = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, creationflags=NO_WIN)

            cfg_path = extract_dir / "setup.cfg"
            slim_setup = extract_dir / "setup.exe"
            if res7.returncode > 1:  # 7-Zip: 0 = ok, 1 = solo avvisi, >1 = errore
                console.print("[yellow]! " + tr("7-Zip ha restituito il codice {returncode}: estrazione non affidabile. Passo alla modalità standard.", returncode=res7.returncode) + "[/yellow]")
            elif not (cfg_path.exists() and slim_setup.exists()):
                console.print("[yellow]! " + tr("Estrazione SLIM incompleta (setup.cfg/setup.exe mancanti). Passo alla modalità standard.") + "[/yellow]")
            elif not verify_signature(slim_setup, NVIDIA_SIGNER_ORG):
                console.print("[yellow]! " + tr("setup.exe estratto non firmato da NVIDIA. Passo alla modalità standard.") + "[/yellow]")
            else:
                blocked_tokens = ("EulaHtmlFile", "FunctionalConsentFile", "PrivacyPolicyFile")
                lines = cfg_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                cleaned_lines = [line for line in lines if not any(tok in line for tok in blocked_tokens)]
                cfg_path.write_text("\n".join(cleaned_lines), encoding="utf-8")
                target_exe = slim_setup
                console.print("[bold green]✔ " + tr("Pacchetto alleggerito e telemetria rimossa da setup.cfg.") + "[/bold green]")

    args = [str(target_exe), "-passive", "-noreboot"]
    if clean_install:
        args.append("-clean")

    console.print("\n[bold cyan]" + tr("Avvio installazione NVIDIA ({value})...", value='SLIM' if target_exe != exe_path else 'STANDARD') + "[/bold cyan]")
    console.print("[dim]" + tr("Lo schermo potrebbe lampeggiare per alcuni secondi.") + "[/dim]")

    ok = False
    snap_before = snapshot_infs()
    try:
        proc = subprocess.run(args, check=False, creationflags=NO_WIN)
        if proc.returncode in (0, 3010):
            console.print("[bold green]✔ " + tr("Installazione NVIDIA completata con successo!") + "[/bold green]")
            if proc.returncode == 3010:
                console.print("[bold yellow]! " + tr("Riavvio del sistema consigliato.") + "[/bold yellow]")
            ok = True
            gpu = gpu or {}
            record_install("nvidia", gpu.get("name") or "GPU NVIDIA", gpu.get("device_id", ""),
                           gpu.get("local", ""), gpu.get("remote", ""), gpu.get("inf_name"), snap_before)
        else:
            console.print("[bold red]✖ " + tr("L'installer ha restituito il codice: {returncode}", returncode=proc.returncode) + "[/bold red]")
    except Exception as e:
        console.print("[bold red]✖ " + tr("Errore esecuzione installer: {e}", e=e) + "[/bold red]")
    finally:
        if extract_dir.exists():
            shutil.rmtree(extract_dir, ignore_errors=True)

    # Installer (~1 GB) non più necessario dopo un'installazione riuscita
    if ok and exe_path.resolve().parent == DOWNLOAD_DIR.resolve():
        try:
            exe_path.unlink()
            console.print("[dim] -> " + tr("Installer rimosso da {download_dir}.", download_dir=DOWNLOAD_DIR) + "[/dim]")
        except OSError:
            pass
    return ok


def install_windows_update_drivers(updates):
    """Scarica e installa i driver trovati nel catalogo Windows Update."""
    if not updates:
        return

    session = win32com.client.Dispatch("Microsoft.Update.Session")
    coll = win32com.client.Dispatch("Microsoft.Update.UpdateColl")
    for u in updates:
        coll.Add(u)

    console.print("\n[bold cyan]" + tr("Download di {count} driver dal catalogo Microsoft...", count=coll.Count) + "[/bold cyan]")
    downloader = session.CreateUpdateDownloader()
    downloader.Updates = coll
    downloader.Download()

    console.print("[bold cyan]" + tr("Installazione driver Windows Update in corso...") + "[/bold cyan]")
    installer = session.CreateUpdateInstaller()
    installer.Updates = coll
    res = installer.Install()

    # ResultCode WUA: 2 = Succeeded, 3 = SucceededWithErrors, 4 = Failed, 5 = Aborted
    if res.ResultCode == 2:
        console.print("[bold green]✔ " + tr("Installazione completata (Riavvio richiesto: {rebootrequired})", rebootrequired=res.RebootRequired) + "[/bold green]")
    else:
        console.print("[bold red]✖ " + tr("Installazione non riuscita o parziale (ResultCode: {resultcode}, Riavvio richiesto: {rebootrequired})", resultcode=res.ResultCode, rebootrequired=res.RebootRequired) + "[/bold red]")


def update_game_runtimes() -> bool:
    """Aggiorna librerie di sistema VC++ e .NET tramite winget. Ritorna True se nessun pacchetto è fallito."""
    packages = [
        "Microsoft.VCRedist.2015+.x64",
        "Microsoft.VCRedist.2015+.x86",
        "Microsoft.DotNet.DesktopRuntime.8",
        "Microsoft.DotNet.DesktopRuntime.10",
    ]
    # Codici winget che NON sono errori: nessun aggiornamento applicabile / già installato
    # (confrontati come interi senza segno: winget può restituirli anche come negativi)
    winget_ok = {
        0,
        0x8A15002B,  # aggiornamento non applicabile (già all'ultima versione)
        0x8A150061,  # pacchetto già installato
    }
    console.print("\n[bold cyan]" + tr("Verifica e aggiornamento Runtime di gioco (VC++ / .NET)...") + "[/bold cyan]")
    failed = []
    for pkg in packages:
        console.print(" -> " + tr("Controllo [yellow]{pkg}[/yellow]...", pkg=pkg))
        try:
            res = subprocess.run(
                ["winget", "upgrade", "--id", pkg, "--silent",
                 "--accept-package-agreements", "--accept-source-agreements"],
                check=False,
                creationflags=NO_WIN
            )
        except FileNotFoundError:
            console.print("[bold red]✖ " + tr("winget non trovato: installa 'App Installer' dal Microsoft Store.") + "[/bold red]")
            return False
        code = res.returncode & 0xFFFFFFFF
        if code == 0x8A150014:
            # Nessun pacchetto installato corrisponde all'ID: niente da aggiornare, non è un errore
            console.print("[dim] -> " + tr("{pkg} non è installato: salto.", pkg=pkg) + "[/dim]")
            continue
        if code not in winget_ok:
            failed.append((pkg, f"0x{code:08X}"))

    if failed:
        details = ", ".join(f"{p} (codice {c})" for p, c in failed)
        console.print("[bold red]✖ " + tr("Aggiornamento runtime non riuscito per: {details}", details=details) + "[/bold red]")
        return False
    console.print("[bold green]✔ " + tr("Controllo runtime terminato.") + "[/bold green]")
    return True


def create_system_restore_point(description: str = "DriverCore Pre-Update") -> bool:
    """Crea un Punto di Ripristino di Windows tramite PowerShell Checkpoint-Computer."""
    console.print("\n[bold cyan]" + tr("Creazione Punto di Ripristino di Sistema ({description})...", description=description) + "[/bold cyan]")
    safe_desc = description.replace("'", "''")
    cmd = [
        "powershell.exe", "-NoProfile", "-Command",
        f"Checkpoint-Computer -Description '{safe_desc}' -RestorePointType 'DEVICE_DRIVER_INSTALL' -ErrorAction Stop"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="oem", errors="replace", creationflags=NO_WIN)
    if res.returncode == 0:
        console.print("[bold green]✔ " + tr("Punto di ripristino di Windows creato con successo.") + "[/bold green]")
        return True

    reason = (res.stderr or res.stdout or "").strip().splitlines()
    reason_txt = reason[0][:160] if reason else tr("codice {code}", code=res.returncode)
    console.print("[yellow]! " + tr("Punto di ripristino non creato: {reason_txt}", reason_txt=reason_txt) + "[/yellow]")
    return False


def clean_gpu_shader_cache():
    """Svuota le cache DirectX e NVIDIA DXCache/GLCache per eliminare stuttering post-aggiornamento."""
    console.print("\n[bold cyan]" + tr("Pulizia Cache Shader GPU (NVIDIA DXCache, GLCache, DirectX D3DSCache)...") + "[/bold cyan]")
    local_app = Path(os.environ.get("LOCALAPPDATA", ""))
    target_dirs = [
        local_app / "NVIDIA" / "DXCache",
        local_app / "NVIDIA" / "GLCache",
        local_app / "D3DSCache",
        local_app / "Temp" / "NVIDIA Corporation" / "NV_Cache"
    ]
    freed_files = 0
    freed_bytes = 0
    for d in target_dirs:
        if d.exists():
            for item in d.rglob("*"):
                if item.is_file():
                    try:
                        sz = item.stat().st_size
                        item.unlink()
                        freed_files += 1
                        freed_bytes += sz
                    except (PermissionError, OSError):
                        # File in uso (es. dal compositore desktop di Windows)
                        pass
    mb_freed = freed_bytes / (1024 * 1024)
    console.print("[bold green]✔ " + tr("Cache Shader ripulita: {freed_files} file rimossi ({mb_freed:.1f} MB liberati).", freed_files=freed_files, mb_freed=mb_freed) + "[/bold green]")


def enable_gpu_msi_mode(wmi_client):
    """Verifica e attiva Message Signaled Interrupts (MSI Mode) nel registro PCI per la GPU NVIDIA."""
    console.print("\n[bold cyan]" + tr("Verifica e attivazione MSI Low-Latency Mode sulla GPU...") + "[/bold cyan]")
    gpus = [g for g in wmi_client.Win32_VideoController() if "NVIDIA" in (g.Name or "")]
    if not gpus:
        console.print("[yellow]! " + tr("Nessuna GPU NVIDIA trovata per l'ottimizzazione MSI.") + "[/yellow]")
        return

    for gpu in gpus:
        pnp_id = gpu.PNPDeviceID
        if not pnp_id:
            continue
        reg_path = f"SYSTEM\\CurrentControlSet\\Enum\\{pnp_id}\\Device Parameters\\Interrupt Management\\MessageSignaledInterruptProperties"
        key = None
        try:
            key = winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, reg_path, 0, winreg.KEY_READ | winreg.KEY_WRITE)
            try:
                cur_val, _ = winreg.QueryValueEx(key, "MSISupported")
            except FileNotFoundError:
                cur_val = 0

            if cur_val == 1:
                console.print("[bold green]✔ " + tr("{name}: MSI Low-Latency Mode è GIÀ ATTIVO (MSISupported = 1).", name=gpu.Name) + "[/bold green]")
            else:
                winreg.SetValueEx(key, "MSISupported", 0, winreg.REG_DWORD, 1)
                console.print("[bold green]✔ " + tr("{name}: MSI Mode ATTIVATO con successo! (valore precedente: {cur_val}; riavvia il PC per applicare).", name=gpu.Name, cur_val=cur_val) + "[/bold green]")
        except Exception as e:
            console.print("[red]✖ " + tr("Impossibile accedere alla chiave MSI di {name}: {e}", name=gpu.Name, e=e) + "[/red]")
        finally:
            if key is not None:
                winreg.CloseKey(key)


def restore_driver_backup_folder(folder_path: str) -> bool:
    """Reinstalla i driver .inf presenti in una cartella di backup selezionata.

    NB: Windows sceglie comunque il driver "migliore" tra quelli disponibili: se il driver
    più nuovo è ancora installato, potrebbe restare attivo. Per un vero rollback serve
    anche rimuovere il pacchetto nuovo (pnputil /delete-driver).
    """
    target = Path(folder_path)
    if not target.exists():
        console.print("[bold red]✖ " + tr("Cartella di backup non trovata: {target}", target=target) + "[/bold red]")
        return False
    console.print("\n[bold cyan]" + tr("Ripristino driver dalla cartella:[/bold cyan] {name}", name=target.name))
    res = subprocess.run(
        ["pnputil", "/add-driver", str(target / "*.inf"), "/subdirs", "/install"],
        capture_output=True, text=True, encoding="oem", errors="replace", creationflags=NO_WIN
    )
    if res.returncode in (0, 3010):
        console.print("[bold green]✔ " + tr("Reinstallazione completata da {name} (codice {returncode}).", name=target.name, returncode=res.returncode) + "[/bold green]")
        return True
    console.print("[bold red]✖ " + tr("Ripristino non riuscito da {name} (codice {returncode}).", name=target.name, returncode=res.returncode) + "[/bold red]")
    return False
