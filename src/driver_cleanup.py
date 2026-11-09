"""Pulizia dei pacchetti driver obsoleti dal DriverStore di Windows.

Regole di sicurezza:
- si considerano solo pacchetti di terze parti (non Inbox, non BootCritical);
- per ogni "famiglia" di driver (stesso INF originale + provider + classe) si tiene il pacchetto più recente;
- non si tocca mai un pacchetto attualmente in uso da una periferica;
- l'eliminazione usa `pnputil /delete-driver` SENZA /force: se Windows lo ritiene in uso, rifiuta.
"""
import json
import re
import subprocess
from pathlib import PureWindowsPath

from packaging import version
from rich.console import Console

from driver_history import protected_infs
from i18n import tr

console = Console()
NO_WIN = subprocess.CREATE_NO_WINDOW

_PS_LIST = (
    "[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
    "Get-WindowsDriver -Online -All | Select-Object Driver, OriginalFileName, ProviderName, ClassName, "
    "@{n='Version';e={\"$($_.Version)\"}}, @{n='Date';e={$_.Date.ToString('yyyy-MM-dd')}}, "
    "BootCritical, Inbox | ConvertTo-Json -Compress"
)


def _version_key(ver: str):
    """Chiave ordinabile per le versioni driver (es. 31.0.101.5186), robusta a formati strani."""
    try:
        return (1, version.parse(ver))
    except Exception:
        nums = tuple(int(n) for n in re.findall(r"\d+", ver or ""))
        return (0, version.parse(".".join(map(str, nums)) or "0"))


def list_driver_packages() -> list[dict] | None:
    """Elenca i pacchetti del DriverStore tramite PowerShell (JSON, indipendente dalla lingua di Windows)."""
    try:
        res = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", _PS_LIST],
            capture_output=True, encoding="utf-8", errors="replace",
            creationflags=NO_WIN, timeout=180
        )
    except Exception as e:
        console.print(f"[bold red]✖ {tr('Impossibile leggere il DriverStore: {error}', error=e)}[/bold red]")
        return None

    out = (res.stdout or "").strip()
    if res.returncode != 0 or not out:
        err = (res.stderr or "").strip().splitlines()
        detail = err[0][:160] if err else tr("nessun output")
        console.print(f"[bold red]✖ {tr('Lettura DriverStore non riuscita: {error}', error=detail)}[/bold red]")
        return None
    try:
        data = json.loads(out)
    except json.JSONDecodeError as e:
        console.print(f"[bold red]✖ {tr('Risposta PowerShell non valida: {error}', error=e)}[/bold red]")
        return None
    return data if isinstance(data, list) else [data]


def select_obsolete(packages: list[dict], in_use_infs: set[str]) -> list[dict]:
    """Funzione pura: dato l'elenco dei pacchetti e gli INF in uso, ritorna i pacchetti eliminabili."""
    families: dict[tuple, list[dict]] = {}
    for p in packages:
        if p.get("Inbox") or p.get("BootCritical"):
            continue
        driver = (p.get("Driver") or "").lower()
        if not re.fullmatch(r"oem\d+\.inf", driver):
            continue
        original = PureWindowsPath(p.get("OriginalFileName") or "").name.lower()
        key = (original, (p.get("ProviderName") or "").lower(), (p.get("ClassName") or "").lower())
        families.setdefault(key, []).append(p)

    obsolete = []
    for members in families.values():
        if len(members) < 2:
            continue
        # Il più recente per (versione, data); a parità, il nome oemN più alto
        members.sort(
            key=lambda m: (_version_key(m.get("Version", "")), m.get("Date", ""), int(re.search(r"\d+", m["Driver"]).group())),
            reverse=True
        )
        newest = members[0]
        for old in members[1:]:
            if old["Driver"].lower() in in_use_infs:
                continue
            obsolete.append({
                "driver": old["Driver"],
                "provider": old.get("ProviderName") or "?",
                "class": old.get("ClassName") or "?",
                "version": old.get("Version") or "?",
                "date": old.get("Date") or "?",
                "kept_driver": newest["Driver"],
                "kept_version": newest.get("Version") or "?",
            })
    obsolete.sort(key=lambda o: (o["provider"].lower(), o["class"].lower(), o["driver"]))
    return obsolete


