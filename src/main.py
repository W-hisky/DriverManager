import ctypes
import sys
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table

from i18n import tr
from wmi_fast import FastWMI
from driver_history import load_history, snapshot_infs, undo_install, undo_plan

from driver_scanner import (
    check_nvidia_update,
    list_third_party_drivers,
    check_windows_update_drivers,
)
from driver_installer import (
    backup_current_drivers,
    download_file,
    install_nvidia_driver,
    install_windows_update_drivers,
    update_game_runtimes,
)
from driver_cleanup import find_obsolete_driver_packages, remove_obsolete_driver_packages, dism_component_cleanup
from deep_catalog import deep_scan_peripherals, install_catalog_cab_updates, scan_problem_devices

console = Console()

def ensure_admin():
    if ctypes.windll.shell32.IsUserAnAdmin() == 0:
        console.print("[bold red]✖ " + tr("Errore: Avvia il programma come Amministratore.") + "[/bold red]")
        sys.exit(1)

STATUS_LABEL = {"installed": tr("installato"), "partial": tr("annullato in parte"), "undone": tr("annullato")}


def history_menu():
    entries = list(reversed(load_history()))[:20]
    if not entries:
        console.print("[green]" + tr("Nessuna installazione registrata.") + "[/green]")
        return
    table = Table(title=tr("Cronologia driver (più recenti in alto)"))
    for col in ("#", tr("Data"), tr("Periferica"), tr("Da"), tr("A"), tr("Stato")):
        table.add_column(col)
    for n, e in enumerate(entries, 1):
        table.add_row(str(n), e["time"].replace("T", " ")[:16], e["name"][:40], e["old_ver"] or "—",
                      e["new_ver"], STATUS_LABEL.get(e["status"], e["status"]))
    console.print(table)
    pick = Prompt.ask(tr("Numero dell'aggiornamento da annullare (invio per tornare)"), default="")
    if not pick.isdigit() or not 1 <= int(pick) <= len(entries):
        return
    entry = entries[int(pick) - 1]
    plan = undo_plan(entry, load_history(), snapshot_infs())
    if not plan["ok"]:
        console.print(f"[yellow]! {plan['reason']}[/yellow]")
        return
    for w in plan["warnings"]:
        console.print(f"[yellow]! {w}[/yellow]")
    target = entry["old_ver"] or tr("il driver precedente")
    if Confirm.ask(tr("Riportare {name} a {version}?", name=entry["name"], version=target), default=False):
        backup_current_drivers()
        undo_install(entry["id"])


def ask_backup(question: str | None = None) -> None:
    if Confirm.ask(question or tr("Vuoi eseguire un backup dei driver prima di procedere?"), default=True):
        backup_current_drivers()


def main():
    ensure_admin()
    c = FastWMI()

    nv_info = check_nvidia_update(c)
    list_third_party_drivers(c)
    wua_updates = check_windows_update_drivers()
    deep_updates = []

    while True:
        console.print("\n[bold magenta]=== DRIVERCORE ===[/bold magenta]")
        console.print(tr("1. Esegui Backup completo dei driver attuali (pnputil)"))
        console.print(tr("2. Aggiorna GPU NVIDIA (Modalità Slim Zero-Telemetria / Standard)"))
        console.print(tr("3. [bold yellow][DEEP SCAN][/bold yellow] Cerca aggiornamenti per TUTTE le periferiche (Chipset, LAN, Audio, USB)"))
        console.print(tr("4. Installa driver standard da Windows Update"))
        console.print(tr("5. Aggiorna Runtime di Gioco (Visual C++ / .NET)"))
        console.print(tr("6. Rimuovi pacchetti driver obsoleti dal DriverStore e pulisci componenti di sistema"))
        console.print(tr("7. Ripeti scansione base"))
        console.print(tr("8. Periferiche senza driver o in errore (Gestione dispositivi)"))
        console.print(tr("9. Cronologia driver installati e annullamento"))
        console.print(tr("0. Esci"))

        c.refresh()
        choice = Prompt.ask("\n" + tr("Seleziona un'opzione"), choices=[str(n) for n in range(10)], default="3")

        if choice == "0":
            console.print("[cyan]" + tr("Uscita completata.") + "[/cyan]")
            break

        elif choice == "1":
            backup_current_drivers()

        elif choice == "2":
            if not nv_info:
                console.print("[yellow]" + tr("Informazioni GPU NVIDIA non disponibili.") + "[/yellow]")
                continue
            if not nv_info["update"]:
                if not Confirm.ask(tr("Il driver NVIDIA risulta già aggiornato. Vuoi scaricarlo comunque?")):
                    continue
            ask_backup()

            exe_path = download_file(nv_info["url"])
            if exe_path and Confirm.ask(tr("Avviare l'installazione del driver NVIDIA ora?"), default=True):
                slim = Confirm.ask(tr("Usare la modalità SLIM (rimuove telemetria e bloatware NVIDIA)?"), default=True)
                clean = Confirm.ask(tr("Eseguire un'installazione pulita (-clean)?"), default=False)
                install_nvidia_driver(exe_path, clean_install=clean, slim_mode=slim, gpu=nv_info)

        elif choice == "3":
            deep_updates = deep_scan_peripherals(c)
            if deep_updates and Confirm.ask("\n" + tr("Vuoi scaricare e installare i {count} aggiornamenti WHQL trovati?",
                                                      count=len(deep_updates)), default=True):
                ask_backup(tr("Eseguire un backup di sicurezza prima dell'installazione?"))
                install_catalog_cab_updates(deep_updates)

        elif choice == "4":
            if not wua_updates:
                console.print("[green]" + tr("Nessun driver in sospeso su Windows Update locale.") + "[/green]")
                continue
            ask_backup()
            install_windows_update_drivers(wua_updates)

        elif choice == "5":
            update_game_runtimes()

        elif choice == "6":
            candidates = find_obsolete_driver_packages(c)
            if candidates:
                for o in candidates:
                    console.print(f" • {o['driver']}  {o['provider']} / {o['class']}  {o['version']}  "
                                  + tr("(resta {version})", version=o["kept_version"]))
                if Confirm.ask(tr("Rimuovere questi {count} pacchetti obsoleti?", count=len(candidates)), default=False):
                    if backup_current_drivers():
                        remove_obsolete_driver_packages(candidates)
                    else:
                        console.print("[bold red]✖ " + tr("Backup non riuscito: pulizia annullata.") + "[/bold red]")
            if Confirm.ask(tr("Eseguire anche la pulizia dei componenti di sistema (DISM, può richiedere diversi minuti)?"),
                           default=False):
                dism_component_cleanup()

        elif choice == "8":
            fixable = [d for d in scan_problem_devices(c) if d.get("update_id")]
            if fixable and Confirm.ask("\n" + tr("Installare i {count} driver trovati?", count=len(fixable)), default=True):
                ask_backup(tr("Eseguire un backup di sicurezza prima dell'installazione?"))
                install_catalog_cab_updates(fixable)

        elif choice == "9":
            history_menu()

        elif choice == "7":
            nv_info = check_nvidia_update(c)
            list_third_party_drivers(c)
            wua_updates = check_windows_update_drivers()

if __name__ == "__main__":
    main()
