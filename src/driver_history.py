"""Cronologia delle installazioni di driver e annullamento del singolo aggiornamento.

Ogni installazione registra quali pacchetti oemN.inf sono comparsi e quali sono spariti dal DriverStore,
con l'impronta (SHA-256) di ciascun INF. Per annullare:
1. si rimettono nel DriverStore i pacchetti precedenti che non ci sono più, cercandoli per impronta
   nei backup (Windows\\INF\\oemN.inf è una copia identica dell'INF esportato da pnputil);
2. si tolgono i pacchetti nuovi dalle periferiche e dal DriverStore (pnputil /delete-driver /uninstall);
3. Windows reinstalla la periferica col miglior driver rimasto, cioè quello precedente.
"""
import hashlib
import json
import os
import re
import subprocess
import threading
import uuid
from datetime import datetime
from pathlib import Path

from rich.console import Console

from config import BACKUP_ROOT, HISTORY_FILE
from i18n import tr

console = Console()
NO_WIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
INF_DIR = Path(os.environ.get("WINDIR", r"C:\Windows")) / "INF"
MAX_ENTRIES = 200
OEM_INF = re.compile(r"oem\d+\.inf", re.IGNORECASE)
PNPUTIL_OK = (0, 3010)
ACTIVE = ("installed", "partial")  # "partial": annullamento interrotto, si può riprovare
_lock = threading.Lock()


