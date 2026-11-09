"""Lingua dell'interfaccia: italiano (testi nel codice) o inglese (catalogo in locale_en.py).

Il testo italiano è la chiave: tr("Backup di {n} driver", n=3). Con l'inglese si cerca nel catalogo;
se manca una voce si usa l'italiano (il test test_i18n controlla che non manchi nulla).
La lingua si sceglie all'avvio: impostazione "language" in settings.json ("auto", "it", "en");
con "auto" segue la lingua di Windows (italiano se Windows è in italiano, altrimenti inglese).
"""
import ctypes
import json
import os
from pathlib import Path

LANGUAGES = ("auto", "it", "en")
_SETTINGS = Path(os.environ.get("DRIVERCORE_HOME", "C:/DriverManager")) / "settings.json"


def windows_language() -> str:
    try:
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return "it" if lang_id & 0x3FF == 0x10 else "en"  # 0x10 = LANG_ITALIAN
    except Exception:
        return "it"


def configured_language() -> str:
    try:
        value = json.loads(_SETTINGS.read_text(encoding="utf-8")).get("language", "auto")
    except (OSError, ValueError, AttributeError):
        value = "auto"
    return value if value in LANGUAGES else "auto"


def resolve(setting: str) -> str:
    return windows_language() if setting == "auto" else setting


LANG = resolve(os.environ.get("DRIVERCORE_LANG") or configured_language())
_CATALOG: dict[str, str] = {}
if LANG == "en":
    from locale_en import EN as _CATALOG  # noqa: E402


def tr(text: str, **kw) -> str:
    out = _CATALOG.get(text, text)
    return out.format(**kw) if kw else out


MONTHS = (("gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic") if LANG == "it" else
          ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"))


def fmt_day_month(d) -> str:
    """'9 lug' / 'Jul 9'."""
    return f"{d.day} {MONTHS[d.month - 1]}" if LANG == "it" else f"{MONTHS[d.month - 1]} {d.day}"


def fmt_date(d) -> str:
    """'9 lug 2025' / 'Jul 9, 2025'; senza data: 'data sconosciuta'."""
    if not d:
        return tr("data sconosciuta")
    return f"{fmt_day_month(d)} {d.year}" if LANG == "it" else f"{fmt_day_month(d)}, {d.year}"


def save_language(value: str) -> None:
    """Salva la scelta (vale dal prossimo avvio)."""
    try:
        data = json.loads(_SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data["language"] = value
    _SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
