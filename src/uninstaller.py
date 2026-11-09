"""Disinstallazione completa di DriverCore: dati, attività pianificata, registro, notifiche ed eseguibile.

Resta sul PC solo ciò che non appartiene a DriverCore: i driver installati (sono del sistema) e i punti di
ripristino di Windows (servono a tornare indietro). Nella cartella dei dati si cancella solo ciò che DriverCore
crea, mai altro: se dentro c'è dell'altro (es. il codice sorgente) la cartella resta.

I file si cancellano dopo la chiusura del programma (log ed eseguibile sono in uso finché gira): lo fa uno
script PowerShell nascosto che aspetta l'uscita di DriverCore, come per l'aggiornamento automatico.
"""
import os
import subprocess
import sys
from pathlib import Path

from auto_scan import AUMID, PROTOCOL, TASK_NAME, TASK_PATH
from config import BASE_DIR, FROZEN
from driver_installer import disk_size
from i18n import tr

NO_WIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Tutto ciò che DriverCore crea nella cartella dei dati (config.py)
DATA_NAMES = ("backups", "downloads", "logs", "package_verdicts.json", "ignored_updates.json",
              "driver_history.json", "settings.json", "last_auto_scan.json", ".focus_request")

# Chiavi del registro (HKCU) create da DriverCore o da Windows per le sue notifiche
REG_TREES = (
    rf"Software\Classes\AppUserModelId\{AUMID}",
    rf"Software\Classes\{PROTOCOL}",
    rf"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings\{AUMID}",
)
# Valori che Windows registra per ogni eseguibile avviato (nome del valore = percorso dell'exe)
REG_EXE_VALUES = (
    r"Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\MuiCache",
    r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Compatibility Assistant\Store",
    r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers",
)


def data_paths(base: Path = BASE_DIR) -> list[Path]:
    return [base / n for n in DATA_NAMES if (base / n).exists()]


def size_of(paths) -> int:
    """Spazio davvero occupato: i file collegati tra backup (hard link) contano una volta, al netto della compressione."""
    total = 0
    seen: set[tuple[int, int]] = set()

    def add(f: Path) -> None:
        nonlocal total
        try:
            st = f.stat()
            key = (st.st_dev, st.st_ino)
            if key in seen:
                return
            seen.add(key)
            total += disk_size(f)
        except OSError:
            pass

    for p in paths:
        if p.is_file():
            add(p)
            continue
        for root, _dirs, files in os.walk(p):
            for f in files:
                add(Path(root) / f)
    return total


def _delete_tree(root, path: str) -> bool:
    import winreg
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS) as k:
            while True:
                try:
                    sub = winreg.EnumKey(k, 0)
                except OSError:
                    break
                _delete_tree(root, f"{path}\\{sub}")
        winreg.DeleteKey(root, path)
        return True
    except FileNotFoundError:
        return False


def remove_registry(trees=REG_TREES, exe_value_keys=REG_EXE_VALUES, exe: str | None = None) -> list[str]:
    """Cancella le chiavi di DriverCore e i valori che Windows associa al suo eseguibile. Ritorna gli errori."""
    import winreg
    errors = []
    for path in trees:
        try:
            _delete_tree(winreg.HKEY_CURRENT_USER, path)
        except OSError as e:
            errors.append(f"HKCU\\{path}: {e}")
    if exe:
        needle = exe.lower()
        for path in exe_value_keys:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_ALL_ACCESS) as k:
                    names, i = [], 0
                    while True:
                        try:
                            names.append(winreg.EnumValue(k, i)[0])
                        except OSError:
                            break
                        i += 1
                    for n in names:
                        if n.lower().startswith(needle):
                            winreg.DeleteValue(k, n)
            except FileNotFoundError:
                pass
            except OSError as e:
                errors.append(f"HKCU\\{path}: {e}")
    return errors


def _powershell(script: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                          capture_output=True, text=True, encoding="oem", errors="replace",
                          creationflags=NO_WIN, timeout=60, env={**os.environ, **env})