# --- Impronte dei pacchetti ---------------------------------------------------------
def file_hash(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def snapshot_infs(inf_dir: Path | None = None) -> dict[str, str]:
    """{oemN.inf: sha256} dei pacchetti di terze parti presenti ora."""
    inf_dir = inf_dir or INF_DIR
    snap = {}
    for p in inf_dir.glob("oem*.inf"):
        h = file_hash(p)
        if h:
            snap[p.name.lower()] = h
    return snap


def find_in_backups(hashes: set[str], backup_root: Path | None = None) -> dict[str, Path]:
    """Cerca nei backup (dal più recente) gli INF con queste impronte: {sha256: percorso dell'INF}."""
    root = backup_root or BACKUP_ROOT
    found: dict[str, Path] = {}
    wanted = set(h for h in hashes if h)
    if not wanted or not root.exists():
        return found
    for backup in sorted((d for d in root.iterdir() if d.is_dir()), key=lambda d: d.name, reverse=True):
        for inf in backup.glob("*/*.inf"):
            h = file_hash(inf)
            if h in wanted and h not in found:
                found[h] = inf
        if wanted <= found.keys():
            break
    return found


# --- Archivio ---------------------------------------------------------------------
def load_history(path: Path | None = None) -> list[dict]:
    try:
        data = json.loads((path or HISTORY_FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save(entries: list[dict], path: Path | None = None) -> None:
    path = path or HISTORY_FILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entries[-MAX_ENTRIES:], indent=1, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        console.print("[yellow]! " + tr("Cronologia non salvata: {error}", error=e) + "[/yellow]")


def build_entry(kind: str, name: str, device_id: str, old_ver: str, new_ver: str, old_inf: str | None,
                before: dict[str, str], after: dict[str, str]) -> dict:
    """Funzione pura: confronta le due istantanee del DriverStore e descrive l'installazione."""
    added = {n: h for n, h in after.items() if before.get(n) != h}
    removed = {n: h for n, h in before.items() if n not in after}
    old_inf = (old_inf or "").lower()
    previous = {"inf": old_inf, "hash": before.get(old_inf)} if OEM_INF.fullmatch(old_inf) else None
    return {
        "id": uuid.uuid4().hex[:12],
        "time": datetime.now().isoformat(timespec="seconds"),
        "kind": kind,
        "name": name,
        "device_id": device_id or "",
        "old_ver": old_ver or "",
        "new_ver": new_ver or "",
        "previous": previous,   # driver usato dalla periferica prima dell'installazione
        "added": added,         # pacchetti comparsi
        "removed": removed,     # pacchetti spariti (es. l'installer NVIDIA toglie la versione precedente)
        "status": "installed",
    }


def record_install(kind: str, name: str, device_id: str, old_ver: str, new_ver: str, old_inf: str | None,
                   before: dict[str, str], after: dict[str, str] | None = None) -> dict:
    entry = build_entry(kind, name, device_id, old_ver, new_ver, old_inf, before,
                        snapshot_infs() if after is None else after)
    with _lock:
        entries = load_history()
        entries.append(entry)
        _save(entries)
    return entry


def protected_infs(entries: list[dict] | None = None) -> set[str]:
    """Pacchetti precedenti che servono per annullare: la pulizia del DriverStore non deve toccarli."""
    entries = load_history() if entries is None else entries
    return {e["previous"]["inf"] for e in entries
            if e.get("status") in ACTIVE and e.get("previous") and e["previous"].get("inf")}


def backups_needed_for_undo(backups: list[Path], entries: list[dict] | None = None,
                            current: dict[str, str] | None = None) -> set[Path]:
    """Backup che contengono pacchetti precedenti non più nel DriverStore: non vanno eliminati."""
    entries = load_history() if entries is None else entries
    present = set((snapshot_infs() if current is None else current).values())
    wanted = set()
    for e in entries:
        if e.get("status") not in ACTIVE:
            continue
        wanted |= set((e.get("removed") or {}).values())
        if e.get("previous") and e["previous"].get("hash"):
            wanted.add(e["previous"]["hash"])
    wanted -= present
    wanted.discard(None)
    keep = set()
    for b in sorted(backups, key=lambda d: d.name, reverse=True):
        if not wanted:
            break
        hits = {file_hash(inf) for inf in b.glob("*/*.inf")} & wanted
        if hits:
            keep.add(b)
            wanted -= hits
    return keep


# --- Annullamento -----------------------------------------------------------------
def undo_plan(entry: dict, entries: list[dict], current: dict[str, str],
              backup_root: Path | None = None) -> dict:
    """Cosa servirebbe per annullare `entry`, senza toccare nulla.

    Ritorna {"ok", "reason", "remove": [oemN.inf], "restore": [percorsi INF], "warnings": [...]}.
    """
    plan = {"ok": False, "reason": "", "remove": [], "restore": [], "warnings": []}
    if entry.get("status") not in ACTIVE:
        plan["reason"] = tr("Questo aggiornamento è già stato annullato.")
        return plan

    dev = (entry.get("device_id") or "").upper()
    later = [e for e in entries
             if e.get("status") in ACTIVE and e.get("time", "") > entry.get("time", "") and e is not entry
             and ((dev and (e.get("device_id") or "").upper() == dev) or set(e.get("added", {})) & set(entry["added"]))]
    if later:
        plan["reason"] = tr("Dopo questo aggiornamento la stessa periferica è stata aggiornata di nuovo "
                            "({version}): annulla prima quello.", version=later[-1]["new_ver"])
        return plan

    plan["remove"] = sorted(n for n, h in entry.get("added", {}).items() if current.get(n) == h)
    if not plan["remove"]:
        plan["reason"] = tr("Il pacchetto era già nel DriverStore prima dell'installazione, oppure è stato rimosso "
                            "o sostituito nel frattempo: non c'è nulla da togliere.")
        return plan

    # Pacchetti da rimettere: quelli spariti con l'installazione e il driver precedente se non c'è più
    present = set(current.values())
    removed = {h for h in entry.get("removed", {}).values() if h and h not in present}
    prev = entry.get("previous")
    prev_hash = prev.get("hash") if prev else None
    needed = removed | ({prev_hash} if prev_hash and prev_hash not in present else set())
    found = find_in_backups(needed, backup_root)
    plan["restore"] = [str(p) for p in found.values()]

    if not prev:
        plan["warnings"].append(tr("Prima dell'installazione la periferica non aveva un driver di terze parti: "
                                   "userà il driver generico di Windows o resterà senza driver."))
    elif prev_hash in needed and prev_hash not in found:
        plan["warnings"].append(tr("Il driver precedente ({version}) non è più nel DriverStore "
                                   "né nei backup: la periferica userà il miglior driver rimasto.",
                                   version=entry.get("old_ver") or prev["inf"]))
    missing = len(removed - found.keys() - {prev_hash})
    if missing:
        plan["warnings"].append(tr("{count} pacchetti tolti durante l'installazione non sono nei backup.", count=missing))
    if entry.get("kind") == "nvidia":
        plan["warnings"].append(tr("Torna indietro il driver della scheda; il pannello di controllo NVIDIA "
                                   "può restare alla versione nuova."))
    plan["ok"] = True
    return plan


def _pnputil(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["pnputil", *args], capture_output=True, text=True, encoding="mbcs",
                          errors="replace", creationflags=NO_WIN)


def _set_status(entry_id: str, **fields) -> None:
    with _lock:
        entries = load_history()
        for e in entries:
            if e["id"] == entry_id:
                e.update(fields)
        _save(entries)


def undo_install(entry_id: str) -> bool:
    """Annulla l'installazione registrata con `entry_id`. Ritorna True se riuscito."""
    entries = load_history()
    entry = next((e for e in entries if e["id"] == entry_id), None)
    if entry is None:
        console.print("[bold red]✖ " + tr("Voce della cronologia non trovata.") + "[/bold red]")
        return False
    plan = undo_plan(entry, entries, snapshot_infs())
    if not plan["ok"]:
        console.print(f"[yellow]! {entry['name']}: {plan['reason']}[/yellow]")
        return False

    console.print("\n[bold cyan]" + tr("Annullamento: {name} {new} ➔ {old}", name=entry["name"], new=entry["new_ver"],
                                          old=entry["old_ver"] or tr("driver precedente")) + "[/bold cyan]")
    for inf in plan["restore"]:
        res = _pnputil("/add-driver", inf)
        if res.returncode in PNPUTIL_OK:
            console.print(" -> " + tr("Driver precedente rimesso nel DriverStore ({folder}).", folder=Path(inf).parent.name))
        else:
            console.print("[yellow]! " + tr("Non è stato possibile rimettere {name} (codice {code}).", name=Path(inf).name,
                                              code=res.returncode) + "[/yellow]")

    failed = []
    for inf in plan["remove"]:
        res = _pnputil("/delete-driver", inf, "/uninstall")
        if res.returncode in PNPUTIL_OK:
            console.print(" -> " + tr("Rimosso il pacchetto {name}.", name=inf))
        else:
            failed.append(tr("{name} (codice {code})", name=inf, code=res.returncode))
    _pnputil("/scan-devices")  # la periferica si reinstalla col miglior driver rimasto

    if failed:
        console.print("[bold red]✖ " + tr("Annullamento incompleto: Windows non ha rimosso {names}.", names=", ".join(failed))
                      + "[/bold red]")
        if len(failed) < len(plan["remove"]):
            _set_status(entry_id, status="partial", undone_at=datetime.now().isoformat(timespec="seconds"))
        return False
    _set_status(entry_id, status="undone", undone_at=datetime.now().isoformat(timespec="seconds"))
    console.print("[bold green]✔ " + tr("{name}: aggiornamento annullato.", name=entry["name"]) + "[/bold green]")
    for w in plan["warnings"]:
        console.print(f"[yellow]! {w}[/yellow]")
    return True
