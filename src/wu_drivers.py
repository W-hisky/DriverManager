"""Driver proposti da Windows Update (API di Windows Update Agent).

Sono i driver che Windows stesso sceglie per le periferiche presenti: non serve verificarne l'INF.
La ricerca restituisce dizionari semplici (stesso formato degli aggiornamenti del Catalog, con source="wu"),
utilizzabili da qualunque thread; l'installazione ripete la ricerca nel proprio thread e prende
gli aggiornamenti per UpdateID (gli oggetti COM di Windows Update non vanno passati tra thread).
"""
import re
from datetime import datetime

from rich.console import Console

import driver_history as dh
import ignore_list
from deep_catalog import extract_generic_hwid, extract_specific_hwid, installed_driver_date
from i18n import tr

console = Console()
SEARCH = "IsInstalled=0 and Type='Driver' and IsHidden=0"
WU_SUCCEEDED, WU_SUCCEEDED_WITH_ERRORS = 2, 3
VERSION_IN_TITLE = re.compile(r"(\d+(?:\.\d+){1,3})\s*$")


def _session():
    import win32com.client
    session = win32com.client.Dispatch("Microsoft.Update.Session")
    session.ClientApplicationID = "DriverCore"
    return session


def version_from_title(title: str) -> str:
    """'Realtek - Net - 10.68.815.2023' -> '10.68.815.2023' (l'API non espone la versione del driver)."""
    m = VERSION_IN_TITLE.search(title or "")
    return m.group(1) if m else ""


def _wu_date(value) -> str:
    try:
        return f"{value:%Y-%m-%d}"
    except (TypeError, ValueError):
        return str(value or "")[:10]


def find_installed(hwid: str, drivers) -> object | None:
    """Il driver installato sulla periferica con questo ID (Win32_PnPSignedDriver.HardWareID)."""
    h = (hwid or "").upper()
    best = None
    for d in drivers:
        dh_ = (getattr(d, "HardWareID", None) or "").upper()
        if not dh_:
            continue
        if dh_ == h:
            return d
        if best is None and (h.startswith(dh_) or dh_.startswith(h)):
            best = d
    return best


def to_item(u, drivers) -> dict:
    """Un aggiornamento di Windows Update nel formato degli aggiornamenti mostrati da DriverCore."""
    hwid = (u.DriverHardwareID or "").upper()
    drv = find_installed(hwid, drivers)
    title = u.Title or ""
    return {
        "source": "wu",
        "name": u.DriverModel or title,
        "title": title,
        "hwid": hwid,
        "specific": extract_specific_hwid(hwid),
        "generic": extract_generic_hwid(hwid),
        "provider": u.DriverProvider or "",
        "local_ver": (drv.DriverVersion if drv else "") or "—",
        "local_date": (installed_driver_date(getattr(drv, "InfName", None), drv.DriverDate)
                       if drv else datetime(2000, 1, 1)),
        "device_id": getattr(drv, "DeviceID", "") if drv else "",
        "inf_name": getattr(drv, "InfName", None) if drv else None,
        "remote_ver": version_from_title(title) or _wu_date(u.DriverVerDate),
        "remote_date": _wu_date(u.DriverVerDate),
        "update_id": u.Identity.UpdateID,
        "verified": True,
        "verify_reason": tr("Proposto da Windows Update: è il driver che Windows stesso sceglie per questa periferica."),
    }


def search_drivers(drivers, ignored=frozenset()) -> tuple[list[dict], bool]:
    """(aggiornamenti, ricerca riuscita). drivers: Win32_PnPSignedDriver già letti (per la versione installata).

    Va chiamata in un thread con COM inizializzato.
    """
    console.print(tr("Controllo: Windows Update..."))
    try:
        result = _session().CreateUpdateSearcher().Search(SEARCH)
    except Exception as e:  # servizio disattivato, rete assente, criteri aziendali...
        console.print("[yellow]! " + tr("Windows Update non disponibile: {error}", error=e) + "[/yellow]")
        return [], False
    items = []
    for i in range(result.Updates.Count):
        item = to_item(result.Updates.Item(i), drivers)
        hw = [h for h in (item["specific"], item["generic"], item["hwid"]) if h]
        if any(ignore_list.is_ignored(ignored, h, item["remote_ver"], item["update_id"], wu=True) for h in hw):
            continue
        items.append(item)
    return items, True


def merge(catalog: list[dict], wu: list[dict]) -> list[dict]:
    """Se Windows Update propone un driver per una periferica, quello vince sul Catalog (è la scelta di Windows)."""
    wu_ids = {h for w in wu for h in (w["generic"], w["hwid"]) if h}
    kept = [c for c in catalog if not ({c.get("generic"), c.get("hwid")} & wu_ids)]
    return sorted(kept + wu, key=lambda i: i["name"].lower())


def install(items: list[dict]) -> tuple[int, int]:
    """Installa gli aggiornamenti di Windows Update indicati (uno alla volta, per la cronologia). (riusciti, falliti)"""
    if not items:
        return 0, 0
    import win32com.client
    wanted = {i["update_id"]: i for i in items}
    session = _session()
    console.print("\n[bold cyan]" + tr("Ricerca degli aggiornamenti su Windows Update...") + "[/bold cyan]")
    result = session.CreateUpdateSearcher().Search(SEARCH)
    found = {}
    for k in range(result.Updates.Count):
        u = result.Updates.Item(k)
        if u.Identity.UpdateID in wanted:
            found[u.Identity.UpdateID] = u

    ok = failed = 0
    for uid, item in wanted.items():
        u = found.get(uid)
        if u is None:
            console.print("[yellow]! " + tr("{name}: non più proposto da Windows Update.", name=item["name"]) + "[/yellow]")
            failed += 1
            continue
        try:
            if not u.EulaAccepted:
                u.AcceptEula()
            coll = win32com.client.Dispatch("Microsoft.Update.UpdateColl")
            coll.Add(u)
            console.print(" -> " + tr("Download di {name} da Windows Update...", name=item["name"]))
            downloader = session.CreateUpdateDownloader()
            downloader.Updates = coll
            downloader.Download()
            console.print(" -> " + tr("Installazione {name} tramite Windows Update...", name=item["name"]))
            before = dh.snapshot_infs()
            installer = session.CreateUpdateInstaller()
            installer.Updates = coll
            res = installer.Install()
            if res.ResultCode in (WU_SUCCEEDED, WU_SUCCEEDED_WITH_ERRORS):
                ok += 1
                console.print("[bold green]✔ " + tr("{name} aggiornato alla versione {remote_ver}!", name=item["name"],
                                                    remote_ver=item["remote_ver"]) + "[/bold green]")
                if res.RebootRequired:
                    console.print("[bold yellow]! " + tr("Riavvio del sistema consigliato.") + "[/bold yellow]")
                dh.record_install("wu", item["name"], item.get("device_id", ""),
                                  "" if item.get("local_ver") in (None, "", "—") else item["local_ver"],
                                  item["remote_ver"], item.get("inf_name"), before)
            else:
                failed += 1
                console.print("[bold red]✖ " + tr("Installazione di {name} non riuscita (Windows Update codice {code}).",
                                                  name=item["name"], code=res.ResultCode) + "[/bold red]")
        except Exception as e:
            failed += 1
            console.print("[bold red]✖ " + tr("Errore su {name}: {e}", name=item["name"], e=e) + "[/bold red]")
    return ok, failed