def find_obsolete_driver_packages(wmi_client) -> list[dict]:
    """Analizza il DriverStore e ritorna i pacchetti obsoleti (senza eliminare nulla)."""
    console.print(f"\n[bold cyan]{tr('Analisi del DriverStore: ricerca pacchetti driver obsoleti...')}[/bold cyan]")
    packages = list_driver_packages()
    if packages is None:
        return []

    in_use = set()
    for drv in wmi_client.Win32_PnPSignedDriver():
        inf = (getattr(drv, "InfName", None) or "").lower()
        if inf:
            in_use.add(inf)

    # I driver precedenti degli aggiornamenti ancora annullabili restano nel DriverStore
    in_use |= protected_infs()
    obsolete = select_obsolete(packages, in_use)
    console.print(tr("Pacchetti totali nel DriverStore: {total}  |  obsoleti eliminabili: {obsolete}",
                     total=f"[bold yellow]{len(packages)}[/bold yellow]", obsolete=f"[bold yellow]{len(obsolete)}[/bold yellow]"))
    if not obsolete:
        console.print(f"[bold green]✔ {tr('Nessun pacchetto driver obsoleto da rimuovere.')}[/bold green]")
    return obsolete


def remove_obsolete_driver_packages(obsolete: list[dict]) -> tuple[int, int]:
    """Elimina i pacchetti indicati (senza /force). Ritorna (eliminati, saltati/falliti)."""
    removed = skipped = 0
    for item in obsolete:
        res = subprocess.run(
            ["pnputil", "/delete-driver", item["driver"]],
            capture_output=True, text=True, encoding="oem", errors="replace", creationflags=NO_WIN
        )
        label = f"{item['driver']} ({item['provider']} {item['class']} {item['version']})"
        if res.returncode == 0:
            removed += 1
            console.print(" -> " + tr("Rimosso {label}", label=label))
        else:
            skipped += 1
            console.print("[dim] -> " + tr("Saltato {label}: Windows lo considera in uso o protetto (codice {code}).",
                                         label=label, code=res.returncode) + "[/dim]")

    if removed:
        console.print("[bold green]✔ " + tr("DriverStore ripulito: {removed} pacchetti rimossi, {skipped} saltati.",
                                            removed=removed, skipped=skipped) + "[/bold green]")
    else:
        console.print("[yellow]! " + tr("Nessun pacchetto rimosso ({skipped} saltati).", skipped=skipped) + "[/yellow]")
    return removed, skipped


def dism_component_cleanup() -> bool:
    """Pulizia dei componenti di sistema (WinSxS) con DISM /StartComponentCleanup.

    NB: non tocca i pacchetti driver: per quelli c'è remove_obsolete_driver_packages().
    """
    console.print(f"\n[bold cyan]{tr('Avvio pulizia componenti di sistema (DISM StartComponentCleanup)...')}[/bold cyan]")
    dism = subprocess.run(
        ["Dism.exe", "/Online", "/Cleanup-Image", "/StartComponentCleanup"],
        capture_output=True, text=True, encoding="oem", errors="replace", check=False, creationflags=NO_WIN
    )
    code = dism.returncode & 0xFFFFFFFF  # Windows restituisce gli HRESULT come interi positivi enormi
    if code in (0, 3010):
        console.print(f"[bold green]✔ {tr('Pulizia componenti di sistema completata.')}[/bold green]")
        if code == 3010:
            console.print(f"[bold yellow]! {tr('Riavvio del sistema consigliato.')}[/bold yellow]")
        return True

    if code == 0x800F0806:
        console.print("[bold yellow]! " + tr("Windows ha un'operazione di aggiornamento in sospeso (0x800F0806): "
                                             "riavvia il PC e ripeti la pulizia.") + "[/bold yellow]")
    else:
        last = [ln.strip() for ln in (dism.stdout or "").splitlines() if ln.strip()]
        detail = f" - {last[-1][:140]}" if last else ""
        console.print("[bold red]✖ " + tr("DISM ha restituito l'errore {code}", code=f"0x{code:08X}") + f"{detail}[/bold red]")
        console.print("[dim]" + tr("Dettagli in {path}", path=r"C:\Windows\Logs\DISM\dism.log") + "[/dim]")
    return False
