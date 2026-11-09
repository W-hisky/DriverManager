"""Aggiornamenti ignorati: scelti dall'utente ("Ignora") o rifiutati da Windows durante l'installazione.

Ogni voce raggruppa le chiavi che nasconde (ID del Catalog, periferica+versione, periferica intera)
e ha un nome leggibile, così si può elencare e ripristinare.

Formato del file: {"version": 2, "entries": [{"id", "name", "version", "scope", "time", "keys": [...]}]}.
Il vecchio formato (un elenco di chiavi) viene letto come un'unica voce "rifiutati da Windows".
"""
import json
import threading
import uuid
from datetime import datetime

from config import IGNORED_UPDATES_FILE

ALL_VERSIONS = "*"
SCOPES = ("version", "device", "auto")  # questa versione / tutta la periferica / rifiutato da Windows
_lock = threading.Lock()


def ignore_key(hwid: str, ver: str) -> str:
    """Chiave periferica+versione: il Catalog pubblica lo stesso driver con molti ID diversi
    (uno per ogni versione di Windows), quindi ignorare il solo ID non basta. ver="*": tutte le versioni."""
    return f"{(hwid or '').upper()}|{(ver or '').strip()}"


def wu_key(update_id: str) -> str:
    return f"wu|{update_id}"


def load_entries(path=None) -> list[dict]:
    path = path or IGNORED_UPDATES_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(data, list):  # formato precedente: solo chiavi, tutte rifiutate da Windows
        keys = [k for k in data if isinstance(k, str)]
        return [{"id": "legacy", "name": "", "version": "", "scope": "auto", "time": "", "keys": keys}] if keys else []
    entries = data.get("entries", []) if isinstance(data, dict) else []
    return [e for e in entries if isinstance(e, dict) and isinstance(e.get("keys"), list)]


def _save(entries: list[dict], path=None) -> None:
    path = path or IGNORED_UPDATES_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 2, "entries": entries}, indent=1, ensure_ascii=False), encoding="utf-8")


def load_ignored_updates(path=None) -> set[str]:
    return {k for e in load_entries(path) for k in e["keys"]}


def add_ignored(keys, name: str = "", version: str = "", scope: str = "auto", path=None) -> dict | None:
    keys = sorted({k for k in keys if k})
    if not keys:
        return None
    entry = {"id": uuid.uuid4().hex[:10], "name": name, "version": version, "scope": scope,
             "time": datetime.now().isoformat(timespec="seconds"), "keys": keys}
    with _lock:
        entries = load_entries(path)
        entries.append(entry)
        try:
            _save(entries, path)
        except OSError:
            return None
    return entry


def remove_entry(entry_id: str, path=None) -> bool:
    with _lock:
        entries = load_entries(path)
        kept = [e for e in entries if e["id"] != entry_id]
        if len(kept) == len(entries):
            return False
        _save(kept, path)
    return True


def keys_for(item: dict, scope: str) -> list[str]:
    """Le chiavi che nascondono questo aggiornamento (scope "version") o la periferica intera ("device")."""
    hwids = {h for h in (item.get("specific"), item.get("generic"), item.get("hwid")) if h}
    if scope == "device":
        return [ignore_key(h, ALL_VERSIONS) for h in hwids]
    keys = [ignore_key(h, item.get("remote_ver")) for h in hwids]
    if item.get("source") == "wu" and item.get("update_id"):
        keys.append(wu_key(item["update_id"]))
    elif item.get("update_id"):
        keys.append(item["update_id"])
    return keys


def is_ignored(ignored, hwid: str, ver: str, update_id: str | None = None, wu: bool = False) -> bool:
    if update_id and (wu_key(update_id) if wu else update_id) in ignored:
        return True
    return ignore_key(hwid, ver) in ignored or ignore_key(hwid, ALL_VERSIONS) in ignored
