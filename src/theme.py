"""Tema di DriverCore: colori chiari/scuri, icone, curve di animazione.

Il tema si sceglie una volta all'avvio (preferenza, variabile DRIVERCORE_THEME o tema di Windows).
"""
import ctypes
import os

import customtkinter as ctk

import prefs

# --- Stile: colori e movimento (vedi la tavola "Movimento e componenti") -------
C_LIGHT = {
    "bg": "#F4F4F6", "surface": "#FFFFFF", "text": "#18181B", "text2": "#62626B",
    "muted": "#A1A1AA", "line": "#E6E6EA", "line_hover": "#D4D4DA", "hover": "#F0F0F3",
    "tile_hover": "#FBFBFC", "row_hover": "#FAFAFB",
    "accent": "#1F6FEB", "accent_hover": "#1A5FCC", "accent_soft": "#9DBDF5", "track": "#DCDCE2",
    "accent_ink": "#1A5FCC",  # testo blu: 4,5:1 anche sulle righe evidenziate
    "ok_bg": "#E6F4EA", "ok_ink": "#17703A", "warn_bg": "#FDF0E1", "warn_ink": "#9A4B00",
    "toast": "#1C1C1F", "toast_text2": "#C7C7CC", "seg_on": "#FFFFFF",
    "danger_ink": "#B42318", "danger_bg": "#FCE8E6",
}
# Stessi ruoli al buio: superfici appena più chiare dello sfondo, testo non bianco puro, accento più luminoso
C_DARK = {
    "bg": "#141416", "surface": "#1D1D20", "text": "#F1F1F4", "text2": "#A3A3AC",
    "muted": "#63636C", "line": "#2C2C31", "line_hover": "#3A3A41", "hover": "#2A2A2F",
    "tile_hover": "#232327", "row_hover": "#222226",
    "accent": "#2A6FE6", "accent_hover": "#2361D0", "accent_soft": "#294B80", "track": "#3A3A41",
    "accent_ink": "#6AA6FF",  # al buio il testo blu deve essere più chiaro dei pulsanti (6,8:1)
    "ok_bg": "#15301F", "ok_ink": "#5CD083", "warn_bg": "#36280F", "warn_ink": "#F2B65E",
    "toast": "#2B2B30", "toast_text2": "#B9B9C0", "seg_on": "#3A3A41",
    "danger_ink": "#FF8A80", "danger_bg": "#3A2224",
}
THEMES = ("auto", "light", "dark")

def windows_uses_dark() -> bool:
    """Tema delle app scelto in Impostazioni di Windows (Personalizzazione › Colori)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False

THEME = os.environ.get("DRIVERCORE_THEME") or prefs.get("theme", "auto")
THEME = THEME if THEME in THEMES else "auto"
DARK = windows_uses_dark() if THEME == "auto" else THEME == "dark"
C = C_DARK if DARK else C_LIGHT
ctk.set_appearance_mode("Dark" if DARK else "Light")

def dark_title_bar(win) -> None:
    """Barra del titolo scura (DWMWA_USE_IMMERSIVE_DARK_MODE, Windows 10 20H1+ e 11)."""
    if not DARK:
        return
    try:
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        on = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), ctypes.sizeof(on))
    except Exception:
        pass
TOAST_DOTS = {"success": "#34C759", "info": C["accent"], "warning": "#FF9F0A", "error": "#FF453A"}

# Icone del font di sistema (Segoe Fluent Icons su Windows 11, MDL2 su Windows 10)
GLYPH = {
    "app": "", "backup": "", "shield": "", "history": "",
    "delete": "", "package": "", "palette": "", "bolt": "", "check": "",
    "warning": "",
}
GLYPH["hide"] = "\uED1A"

def ease_out_quint(t: float) -> float:      # ≈ cubic-bezier(.22, 1, .36, 1)
    return 1 - (1 - t) ** 5

def ease_out_back(t: float) -> float:       # ≈ cubic-bezier(.34, 1.56, .64, 1): leggero rimbalzo
    s = 1.70158
    t -= 1
    return 1 + (s + 1) * t ** 3 + s * t ** 2

def ease_in_cubic(t: float) -> float:       # ≈ cubic-bezier(.4, 0, 1, 1)
    return t ** 3

def ease_in_out_cubic(t: float) -> float:   # ≈ cubic-bezier(.45, 0, .2, 1)
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2

def mix(c1: str, c2: str, t: float) -> str:
    """Interpola due colori esadecimali (t fuori da 0..1 viene limitato)."""
    t = max(0.0, min(1.0, t))
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(a, b))

def _system_animations_enabled() -> bool:
    """Rispetta "Effetti di animazione" di Windows (SPI_GETCLIENTAREAANIMATION)."""
    try:
        val = ctypes.c_bool(True)
        ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(val), 0)
        return bool(val.value)
    except Exception:
        return True

ANIMATE = _system_animations_enabled()
