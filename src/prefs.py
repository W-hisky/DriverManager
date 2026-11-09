"""Preferenze dell'utente in settings.json (lingua, tema, controllo automatico, ultimo controllo versioni)."""
import json

from config import SETTINGS_FILE


def load(path=None) -> dict:
    try:
        data = json.loads((path or SETTINGS_FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def get(key: str, default=None, path=None):
    return load(path).get(key, default)


def set_value(key: str, value, path=None) -> None:
    path = path or SETTINGS_FILE
    data = load(path)
    data[key] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
