"""Ogni testo passato a tr() deve avere la traduzione inglese, con gli stessi segnaposto."""
import ast
import string
from pathlib import Path

from locale_en import EN

SRC = Path(__file__).resolve().parent.parent / "src"


def tr_keys() -> dict[str, str]:
    """{testo italiano: file:riga} di tutte le chiamate tr("...") nei sorgenti."""
    keys = {}
    for path in sorted(SRC.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "tr":
                arg = node.args[0] if node.args else None
                assert isinstance(arg, ast.Constant) and isinstance(arg.value, str), \
                    f"{path.name}:{node.lineno}: tr() vuole un testo fisso, non un'espressione"
                keys.setdefault(arg.value, f"{path.name}:{node.lineno}")
    return keys


def fields(text: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(text) if f}


def test_every_text_has_an_english_translation():
    missing = [f"{where}: {key!r}" for key, where in tr_keys().items() if key not in EN]
    assert not missing, "Traduzioni mancanti:\n" + "\n".join(missing)


def test_placeholders_match():
    wrong = [f"{k!r} -> {v!r}" for k, v in EN.items() if fields(k) != fields(v)]
    assert not wrong, "Segnaposto diversi:\n" + "\n".join(wrong)


def test_no_unused_translations():
    unused = sorted(set(EN) - set(tr_keys()))
    assert not unused, "Voci non più usate:\n" + "\n".join(map(repr, unused))


def test_tr_formats_and_falls_back():
    import i18n
    assert i18n.tr("Errore {code}", code=5) == "Errore 5"
    assert i18n.tr("testo non tradotto") == "testo non tradotto"
