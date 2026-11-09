"""Una sola finestra di DriverCore: un secondo avvio porta in primo piano quella già aperta ed esce.

- La prima istanza (già amministratore) crea il mutex "Local\\DriverCore.GUI".
- Un secondo avvio lo trova (o riceve "accesso negato", perché il mutex appartiene a un processo
  amministratore): non chiede l'UAC, lascia una richiesta in un file e cede il diritto di primo piano.
- La finestra aperta controlla il file due volte al secondo e torna davanti, anche se minimizzata.
  Il file funziona tra processi con privilegi diversi, dove i messaggi di finestra verrebbero bloccati.
"""
import ctypes
import time

from config import BASE_DIR

MUTEX_NAME = "Local\\DriverCore.GUI"
FOCUS_FILE = BASE_DIR / ".focus_request"
_SYNCHRONIZE = 0x00100000
_ERROR_ACCESS_DENIED = 5
_ERROR_ALREADY_EXISTS = 183
_ASFW_ANY = -1
_handle = None  # resta aperto finché il programma è in esecuzione


def _k32():
    k = ctypes.windll.kernel32
    k.OpenMutexW.restype = ctypes.c_void_p
    k.CreateMutexW.restype = ctypes.c_void_p
    return k


def another_running() -> bool:
    k = _k32()
    h = k.OpenMutexW(_SYNCHRONIZE, False, MUTEX_NAME)
    if h:
        k.CloseHandle(ctypes.c_void_p(h))
        return True
    return k.GetLastError() == _ERROR_ACCESS_DENIED


def claim() -> bool:
    """True se questa è la prima istanza (e da ora lo resta)."""
    global _handle
    k = _k32()
    h = k.CreateMutexW(None, False, MUTEX_NAME)
    if not h:
        return True  # nel dubbio non impedire l'avvio
    if k.GetLastError() == _ERROR_ALREADY_EXISTS:
        k.CloseHandle(ctypes.c_void_p(h))
        return False
    _handle = h
    return True


def request_focus() -> None:
    """Chiamata dal secondo avvio: chiede alla finestra già aperta di venire davanti."""
    try:
        ctypes.windll.user32.AllowSetForegroundWindow(_ASFW_ANY)
    except Exception:
        pass
    try:
        FOCUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        FOCUS_FILE.write_text(str(time.time()), encoding="utf-8")
    except OSError:
        pass


def watch(root, interval_ms: int = 500, on_focus=None) -> None:
    """Nella prima istanza: controlla le richieste e porta la finestra in primo piano."""
    try:
        last = FOCUS_FILE.stat().st_mtime
    except OSError:
        last = 0.0

    def check():
        nonlocal last
        try:
            m = FOCUS_FILE.stat().st_mtime
        except OSError:
            m = last
        if m > last:
            last = m
            bring_to_front(root)
            if on_focus:
                on_focus()
        root.after(interval_ms, check)

    root.after(interval_ms, check)


def bring_to_front(root) -> None:
    try:
        root.deiconify()
        root.lift()
        root.attributes("-topmost", True)
        root.after(200, lambda: root.attributes("-topmost", False))
        root.focus_force()
    except Exception:
        pass