# Attività pianificata e la sua cartella \DriverCore\ (se vuota), poi lo storico delle notifiche
_TASK_PS = (
    "Get-ScheduledTask -TaskPath $env:DC_TPATH -ErrorAction SilentlyContinue "
    "| Unregister-ScheduledTask -Confirm:$false -ErrorAction Stop; "
    "$svc = New-Object -ComObject Schedule.Service; $svc.Connect(); "
    "$name = $env:DC_TPATH.Trim('\\'); "
    "try { $f = $svc.GetFolder('\\' + $name); "
    "  if ($f.GetTasks(1).Count -eq 0 -and $f.GetFolders(0).Count -eq 0) { $svc.GetFolder('\\').DeleteFolder($name, 0) } "
    "} catch { }; exit 0"  # cartella già assente; un errore vero di Unregister esce prima con codice 1
)
_NOTIFY_PS = (
    "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] "
    "| Out-Null; [Windows.UI.Notifications.ToastNotificationManager]::History.Clear($env:DC_AUMID)"
)


def remove_task(task_path: str = TASK_PATH) -> list[str]:
    res = _powershell(_TASK_PS, {"DC_TPATH": task_path, "DC_TNAME": TASK_NAME})
    if res.returncode != 0:
        err = (res.stderr or res.stdout or "").strip().splitlines()
        return [tr("attività pianificata: {error}", error=err[0] if err else res.returncode)]
    return []


def clear_notifications(aumid: str = AUMID) -> None:
    try:
        _powershell(_NOTIFY_PS, {"DC_AUMID": aumid})  # se non ce ne sono, nessun problema
    except Exception:
        pass


# Dopo la chiusura: dati, eseguibile, file Prefetch di Windows e, se vuota, la cartella dei dati
CLEANUP_PS = (
    "foreach ($p in ($env:DC_PIDS -split ',')) { if ($p) { Wait-Process -Id ([int]$p) -ErrorAction SilentlyContinue } }; "
    "$items = @($env:DC_ITEMS -split \"`n\" | Where-Object { $_ }); "
    "if ($env:DC_EXE) { $items += $env:DC_EXE }; "
    "for ($i = 0; $i -lt 40 -and $items.Count -gt 0; $i++) { "
    "  $left = @(); "
    "  foreach ($p in $items) { "
    "    if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue }; "
    "    if (Test-Path -LiteralPath $p) { $left += $p } }; "
    "  $items = $left; if ($items.Count -gt 0) { Start-Sleep -Milliseconds 500 } }; "
    "if ($env:DC_PREFETCH) { Remove-Item -Path (Join-Path (Join-Path $env:WINDIR 'Prefetch') $env:DC_PREFETCH) "
    "-Force -ErrorAction SilentlyContinue }; "
    # la cartella dei dati sparisce solo se è vuota (le cancellazioni appena fatte possono finire un attimo dopo)
    # (Windows elenca ancora per un attimo i file in cancellazione): fino a 3 s, poi la si lascia com'è
    "for ($i = 0; $i -lt 10 -and $env:DC_BASE -and (Test-Path -LiteralPath $env:DC_BASE); $i++) { "
    "  if (-not (Get-ChildItem -LiteralPath $env:DC_BASE -Force | Select-Object -First 1)) { "
    "    Remove-Item -LiteralPath $env:DC_BASE -Force -ErrorAction SilentlyContinue }; "
    "  if (Test-Path -LiteralPath $env:DC_BASE) { Start-Sleep -Milliseconds 300 } }"
)


def schedule_cleanup(items, exe: str | None, base: Path, pids=None) -> subprocess.Popen:
    """Avvia lo script che cancella i file appena DriverCore si chiude. Ritorna subito."""
    pids = pids if pids is not None else [os.getpid(), os.getppid()]
    prefetch = f"{Path(exe).name.upper()}-*.pf" if exe else ""
    from updater import launch_after_exit
    return launch_after_exit(CLEANUP_PS, {"DC_PIDS": ",".join(map(str, pids)), "DC_ITEMS": "\n".join(map(str, items)),
                                          "DC_EXE": exe or "", "DC_BASE": str(base), "DC_PREFETCH": prefetch})


def uninstall() -> list[str]:
    """Tutto tranne i file (vedi schedule_cleanup). Ritorna gli errori non bloccanti."""
    exe = sys.executable if FROZEN else None
    errors = remove_task()
    clear_notifications()
    errors += remove_registry(exe=exe)
    schedule_cleanup(data_paths(), exe, BASE_DIR)
    return errors
