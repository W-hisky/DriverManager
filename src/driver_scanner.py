import win32com.client
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

import gpu_check
from gpu_check import wmi_to_nvidia_version  # noqa: F401  (usata anche dai test)
from i18n import tr

console = Console()
VENDOR_NAMES = {"nvidia": "NVIDIA", "amd": "AMD", "intel": "Intel"}


def _print_gpu(r: dict):
    if r["update"] is True:
        status = f"[bold red]{tr('AGGIORNAMENTO DISPONIBILE')}[/bold red]"
    elif r["update"] is False:
        status = f"[bold green]{tr('AGGIORNATO')}[/bold green]"
    else:
        status = f"[yellow]{tr('DA VERIFICARE')}[/yellow]"
    lines = [f"[bold]GPU:[/bold] {r['name']}", f"[bold]{tr('Installato:')}[/bold] {r['local']}"]
    if r["remote"]:
        lines.append(f"[bold]{tr('Ultima versione:')}[/bold] {r['remote']} ({r['date']})")
    lines.append(f"[bold]{tr('Stato:')}[/bold] {status}")
    if r["note"]:
        lines.append(f"[bold]{tr('Nota:')}[/bold] {r['note']}")
    if r["url"] or r["page"]:
        lines.append(f"[bold]Download:[/bold] {r['url'] or r['page']}")
    console.print(Panel("\n".join(lines), title=tr("Driver GPU {vendor}", vendor=VENDOR_NAMES.get(r['vendor'], '')).strip(),
                        border_style="cyan",
                        expand=False))  # senza expand=False il riquadro occupa 400 colonne nei log
    if r["error"]:
        console.print(f"[red]{tr('Controllo della GPU {name} non riuscito: {error}', name=r['name'], error=r['error'])}[/red]")


def check_all_gpus(c) -> list[dict]:
    """Tutte le schede video (NVIDIA, AMD, Intel) confrontate con il driver più recente del produttore."""
    console.print(f"\n[bold cyan][1/3] {tr('Controllo driver delle schede video (fonti ufficiali NVIDIA, AMD, Intel)...')}[/bold cyan]")
    results = gpu_check.check_gpus(c)
    if not results:
        console.print(f"[yellow]{tr('Nessuna scheda video NVIDIA, AMD o Intel rilevata.')}[/yellow]")
    for r in results:
        _print_gpu(r)
    return results


def nvidia_info(results: list[dict]) -> dict | None:
    """La prima GPU NVIDIA installabile, nel formato usato da menu e GUI per l'aggiornamento."""
    r = next((g for g in results if g["vendor"] == "nvidia" and g["can_install"]), None)
    if not r:
        return None
    return {"name": r["name"], "local": r["local"], "remote": r["remote"], "url": r["url"],
            "update": bool(r["update"]), "date": r["date"],
            "device_id": r.get("device_id", ""), "inf_name": r.get("inf_name")}


def check_nvidia_update(c):
    """Compatibilità con il menu a console: controlla tutte le GPU e ritorna i dati della NVIDIA."""
    return nvidia_info(check_all_gpus(c))

def list_third_party_drivers(c):
    console.print(f"\n[bold cyan][2/3] {tr('Inventario Driver Hardware Principali (Non-Microsoft)...')}[/bold cyan]")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column(tr("Classe"), style="cyan", width=16)
    table.add_column(tr("Dispositivo"), style="white", width=38)
    table.add_column(tr("Fornitore"), style="green", width=18)
    table.add_column(tr("Versione"), style="yellow", width=16)
    table.add_column(tr("Data"), style="dim", width=12)

    target_classes = {"Display", "Net", "Media", "System", "SCSIAdapter", "USB", "HIDClass"}
    seen = set()

    for drv in c.Win32_PnPSignedDriver():
        if not drv.DeviceName or not drv.DriverVersion:
            continue
        if drv.DriverProviderName in ("Microsoft", None) or drv.DeviceClass not in target_classes:
            continue
        key = (drv.DeviceName, drv.DriverVersion)
        if key in seen:
            continue
        seen.add(key)
        drv_date = drv.DriverDate[:8] if drv.DriverDate else "N/A"
        table.add_row(drv.DeviceClass or "N/A", drv.DeviceName[:36], drv.DriverProviderName[:16], drv.DriverVersion, drv_date)

    console.print(table)

def check_windows_update_drivers():
    console.print(f"\n[bold cyan][3/3] {tr('Scansione Catalogo Windows Update (Driver WHQL Opzionali/Chipset)...')}[/bold cyan]")
    session = win32com.client.Dispatch("Microsoft.Update.Session")
    searcher = session.CreateUpdateSearcher()
    result = searcher.Search("IsInstalled=0 and Type='Driver'")

    if result.Updates.Count == 0:
        console.print(f"[bold green]✔ {tr('Nessun driver mancante o obsoleto rilevato sul catalogo Microsoft.')}[/bold green]")
        return []

    wua_table = Table(title=tr("Driver Disponibili su Catalogo Microsoft"))
    wua_table.add_column("#", style="cyan")
    wua_table.add_column(tr("Titolo Pacchetto"), style="yellow")
    wua_table.add_column(tr("Classe"), style="green")

    updates = []
    for i in range(result.Updates.Count):
        upd = result.Updates.Item(i)
        wua_table.add_row(str(i + 1), upd.Title, getattr(upd, "DriverClass", "Hardware"))
        updates.append(upd)

    console.print(wua_table)
    return updates

if __name__ == "__main__":
    from wmi_fast import FastWMI
    wmi_client = FastWMI()
    check_nvidia_update(wmi_client)
    list_third_party_drivers(wmi_client)
    check_windows_update_drivers()
