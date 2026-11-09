import ctypes
import ctypes.wintypes
import os
import re
import site
import sys
import threading
import time
import logging
import logging.handlers
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import APP_VERSION, BASE_DIR, FROZEN, SRC_DIR, LOG_DIR, BACKUP_ROOT as BACKUP_DIR, app_command  # noqa: E402

VENV_SITE = BASE_DIR / ".venv" / "Lib" / "site-packages"
LOG_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# Controllo automatico (avviato dall'Utilità di pianificazione): senza finestra e senza diritti di amministratore
if "--auto-scan" in sys.argv or "--test-notify" in sys.argv:
    import auto_scan
    auto_scan.main(sys.argv[1:])
    sys.exit(0)

SELFTEST = "--selftest" in sys.argv


def _process_start(pid: int | None = None) -> float:
    """Ora di creazione di un processo (stesso orologio di time.time()), per misurare l'avvio.

    Nel .exe a file unico conta il processo padre (scompatta e poi avvia questo): FROZEN usa quello.
    """
    k32 = ctypes.windll.kernel32
    k32.OpenProcess.restype = ctypes.c_void_p
    if pid is None:
        pid = os.getppid() if FROZEN else os.getpid()
    handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    ft_create, ft_x = ctypes.c_ulonglong(), ctypes.c_ulonglong()
    k32.GetProcessTimes(ctypes.c_void_p(handle), ctypes.byref(ft_create), ctypes.byref(ft_x),
                        ctypes.byref(ft_x), ctypes.byref(ft_x))
    k32.CloseHandle(ctypes.c_void_p(handle))
    return ft_create.value / 1e7 - 11644473600  # FILETIME (dal 1601) -> epoch Unix


_PY_START = time.time()

# DriverCore è già aperto: portalo davanti invece di aprirne un altro (e senza chiedere di nuovo l'UAC)
import single_instance  # noqa: E402
if not SELFTEST and single_instance.another_running():
    single_instance.request_focus()
    sys.exit(0)

try:
    if ctypes.windll.shell32.IsUserAnAdmin() == 0 and not SELFTEST:
        exe, args = app_command(windowed=False)
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe, " ".join(f'"{a}"' for a in args), str(BASE_DIR), 1
        )
        sys.exit(0)

    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd != 0:
        ctypes.windll.user32.ShowWindow(hwnd, 0)

    BASE_DIR.mkdir(parents=True, exist_ok=True)
    os.chdir(BASE_DIR)
    if not FROZEN and VENV_SITE.exists():  # nel .exe le librerie sono già incluse
        site.addsitedir(str(VENV_SITE))
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))

    import pythoncom
    from wmi_fast import FastWMI
    import wu_drivers
    import prefs
    import diagnostics
    import updater
    import ignore_list
    from ignore_list import load_ignored_updates
    import tkinter as tk
    import tkinter.font as tkfont
    from tkinter import filedialog, messagebox
    import customtkinter as ctk
    from PIL import Image, ImageChops, ImageDraw, ImageFilter

    import webbrowser
    from datetime import date as _date
    from i18n import LANG, LANGUAGES, configured_language, fmt_date, fmt_day_month, save_language, tr
    from driver_scanner import check_all_gpus, nvidia_info, console as ds_console
    from deep_catalog import (
        deep_scan_peripherals,
        install_catalog_cab_updates,
        scan_problem_devices,
        console as dc_console,
    )
    from driver_cleanup import (
        find_obsolete_driver_packages,
        remove_obsolete_driver_packages,
        dism_component_cleanup,
        console as cl_console,
    )
    from driver_installer import (
        backup_current_drivers,
        download_file,
        install_nvidia_driver,
        update_game_runtimes,
        create_system_restore_point,
        clean_gpu_shader_cache,
        enable_gpu_msi_mode,
        restore_driver_backup_folder,
        console as di_console,
    )
    from driver_history import load_history, snapshot_infs, undo_install, undo_plan, console as dh_console

    from auto_scan import get_frequency, last_result, mark_seen, next_run, set_frequency, summarize

    HISTORY_ROWS = 6  # ultime installazioni mostrate nella card Cronologia
    AUTO_LABELS = {"off": tr("Disattivato"), "daily": tr("Ogni giorno"), "weekly": tr("Ogni settimana")}
    LANG_LABELS = {"auto": tr("Automatica"), "it": "Italiano", "en": "English"}
    THEME_LABELS = {"auto": tr("Automatico"), "light": tr("Chiaro"), "dark": tr("Scuro")}
    # Messaggi di avanzamento mostrati come sottotitolo durante il lavoro (riconosciuti dalla parola iniziale)
    PROGRESS_WORDS = (tr("Controllo:"), tr("Avanzamento"), tr("Avvio"), tr("Pulizia"), tr("Creazione"), tr("Richiesta"))

    ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    # --- Stile: colori e movimento (vedi la tavola "Movimento e componenti") -------
    C_LIGHT = {
        "bg": "#F4F4F6", "surface": "#FFFFFF", "text": "#18181B", "text2": "#62626B",
        "muted": "#A1A1AA", "line": "#E6E6EA", "line_hover": "#D4D4DA", "hover": "#F0F0F3",
        "tile_hover": "#FBFBFC", "row_hover": "#FAFAFB",
        "accent": "#1F6FEB", "accent_hover": "#1A5FCC", "accent_soft": "#9DBDF5", "track": "#DCDCE2",
        "accent_ink": "#1A5FCC",  # testo blu: 4,5:1 anche sulle righe evidenziate
        "ok_bg": "#E6F4EA", "ok_ink": "#17703A", "warn_bg": "#FDF0E1", "warn_ink": "#9A4B00",
        "toast": "#1C1C1F", "toast_text2": "#C7C7CC", "seg_on": "#FFFFFF",
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

    def fmt_iso_date(raw: str) -> str:
        """'2025-07-09' -> '9 lug 2025' / 'Jul 9, 2025' (lascia invariato ciò che non riconosce)."""
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", raw or "")
        return fmt_date(_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))) if m else (raw or "")

    def fmt_when(d) -> str:
        """'9 nov 10:02' / 'Nov 9 10:02'."""
        return f"{fmt_day_month(d)} {d:%H:%M}"

    def verify_line(item: dict) -> tuple[str, str]:
        """(testo, colore) dell'esito della verifica del pacchetto."""
        if item.get("verified"):
            return tr("Verificato: Windows lo installerà.") + " " + item.get("verify_reason", ""), C["ok_ink"]
        return item.get("verify_reason") or tr("Non verificato."), C["text2"]


    class SmoothTimer:
        """Timer di Windows a 1 ms solo mentre almeno un'animazione è in corso.

        Con il timer predefinito (15,6 ms) Tk esegue after(16) ogni ~31 ms: le animazioni girano a 33 fps.
        A 1 ms arrivano a 60 fps; finita l'ultima animazione si torna al valore predefinito (nessun costo a riposo).
        """
        active = 0

        @classmethod
        def acquire(cls):
            if cls.active == 0:
                try:
                    ctypes.windll.winmm.timeBeginPeriod(1)
                except Exception:
                    pass
            cls.active += 1

        @classmethod
        def release(cls):
            if cls.active > 0:
                cls.active -= 1
                if cls.active == 0:
                    try:
                        ctypes.windll.winmm.timeEndPeriod(1)
                    except Exception:
                        pass

    FRAME_MS = 16

    class Tween:
        """Animazione a tempo reale (~60 fps): se un frame arriva in ritardo non rallenta, salta avanti."""

        def __init__(self, widget, duration_ms: int, step, easing=ease_out_quint, done=None):
            self.widget, self.duration, self.step, self.easing, self.done = widget, duration_ms, step, easing, done
            self._id = None
            self._held = False
            self.start = time.perf_counter()
            if not ANIMATE or duration_ms <= 0:
                self._finish()
            else:
                SmoothTimer.acquire()
                self._held = True
                self._tick()

        def _release(self):
            if self._held:
                self._held = False
                SmoothTimer.release()

        def _finish(self):
            try:
                self.step(1.0)
            except tk.TclError:
                return
            if self.done:
                self.done()

        def _tick(self):
            t = min(1.0, (time.perf_counter() - self.start) * 1000 / self.duration)
            try:
                self.step(self.easing(t))
            except tk.TclError:  # widget distrutto nel frattempo
                self._id = None
                self._release()
                return
            if t < 1.0:
                self._id = self.widget.after(FRAME_MS, self._tick)
            else:
                self._id = None
                self._release()
                if self.done:
                    self.done()

        def cancel(self):
            if self._id:
                try:
                    self.widget.after_cancel(self._id)
                except tk.TclError:
                    pass
                self._id = None
            self._release()

    def composited(win) -> None:
        """Disegno a doppio buffer di tutta la finestra (WS_EX_COMPOSITED).

        Senza, scorrendo Windows copia i pixel già disegnati (ScrollWindowEx) e poi ridisegna i singoli widget uno
        alla volta: per qualche frame si vedono righe stirate e testo "allungato". Con il doppio buffer ogni frame
        arriva sullo schermo completo.
        """
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetParent(win.winfo_id())
            get = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
            put = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            get.restype = put.restype = ctypes.c_ssize_t
            get.argtypes = (ctypes.wintypes.HWND, ctypes.c_int)
            put.argtypes = (ctypes.wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
            put(hwnd, -20, get(hwnd, -20) | 0x02000000)  # GWL_EXSTYLE |= WS_EX_COMPOSITED
        except Exception:
            pass

    class SmoothScrollFrame(ctk.CTkScrollableFrame):
        """Rotellina con scorrimento fluido: la pagina rallenta dolcemente verso il punto di arrivo (~60 fps)
        invece di saltare di 20 px a ogni scatto. Scatti ravvicinati si sommano, come su macOS."""
        STEP_PX = 96       # pixel per scatto della rotellina (120 di delta)
        FOLLOW = 0.22      # frazione della distanza residua percorsa in un frame da 16,7 ms

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._target = None
            self._pos = 0.0
            self._scroll_id = None
            self._last = 0.0

        def _content_height(self) -> float:
            region = str(self._parent_canvas.cget("scrollregion")).split()
            return float(region[3]) - float(region[1]) if len(region) == 4 else 0.0

        def _max_top(self) -> float:
            return max(0.0, self._content_height() - self._parent_canvas.winfo_height())

        def _mouse_wheel_all(self, event):
            if self._shift_pressed or not sys.platform.startswith("win") or not ANIMATE:
                return super()._mouse_wheel_all(event)
            if not self._check_if_valid_scroll(event.widget) or self._parent_canvas.yview() == (0.0, 1.0):
                return
            if self._scroll_id is None:  # parte da dove si trova ora (anche se spostata con la barra)
                self._pos = self._parent_canvas.canvasy(0)
                self._target = self._pos
            self._target = min(self._max_top(), max(0.0, self._target - event.delta / 120 * self.STEP_PX))
            if self._scroll_id is None:
                SmoothTimer.acquire()
                self._last = time.perf_counter()
                self._scroll_tick()

        def _scroll_tick(self):
            now = time.perf_counter()
            frames = max(1.0, (now - self._last) * 60)  # se un frame arriva tardi si recupera il ritardo
            self._last = now
            diff = self._target - self._pos
            if abs(diff) < 1.5:  # ultimo pixel e mezzo: si arriva subito invece di strisciare
                self._pos = self._target
            else:
                self._pos += diff * (1 - (1 - self.FOLLOW) ** frames)
            total = self._content_height()
            try:
                if total > 0:
                    self._parent_canvas.yview_moveto(round(self._pos) / total)
            except tk.TclError:
                self._pos = self._target
            if self._pos == self._target:
                self._scroll_id = None
                SmoothTimer.release()
            else:
                self._scroll_id = self.after(FRAME_MS, self._scroll_tick)

    class Switch(ctk.CTkLabel):
        """Interruttore disegnato con Pillow (bordi lisci) con pomello a molla."""
        W, H, S = 48, 28, 4  # dimensioni e fattore di sovracampionamento

        def __init__(self, master, value: bool, command):
            super().__init__(master, text="", width=self.W, height=self.H, fg_color="transparent")
            self.value, self.command = value, command
            self._pos = 1.0 if value else 0.0
            self._tween = None
            self._mask = Image.new("L", (self.W * self.S, self.H * self.S), 0)
            ImageDraw.Draw(self._mask).rounded_rectangle(
                (0, 0, self.W * self.S - 1, self.H * self.S - 1), radius=self.H * self.S // 2, fill=255)
            self._render(self._pos)
            self.bind("<Button-1>", self._click)
            tk.Label.configure(self._label, cursor="hand2")

        def _render(self, p: float):
            s, w, h = self.S, self.W * self.S, self.H * self.S
            img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            ImageDraw.Draw(img).rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2,
                                                  fill=mix(C["track"], C["accent"], p))
            knob, pad = 24 * s, 2 * s
            x = pad + 20 * s * p
            shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            ImageDraw.Draw(shadow).ellipse((x, pad + 2 * s, x + knob, pad + 2 * s + knob), fill=(0, 0, 0, 70))
            shadow = shadow.filter(ImageFilter.GaussianBlur(3 * s))
            shadow.putalpha(ImageChops.multiply(shadow.getchannel("A"), self._mask))
            img = Image.alpha_composite(img, shadow)
            ImageDraw.Draw(img).ellipse((x, pad, x + knob, pad + knob), fill="#FFFFFF")
            self._img = ctk.CTkImage(light_image=img, dark_image=img, size=(self.W, self.H))
            self.configure(image=self._img)

        def _click(self, _event=None):
            self.value = not self.value
            start, target = self._pos, (1.0 if self.value else 0.0)
            if self._tween:
                self._tween.cancel()

            def step(e):
                self._pos = start + (target - start) * e
                self._render(self._pos)

            self._tween = Tween(self, 320, step, ease_out_back)
            if self.command:
                self.command(self.value)

    class ScanBar(tk.Canvas):
        """Barra sottile indeterminata: un segmento scorre in ciclo continuo mentre si lavora."""

        def __init__(self, master, width: int = 420):
            super().__init__(master, width=width, height=7, bg=C["bg"], highlightthickness=0, bd=0)
            self.w = width
            self.track = self.create_line(3, 4, width - 3, 4, width=3, capstyle="round", fill=C["bg"])
            self.seg = self.create_line(-10, 4, -10, 4, width=3, capstyle="round", fill=C["bg"])
            self.running = False
            self._fade = None
            self._t0 = 0.0

        def _set_fade(self, p: float):
            self.itemconfigure(self.track, fill=mix(C["bg"], C["track"], p))
            self.itemconfigure(self.seg, fill=mix(C["bg"], C["accent"], p))

        def start(self):
            if self.running:
                return
            self.running = True
            SmoothTimer.acquire()
            self._t0 = time.perf_counter()
            if self._fade:
                self._fade.cancel()
            self._fade = Tween(self, 280, self._set_fade)
            self._loop()

        def stop(self):
            if self.running:
                SmoothTimer.release()
            self.running = False
            if self._fade:
                self._fade.cancel()
            self._fade = Tween(self, 280, lambda e: self._set_fade(1 - e))

        def _loop(self):
            if not self.running:
                return
            e = ease_in_out_cubic(((time.perf_counter() - self._t0) / 1.4) % 1.0)
            seg = self.w * 0.38
            x1 = -seg + e * (self.w + seg)
            a, b = max(3, x1), min(self.w - 3, x1 + seg)
            self.coords(self.seg, *((a, 4, b, 4) if b - a > 1 else (-10, 4, -10, 4)))
            self.after(FRAME_MS, self._loop)

    class ModernEventInterceptor:
        def __init__(self, app):
            self.app = app
            # Log con rotazione (1 MB x 3 file) e data/ora su ogni riga
            self.logger = logging.getLogger("drivercore")
            if not self.logger.handlers:
                handler = logging.handlers.RotatingFileHandler(
                    LOG_DIR / "session_activity.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
                )
                handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
                self.logger.addHandler(handler)
                self.logger.setLevel(logging.INFO)
                self.logger.propagate = False

        def write(self, text: str):
            clean = ANSI_ESCAPE.sub("", text).strip()
            if not clean:
                return

            for log_line in clean.splitlines():
                if log_line.strip():
                    try:
                        self.logger.info(log_line.rstrip())
                    except Exception:
                        pass

            for line in clean.splitlines():
                s = line.strip()
                if not s or s.startswith(("─", "│", "╭", "╰", "┏", "┗", "┌", "└", "===")):
                    continue

                if "✔" in s:
                    self._toast(tr("Completato"), s.replace("✔", "").strip(), "success")
                elif "✖" in s or "[ERRORE]" in s:
                    self._toast(tr("Errore"), s.replace("✖", "").replace("[ERRORE]", "").strip(), "error")
                elif s.startswith("!"):
                    self._toast(tr("Attenzione"), s.lstrip("!").strip(), "warning")
                elif any(k in s for k in PROGRESS_WORDS):
                    clean_sub = s.replace("[Pro Toolkit]", "").replace("[Deep Scan]", "").strip()
                    self.app.after(0, self.app.update_live_subtitle, clean_sub[:110])

        def _toast(self, default_title: str, msg: str, kind: str):
            # Messaggio breve: diventa il titolo; lungo: titolo generico + testo sotto
            if len(msg) <= 64:
                self.app.after(0, self.app.show_toast, msg, "", kind)
            else:
                self.app.after(0, self.app.show_toast, default_title, msg, kind)

        def flush(self):
            pass

    class DriverManagerGUI(ctk.CTk):
        def __init__(self):
            super().__init__()
            self.title("DriverCore")
            self._place_window(1180, 820)
            self.minsize(960, 640)
            self.configure(fg_color=C["bg"])
            if ANIMATE:
                self.attributes("-alpha", 0.0)

            self.nv_info = None
            self.gpus = []
            self.deep_updates = []
            self.checkbox_vars = []
            self.problem_devices = []
            self.problem_vars = []
            self.slim_mode = True
            self.clean_mode = False
            self.is_busy = False
            self.last_scan = None
            self.tiles = []
            self.undo_btns = []
            self._fonts = {}
            self._toast_tween = None
            self._toast_hide_id = None
            self._toast_visible = False
            self._toast_y = 0

            self._pick_fonts()
            self.grid_columnconfigure(0, weight=1)
            self.grid_rowconfigure(2, weight=1)
            self._build_header()
            self._build_body()
            self._build_toast()

            interceptor = ModernEventInterceptor(self)
            sys.stdout = interceptor
            sys.stderr = interceptor
            for _c in (ds_console, dc_console, di_console, cl_console, dh_console, wu_drivers.console):
                _c.file = interceptor
                _c.width = 400  # Rich andrebbe a capo a 80 colonne spezzando le righe nei log e nei toast

            dark_title_bar(self)
            composited(self)
            self.after(40, self._intro)
            self.run_in_background(self._task_full_scan, tr("Scansione in corso"))

        def _place_window(self, width: int, height: int):
            """Centra la finestra nell'area di lavoro (senza barra delle applicazioni), senza mai superarla.

            In geometry() customtkinter scala larghezza e altezza col DPI, ma non la posizione:
            quella è in pixel fisici, come l'area di lavoro.
            """
            scale = ctk.ScalingTracker.get_window_scaling(self)
            try:
                rect = ctypes.wintypes.RECT()
                ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
                left, top, area_w, area_h = rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
            except Exception:
                left, top = 0, 0
                area_w, area_h = self.winfo_screenwidth(), self.winfo_screenheight()
            title_bar = int(32 * scale)
            w = min(width, int((area_w - 40 * scale) / scale))
            h = min(height, int((area_h - title_bar - 24 * scale) / scale))
            x = left + max(0, (area_w - int(w * scale)) // 2)
            y = top + max(0, (area_h - int(h * scale) - title_bar) // 2)
            self.geometry(f"{w}x{h}+{x}+{y}")

        # --- Font ----------------------------------------------------------------
        def _pick_fonts(self):
            fam = set(tkfont.families(self))

            def first(*names):
                return next((n for n in names if n in fam), "Segoe UI")

            self.ff = {
                "regular": first("Segoe UI Variable Text", "Segoe UI"),
                "semibold": first("Segoe UI Variable Text Semibold", "Segoe UI Semibold"),
                "display": first("Segoe UI Variable Display", "Segoe UI"),
            }
            self.ff_icon = next((n for n in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if n in fam), None)

        def F(self, size: int, kind: str = "regular") -> ctk.CTkFont:
            key = (size, kind)
            if key not in self._fonts:
                if kind == "bold":
                    self._fonts[key] = ctk.CTkFont(family=self.ff["display"], size=size, weight="bold")
                elif kind == "icon":
                    self._fonts[key] = ctk.CTkFont(family=self.ff_icon or "Segoe UI", size=size)
                else:
                    self._fonts[key] = ctk.CTkFont(family=self.ff[kind], size=size)
            return self._fonts[key]

        def _label(self, parent, text="", size=14, kind="regular", color=None, **kw):
            return ctk.CTkLabel(parent, text=text, font=self.F(size, kind), text_color=color or C["text"],
                                anchor="w", justify="left", **kw)

        def _sep(self, parent):
            return ctk.CTkFrame(parent, height=1, fg_color=C["line"], corner_radius=0)

        def _card(self, parent):
            return ctk.CTkFrame(parent, fg_color=C["surface"], corner_radius=20, border_width=1, border_color=C["line"])

        # --- Struttura -----------------------------------------------------------
        def _build_header(self):
            bar = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
            bar.grid(row=0, column=0, sticky="ew")
            left = ctk.CTkFrame(bar, fg_color="transparent")
            left.pack(side="left", padx=(40, 0), pady=14)
            if self.ff_icon:
                self._label(left, GLYPH["app"], 18, "icon").pack(side="left", padx=(0, 10))
            self._label(left, "DriverCore", 15, "semibold").pack(side="left")

            self.btn_scan = ctk.CTkButton(
                bar, text=tr("Scansiona"), width=124, height=36, corner_radius=18,
                fg_color=C["accent"], hover_color=C["accent_hover"], text_color="#FFFFFF",
                text_color_disabled="#FFFFFF", font=self.F(14, "semibold"),
                command=lambda: self.run_in_background(self._task_full_scan, tr("Scansione in corso")),
            )
            self.btn_scan.pack(side="right", padx=(0, 40), pady=14)
            self._sep(self).grid(row=1, column=0, sticky="ew")

        def _build_body(self):
            self.body = SmoothScrollFrame(
                self, fg_color=C["bg"], corner_radius=0,
                scrollbar_button_color=C["line_hover"], scrollbar_button_hover_color=C["muted"],
            )
            self.body.grid(row=2, column=0, sticky="nsew")
            self.col = ctk.CTkFrame(self.body, fg_color="transparent")
            self.col.pack(fill="x", padx=40, pady=(72 if ANIMATE else 48, 96))

            self._build_hero(self.col)
            self._build_problem_card(self.col)  # compare solo se ci sono periferiche con problemi

            cards = ctk.CTkFrame(self.col, fg_color="transparent")
            cards.pack(fill="x", pady=(36, 0))
            self.cards_row = cards
            cards.grid_columnconfigure(0, weight=1, uniform="cards")
            cards.grid_columnconfigure(1, weight=2, uniform="cards")
            self._build_gpu_card(cards).grid(row=0, column=0, sticky="new", padx=(0, 10))
            self._build_peripherals_card(cards).grid(row=0, column=1, sticky="new", padx=(10, 0))

            self._build_auto_card(self.col)
            self._build_history_card(self.col)
            self._build_tools(self.col)

        def _build_hero(self, parent):
            hero = ctk.CTkFrame(parent, fg_color="transparent")
            hero.pack(fill="x")
            self.lbl_eyebrow = self._label(hero, tr("Avvio di DriverCore"), 13, "semibold", C["text2"])
            self.lbl_eyebrow.pack(anchor="w")
            self.lbl_title = self._label(hero, "", 34, "bold")
            self.lbl_title.pack(anchor="w", pady=(6, 0))
            self.lbl_sub = self._label(hero, "", 16, "regular", C["text2"], wraplength=680)
            self.lbl_sub.pack(anchor="w", pady=(6, 0))
            self.scanbar = ScanBar(hero, 420)
            self.scanbar.pack(anchor="w", pady=(16, 0))

        def _build_gpu_card(self, parent):
            card = self._card(parent)
            self.gpu_box = ctk.CTkFrame(card, fg_color="transparent")
            self.gpu_box.pack(fill="both", expand=True, padx=24, pady=24)
            self._label(self.gpu_box, tr("Schede video"), 13, "semibold", C["text2"]).pack(anchor="w")
            self.gpu_blocks = [self._label(self.gpu_box, tr("Rilevamento in corso…"), 20, "bold", wraplength=300)]
            self.gpu_blocks[0].pack(anchor="w", pady=(4, 0))

            # Opzioni e pulsante dell'aggiornamento NVIDIA: compaiono sotto il blocco della scheda NVIDIA
            self.nv_options = ctk.CTkFrame(self.gpu_box, fg_color="transparent")
            self._switch_row(self.nv_options, tr("Modalità SLIM"), tr("Solo driver, audio HDMI e PhysX. Niente telemetria."),
                             self.slim_mode, lambda v: setattr(self, "slim_mode", v), pady=(18, 0))
            self._switch_row(self.nv_options, tr("Installazione pulita"),
                             tr("Riporta le impostazioni del driver ai valori iniziali."),
                             self.clean_mode, lambda v: setattr(self, "clean_mode", v), pady=(14, 0))
            self.btn_gpu = ctk.CTkButton(
                self.nv_options, text=tr("Aggiorna GPU"), height=44, corner_radius=22,
                fg_color=C["hover"], hover_color=C["line"], text_color=C["text"],
                text_color_disabled=C["muted"], font=self.F(14, "semibold"), command=self._on_update_gpu,
            )
            self.btn_gpu.pack(fill="x", pady=(22, 0))
            return card

        def _gpu_block(self, gpu: dict, first: bool):
            """Una scheda video: nome, stato, versioni, nota e (per AMD/Intel) il link alla pagina ufficiale."""
            block = ctk.CTkFrame(self.gpu_box, fg_color="transparent")
            block.pack(fill="x", pady=(4 if first else 22, 0))
            if not first:
                self._sep(block).pack(fill="x", pady=(0, 18))

            top = ctk.CTkFrame(block, fg_color="transparent")
            top.pack(fill="x")
            top.grid_columnconfigure(0, weight=1)
            name = self._label(top, "", 20 if first else 17, "bold", wraplength=230)
            name.grid(row=0, column=0, sticky="w")
            if gpu["update"] is True:
                badge = (tr("Nuova versione"), C["warn_bg"], C["warn_ink"])
            elif gpu["update"] is False:
                badge = (tr("Aggiornato"), C["ok_bg"], C["ok_ink"])
            else:
                badge = (tr("Da verificare"), C["hover"], C["text2"])
            ctk.CTkLabel(top, text=f"   {badge[0]}   ", height=26, corner_radius=13, fg_color=badge[1],
                         text_color=badge[2], font=self.F(12, "semibold")).grid(row=0, column=1, sticky="ne", padx=(12, 0))
            self._fade_text(name, gpu["name"], C["text"], bg=C["surface"])

            rows = ctk.CTkFrame(block, fg_color="transparent")
            rows.pack(fill="x", pady=(14, 0))
            self._sep(rows).pack(fill="x")
            self._kv_row(rows, tr("Installato")).configure(text=gpu["local"] or "—")
            self._sep(rows).pack(fill="x")
            latest = gpu["remote"] or "—"
            if gpu["remote"] and gpu["date"]:
                latest = f"{gpu['remote']} · {fmt_iso_date(gpu['date'])}"
            self._kv_row(rows, tr("Ultima versione")).configure(text=latest)
            self._sep(rows).pack(fill="x")

            note = gpu["error"] or gpu["note"]
            if note:
                self._label(block, note, 13, "regular", C["text2"], wraplength=300).pack(anchor="w", pady=(10, 0))

            if gpu["vendor"] in ("amd", "intel") and gpu.get("page"):
                vendor = "AMD" if gpu["vendor"] == "amd" else "Intel"
                primary = gpu["update"] is True
                ctk.CTkButton(
                    block, text=tr("Scarica dal sito {vendor}", vendor=vendor) if primary else tr("Pagina driver {vendor}", vendor=vendor),
                    height=44, corner_radius=22, font=self.F(14, "semibold"),
                    fg_color=C["accent"] if primary else C["hover"],
                    hover_color=C["accent_hover"] if primary else C["line"],
                    text_color="#FFFFFF" if primary else C["text"],
                    command=lambda url=gpu["page"]: webbrowser.open(url),
                ).pack(fill="x", pady=(16, 0))
            return block

        def _kv_row(self, parent, key: str):
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", pady=11)
            self._label(row, key, 14, "regular", C["text2"]).pack(side="left")
            val = self._label(row, "—", 14, "semibold")
            val.pack(side="right")
            return val

        def _switch_row(self, parent, title: str, desc: str, value: bool, command, pady):
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", pady=pady)
            row.grid_columnconfigure(0, weight=1)
            self._label(row, title, 14, "semibold").grid(row=0, column=0, sticky="w")
            self._label(row, desc, 13, "regular", C["text2"], wraplength=220).grid(row=1, column=0, sticky="w")
            Switch(row, value, command).grid(row=0, column=1, rowspan=2, padx=(16, 0))

        def _build_peripherals_card(self, parent):
            card = self._card(parent)
            head = ctk.CTkFrame(card, fg_color="transparent")
            head.pack(fill="x", padx=24, pady=(22, 12))
            self._label(head, tr("Periferiche"), 20, "bold").pack(side="left")
            self._label(head, "Update Catalog · Windows Update", 13, "regular", C["text2"]).pack(side="right")

            # Margine in fondo: i figli non devono coprire gli angoli arrotondati della card
            ctk.CTkFrame(card, fg_color="transparent", height=10).pack(side="bottom", fill="x", padx=20)
            self.per_rows = ctk.CTkFrame(card, fg_color="transparent")
            self.per_rows.pack(fill="x", padx=2)

            self.per_footer = ctk.CTkFrame(card, fg_color="transparent")
            self._sep(self.per_footer).pack(fill="x")
            foot = ctk.CTkFrame(self.per_footer, fg_color="transparent")
            foot.pack(fill="x", padx=24, pady=(16, 12))
            self._label(foot, tr("Prima dell'installazione vengono creati un punto di ripristino e un backup dei driver."),
                        13, "regular", C["text2"], wraplength=360).pack(side="left", fill="x", expand=True)
            self.btn_install = ctk.CTkButton(
                foot, text=tr("Installa selezionati"), height=44, corner_radius=22,
                fg_color=C["accent"], hover_color=C["accent_hover"], text_color="#FFFFFF",
                text_color_disabled="#FFFFFF", font=self.F(14, "semibold"), command=self._on_install_selected,
            )
            self.btn_install.pack(side="right", padx=(16, 0))

            self._label(self.per_rows, tr("Ricerca degli aggiornamenti in corso…"), 14, "regular",
                        C["text2"]).pack(anchor="w", padx=24, pady=(4, 28))
            return card

        def _build_problem_card(self, parent):
            self.problem_card = self._card(parent)
            head = ctk.CTkFrame(self.problem_card, fg_color="transparent")
            head.pack(fill="x", padx=24, pady=(22, 12))
            if self.ff_icon:
                self._label(head, GLYPH["warning"], 18, "icon", C["warn_ink"]).pack(side="left", padx=(0, 10))
            self._label(head, tr("Periferiche con problemi"), 20, "bold").pack(side="left")
            self._label(head, tr("Da Gestione dispositivi"), 13, "regular", C["text2"]).pack(side="right")

            ctk.CTkFrame(self.problem_card, fg_color="transparent", height=10).pack(side="bottom", fill="x", padx=20)
            self.problem_rows = ctk.CTkFrame(self.problem_card, fg_color="transparent")
            self.problem_rows.pack(fill="x", padx=2)

            self.problem_footer = ctk.CTkFrame(self.problem_card, fg_color="transparent")
            self._sep(self.problem_footer).pack(fill="x")
            foot = ctk.CTkFrame(self.problem_footer, fg_color="transparent")
            foot.pack(fill="x", padx=24, pady=(16, 12))
            self._label(foot, tr("Prima dell'installazione vengono creati un punto di ripristino e un backup dei driver."),
                        13, "regular", C["text2"], wraplength=520).pack(side="left", fill="x", expand=True)
            self.btn_fix = ctk.CTkButton(
                foot, text=tr("Installa driver"), height=44, corner_radius=22,
                fg_color=C["accent"], hover_color=C["accent_hover"], text_color="#FFFFFF",
                text_color_disabled="#FFFFFF", font=self.F(14, "semibold"), command=self._on_install_problems,
            )
            self.btn_fix.pack(side="right", padx=(16, 0))

        def _update_problems_ui(self):
            for widget in self.problem_rows.winfo_children():
                widget.destroy()
            self.problem_vars.clear()
            if not self.problem_devices:
                self.problem_card.pack_forget()
                return

            for idx, dev in enumerate(self.problem_devices):
                self._problem_row(dev, delay=idx * 60)
            if self.problem_vars:
                self.problem_footer.pack(fill="x", padx=2)
            else:
                self.problem_footer.pack_forget()
            self.problem_card.pack(fill="x", pady=(36, 0), before=self.cards_row)
            self._refresh_install_btn()

        def _problem_row(self, dev: dict, delay: int):
            self._sep(self.problem_rows).pack(fill="x")
            row = ctk.CTkFrame(self.problem_rows, fg_color=C["surface"], corner_radius=0)
            row.pack(fill="x")
            row.grid_columnconfigure(1, weight=1)

            found = bool(dev.get("update_id"))
            # Contenitore a larghezza fissa: casella e pallino occupano lo stesso spazio, il testo resta allineato
            slot = ctk.CTkFrame(row, width=30, height=24, fg_color="transparent")
            slot.grid(row=0, column=0, rowspan=4, sticky="n", padx=(24, 6), pady=(16, 0))
            slot.grid_propagate(False)
            slot.pack_propagate(False)
            if found:
                var = ctk.BooleanVar(value=True)
                self.problem_vars.append((var, dev))
                ctk.CTkCheckBox(
                    slot, text="", variable=var, width=24, checkbox_width=22, checkbox_height=22, corner_radius=11,
                    border_width=2, border_color=C["muted"], fg_color=C["accent"], hover_color=C["accent_hover"],
                    checkmark_color="#FFFFFF", command=self._refresh_install_btn,
                ).place(x=0, y=0)
            else:
                # Segnala che per questa periferica non c'è nulla da installare
                ctk.CTkFrame(slot, width=22, height=22, corner_radius=11, fg_color=C["warn_bg"]).place(x=0, y=1)

            name = self._label(row, "", 15, "semibold")
            name.grid(row=0, column=1, sticky="w", padx=(0, 24), pady=(15, 0))
            problem = self._label(row, "", 13, "semibold")
            problem.grid(row=1, column=1, sticky="w", padx=(0, 24), pady=(2, 0))
            hwid = self._label(row, "", 12, "regular", wraplength=640)
            hwid.grid(row=2, column=1, sticky="w", padx=(0, 24), pady=(2, 0))

            if found:
                detail = tr("Driver trovato: {version} · {date}", version=dev["remote_ver"], date=fmt_iso_date(dev["remote_date"]))
                detail += " · verificato" if dev.get("verified") else tr(" · non verificato")
                detail_color = C["accent_ink"]
            elif dev.get("rejected_reason"):
                detail = tr("Il driver trovato non verrebbe applicato: {reason}", reason=dev["rejected_reason"])
                detail_color = C["text2"]
            elif dev.get("nvidia"):
                detail, detail_color = tr("Usa «Aggiorna GPU» nella card della scheda video."), C["text2"]
            elif dev.get("queries") and dev.get("lookup_ok") is False:
                detail, detail_color = tr("Ricerca non riuscita (rete o Catalog non raggiungibile): riprova la scansione."), C["text2"]
            elif dev.get("queries"):
                detail = tr("Nessun driver sul Microsoft Update Catalog: cerca l'ID sul sito del produttore.")
                detail_color = C["text2"]
            else:
                detail, detail_color = tr("Periferica software: prova a reinstallare il programma che l'ha creata."), C["text2"]

            last = ctk.CTkFrame(row, fg_color="transparent")
            last.grid(row=3, column=1, sticky="ew", padx=(0, 24), pady=(6, 14))
            info = self._label(last, "", 13, "semibold" if found else "regular", wraplength=560)
            info.pack(side="left")
            if not found and not dev.get("nvidia"):
                ctk.CTkButton(
                    last, text=tr("Copia ID"), width=88, height=30, corner_radius=15, fg_color=C["hover"],
                    hover_color=C["line"], text_color=C["text"], font=self.F(13, "semibold"),
                    command=lambda h=dev["hwid"]: self._copy_hwid(h),
                ).pack(side="right")

            fades = [
                (name, dev["name"], C["text"]),
                (problem, tr("{problem} (codice {code})", problem=dev["problem"], code=dev["code"]), C["warn_ink"]),
                (hwid, dev["hwid"], C["text2"]),
                (info, detail, detail_color),
            ]
            for lbl, text, color in fades:
                self._fade_text(lbl, text, color, ms=420, delay=delay + 40, bg=C["surface"])

            if found:
                def toggle(_e=None, v=var):
                    v.set(not v.get())
                    self._refresh_install_btn()
                for w in (row, name, problem, hwid, info):
                    w.bind("<Button-1>", toggle)
                tk.Frame.configure(row, cursor="hand2")

        # --- Controllo automatico -----------------------------------------------------
        def _build_auto_card(self, parent):
            card = self._card(parent)
            card.pack(fill="x", pady=(36, 0))
            box = ctk.CTkFrame(card, fg_color="transparent")
            box.pack(fill="x", padx=24, pady=22)
            box.grid_columnconfigure(0, weight=1)
            self._label(box, tr("Impostazioni"), 20, "bold").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 16))
            self._label(box, tr("Controllo automatico"), 15, "semibold").grid(row=1, column=0, sticky="w")
            self.lbl_auto = self._label(box, "", 13, "regular", C["text2"], wraplength=560)
            self.lbl_auto.grid(row=2, column=0, sticky="w", pady=(2, 0))
            self.seg_auto = ctk.CTkSegmentedButton(
                box, values=list(AUTO_LABELS.values()), height=36, corner_radius=18, font=self.F(13, "semibold"),
                fg_color=C["hover"], unselected_color=C["hover"], unselected_hover_color=C["line"],
                selected_color=C["seg_on"], selected_hover_color=C["seg_on"], text_color=C["text"],
                command=self._on_auto_change,
            )
            self.seg_auto.grid(row=1, column=1, rowspan=2, padx=(16, 0), sticky="e")
            self.auto_freq = get_frequency()
            self.seg_auto.set(AUTO_LABELS[self.auto_freq])
            self._refresh_auto_label()

            # Lingua: scritta in entrambe le lingue, così si ritrova anche se è quella sbagliata
            self._sep(box).grid(row=3, column=0, columnspan=2, sticky="ew", pady=18)
            self._label(box, "Lingua · Language", 15, "semibold").grid(row=4, column=0, sticky="w")
            self._label(box, tr("Vale dal prossimo avvio di DriverCore."), 13, "regular", C["text2"]).grid(
                row=5, column=0, sticky="w", pady=(2, 0))
            seg_lang = ctk.CTkSegmentedButton(
                box, values=list(LANG_LABELS.values()), height=36, corner_radius=18, font=self.F(13, "semibold"),
                fg_color=C["hover"], unselected_color=C["hover"], unselected_hover_color=C["line"],
                selected_color=C["seg_on"], selected_hover_color=C["seg_on"], text_color=C["text"],
                command=self._on_language_change,
            )
            seg_lang.grid(row=4, column=1, rowspan=2, padx=(16, 0), sticky="e")
            seg_lang.set(LANG_LABELS[configured_language()])

            # Tema
            self._sep(box).grid(row=6, column=0, columnspan=2, sticky="ew", pady=18)
            self._label(box, tr("Tema"), 15, "semibold").grid(row=7, column=0, sticky="w")
            self._label(box, tr("Automatico segue il tema delle app di Windows. Vale dal prossimo avvio."), 13,
                        "regular", C["text2"], wraplength=520).grid(row=8, column=0, sticky="w", pady=(2, 0))
            seg_theme = ctk.CTkSegmentedButton(
                box, values=list(THEME_LABELS.values()), height=36, corner_radius=18, font=self.F(13, "semibold"),
                fg_color=C["hover"], unselected_color=C["hover"], unselected_hover_color=C["line"],
                selected_color=C["seg_on"], selected_hover_color=C["seg_on"], text_color=C["text"],
                command=self._on_theme_change,
            )
            seg_theme.grid(row=7, column=1, rowspan=2, padx=(16, 0), sticky="e")
            seg_theme.set(THEME_LABELS[THEME])

            # Informazioni: versione, aggiornamenti di DriverCore, diagnostica
            self._sep(box).grid(row=9, column=0, columnspan=2, sticky="ew", pady=18)
            self._label(box, f"DriverCore {APP_VERSION}", 15, "semibold").grid(row=10, column=0, sticky="w")
            self.lbl_update = self._label(box, "", 13, "regular", C["text2"], wraplength=520)
            self.lbl_update.grid(row=11, column=0, sticky="w", pady=(2, 0))
            actions = ctk.CTkFrame(box, fg_color="transparent")
            actions.grid(row=10, column=1, rowspan=2, padx=(16, 0), sticky="e")
            self.btn_diag = ctk.CTkButton(
                actions, text=tr("Esporta diagnostica"), height=36, corner_radius=18, fg_color=C["hover"],
                hover_color=C["line"], text_color=C["text"], font=self.F(13, "semibold"), command=self._on_export_diag,
            )
            self.btn_diag.pack(side="left")
            self.btn_update = ctk.CTkButton(
                actions, text=tr("Cerca aggiornamenti"), height=36, corner_radius=18, fg_color=C["hover"],
                hover_color=C["line"], text_color=C["text"], text_color_disabled=C["muted"],
                font=self.F(13, "semibold"), command=self._on_check_update,
            )
            self.btn_update.pack(side="left", padx=(8, 0))
            self.update_info = None
            if not updater.configured():
                self.lbl_update.configure(text=tr("Aggiornamenti automatici non configurati."))
                self.btn_update.configure(state="disabled")
            else:
                self.lbl_update.configure(text=tr("Controlla una volta al giorno se c'è una nuova versione."))
                if updater.due(prefs.get("update_checked")):
                    self.after(4000, lambda: self._check_update(quiet=True))

        def _on_theme_change(self, label: str):
            value = next(k for k, v in THEME_LABELS.items() if v == label)
            try:
                prefs.set_value("theme", value)
            except OSError as e:
                self.show_toast(tr("Impostazione non salvata"), str(e), "error")
                return
            self.show_toast(tr("Tema salvato"), tr("Riavvia DriverCore per applicarlo."), "success")

        # --- Diagnostica e aggiornamenti di DriverCore -------------------------------
        def _on_export_diag(self):
            if self.is_busy:
                return
            target = filedialog.asksaveasfilename(
                title=tr("Esporta diagnostica"), defaultextension=".zip", initialfile=diagnostics.default_name(),
                initialdir=str(Path.home() / "Desktop"), filetypes=[("Zip", "*.zip")],
            )
            if not target:
                return

            def task():
                path = diagnostics.export(Path(target), FastWMI())
                print("✔ " + tr("Diagnostica salvata in {path}", path=path))
            self.run_in_background(task, tr("Esportazione della diagnostica"))

        def _on_check_update(self):
            self._check_update(quiet=False)

        def _check_update(self, quiet: bool):
            """Controllo in background; con quiet=True (all'avvio) avvisa solo se c'è una versione nuova."""
            if self.update_info:  # già trovata: installa
                return self._install_update()
            self.btn_update.configure(state="disabled")

            def work():
                try:
                    info, err = updater.check(), None
                except Exception as e:  # rete, manifest non valido...
                    info, err = None, e
                try:
                    prefs.set_value("update_checked", time.time())
                except OSError:
                    pass
                self.after(0, lambda: self._show_update(info, err, quiet))
            threading.Thread(target=work, daemon=True).start()

        def _show_update(self, info, err, quiet: bool):
            self.btn_update.configure(state="normal")
            if err is not None:
                self.lbl_update.configure(text=tr("Controllo non riuscito: {error}", error=err))
                if not quiet:
                    self.show_toast(tr("Controllo non riuscito"), str(err), "warning")
                return
            if not info:
                self.lbl_update.configure(text=tr("Hai l'ultima versione."))
                if not quiet:
                    self.show_toast(tr("Hai l'ultima versione."), "", "success")
                return
            self.update_info = info
            self.lbl_update.configure(text=tr("Disponibile la versione {version}.", version=info["version"])
                                      + (f" {info['notes']}" if info["notes"] else ""))
            self.btn_update.configure(text=tr("Installa {version}", version=info["version"]), fg_color=C["accent"],
                                      hover_color=C["accent_hover"], text_color="#FFFFFF")
            self.show_toast(tr("Nuova versione di DriverCore"), tr("Disponibile la versione {version}.",
                                                                  version=info["version"]), "info")

        def _install_update(self):
            info = self.update_info
            if self.is_busy or not info:
                return
            if not FROZEN:
                self.show_toast(tr("Aggiornamento non disponibile"),
                                tr("l'aggiornamento automatico funziona solo con DriverCore.exe"), "warning")
                return
            if not messagebox.askyesno(
                tr("Aggiorna DriverCore"),
                tr("Verrà scaricata e installata la versione {version}.\nDriverCore si chiuderà e si riaprirà da solo.\n\n"
                   "Procedere?", version=info["version"])
            ):
                return

            def task():
                new_exe = updater.download(info)
                updater.apply_and_restart(new_exe)
                self.after(300, self.destroy)  # lo script sostituisce il file appena il programma si chiude
            self.run_in_background(task, tr("Aggiornamento di DriverCore"))

        def _on_language_change(self, label: str):
            value = next(k for k, v in LANG_LABELS.items() if v == label)
            try:
                save_language(value)
            except OSError as e:
                self.show_toast(tr("Impostazione non salvata"), str(e), "error")
                return
            self.show_toast(tr("Lingua salvata"), tr("Riavvia DriverCore per applicarla."), "success")

        def _refresh_auto_label(self):
            """Testo di stato; la prossima esecuzione si legge dall'Utilità di pianificazione senza bloccare la UI."""
            last = last_result()
            seen = ""
            if last.get("time"):
                t = datetime.fromisoformat(last["time"])
                n = len(last.get("items", []))
                seen = tr("Ultimo controllo {when}:", when=fmt_when(t)) + " " + \
                       (tr("nessuna novità.") if n == 0 else tr("{count} novità.", count=n))
            if self.auto_freq == "off":
                self.lbl_auto.configure(text=tr("Disattivato. Se lo attivi, DriverCore controlla i driver anche a finestra "
                                             "chiusa e ti avvisa con una notifica. Non installa mai nulla da solo."))
                return
            self.lbl_auto.configure(text=tr("Attivo: ti avvisa con una notifica quando c'è un driver nuovo.") + f" {seen}")

            def read():
                nxt = next_run()
                if nxt:
                    text = tr("Prossimo controllo {day} alle {time}.", day=fmt_day_month(nxt), time=f"{nxt:%H:%M}") + f" {seen}"
                    self.after(0, lambda: self.auto_freq != "off" and self.lbl_auto.configure(text=text))
            threading.Thread(target=read, daemon=True).start()

        def _on_auto_change(self, label: str):
            freq = next(k for k, v in AUTO_LABELS.items() if v == label)
            if freq == self.auto_freq:
                return
            if self.is_busy:
                self.seg_auto.set(AUTO_LABELS[self.auto_freq])
                self.show_toast(tr("Attendi"), tr("Un'altra operazione è in corso."), "warning")
                return

            def task():
                ok, err = set_frequency(freq)
                if ok:
                    self.auto_freq = freq
                    print(tr("Controllo automatico disattivato") if freq == "off" else tr("Controllo automatico attivato"))
                else:
                    print("✖ " + tr("Controllo automatico non modificato: {error}", error=err))
                self.after(0, lambda: (self.seg_auto.set(AUTO_LABELS[self.auto_freq]), self._refresh_auto_label()))
            self.run_in_background(task, tr("Controllo automatico"))

        # --- Cronologia --------------------------------------------------------------
        def _build_history_card(self, parent):
            card = self._card(parent)
            card.pack(fill="x", pady=(36, 0))
            head = ctk.CTkFrame(card, fg_color="transparent")
            head.pack(fill="x", padx=24, pady=(22, 12))
            if self.ff_icon:
                self._label(head, GLYPH["history"], 18, "icon", C["accent_ink"]).pack(side="left", padx=(0, 10))
            self._label(head, tr("Cronologia"), 20, "bold").pack(side="left")
            self._label(head, tr("Ogni aggiornamento si può annullare"), 13, "regular", C["text2"]).pack(side="right")
            ctk.CTkFrame(card, fg_color="transparent", height=10).pack(side="bottom", fill="x", padx=20)
            self.history_rows = ctk.CTkFrame(card, fg_color="transparent")
            self.history_rows.pack(fill="x", padx=2)
            self._update_history_ui()

        def _update_history_ui(self):
            for w in self.history_rows.winfo_children():
                w.destroy()
            self.undo_btns = []
            entries = list(reversed(load_history()))[:HISTORY_ROWS]
            if not entries:
                self._label(self.history_rows, tr("I driver installati da DriverCore compariranno qui."), 14, "regular",
                            C["text2"]).pack(anchor="w", padx=24, pady=(4, 28))
                return
            for e in entries:
                self._history_row(e)

        def _history_row(self, e: dict):
            self._sep(self.history_rows).pack(fill="x")
            row = ctk.CTkFrame(self.history_rows, fg_color="transparent")
            row.pack(fill="x", padx=22, pady=12)
            row.grid_columnconfigure(0, weight=1)
            self._label(row, e["name"], 14, "semibold").grid(row=0, column=0, sticky="w")
            when = datetime.fromisoformat(e["time"])
            change = f"{e['old_ver'] or tr('nessun driver')}  ➔  {e['new_ver']}"
            self._label(row, f"{change}  ·  {fmt_when(when)}", 13, "regular",
                        C["text2"]).grid(row=1, column=0, sticky="w")
            if e["status"] == "undone":
                ctk.CTkLabel(row, text=f"   {tr('Annullato')}   ", height=26, corner_radius=13, fg_color=C["hover"],
                             text_color=C["text2"], font=self.F(12, "semibold")).grid(row=0, column=1, rowspan=2)
                return
            btn = ctk.CTkButton(
                row, text=tr("Riprova") if e["status"] == "partial" else tr("Annulla"), width=96, height=34,
                corner_radius=17, fg_color=C["hover"], hover_color=C["line"], text_color=C["text"],
                text_color_disabled=C["muted"], font=self.F(13, "semibold"),
                state="disabled" if self.is_busy else "normal",
                command=lambda entry=e: self._on_undo(entry),
            )
            btn.grid(row=0, column=1, rowspan=2)
            self.undo_btns.append(btn)

        def _on_undo(self, entry: dict):
            if self.is_busy:
                return
            plan = undo_plan(entry, load_history(), snapshot_infs())
            if not plan["ok"]:
                self.show_toast(tr("Non si può annullare"), plan["reason"], "warning")
                return
            notes = "".join(f"\n• {w}" for w in plan["warnings"])
            target = entry["old_ver"] or tr("il driver precedente")
            if not messagebox.askyesno(
                tr("Annulla aggiornamento"),
                f"{entry['name']}\n{entry['new_ver']}  ➔  {target}\n\n"
                + tr("Il pacchetto installato viene tolto e Windows torna al driver precedente.")
                + f"{notes}\n\n" + tr("Prima verranno creati un punto di ripristino e un backup dei driver. Procedere?")
            ):
                return
            self.run_in_background(lambda: self._task_undo(entry["id"]), tr("Annullamento dell'aggiornamento"))

        def _task_undo(self, entry_id: str):
            create_system_restore_point("DriverCore Pre-Rollback")  # non bloccante
            if not backup_current_drivers():
                print(tr("✖ Backup driver non riuscito: annullamento interrotto."))
                return
            undo_install(entry_id)
            self._task_full_scan()

        # --- Aggiornamenti ignorati ------------------------------------------------------
        def _ignore_menu(self, anchor, item: dict):
            if self.is_busy:
                return
            menu = tk.Menu(self, tearoff=0, font=(self.ff["regular"], 10), bg=C["surface"], fg=C["text"],
                           activebackground=C["hover"], activeforeground=C["text"], bd=0)
            menu.add_command(label=tr("Ignora questa versione ({version})", version=item["remote_ver"]),
                             command=lambda: self._ignore(item, "version"))
            menu.add_command(label=tr("Ignora sempre questa periferica"), command=lambda: self._ignore(item, "device"))
            menu.tk_popup(anchor.winfo_rootx(), anchor.winfo_rooty() + anchor.winfo_height())

        def _ignore(self, item: dict, scope: str):
            entry = ignore_list.add_ignored(ignore_list.keys_for(item, scope), name=item["name"],
                                            version=item["remote_ver"] if scope == "version" else "", scope=scope)
            if entry is None:
                self.show_toast(tr("Impostazione non salvata"), "", "error")
                return
            self.deep_updates = [u for u in self.deep_updates if u is not item]
            self._update_peripherals_ui()
            self._refresh_hero()
            self.show_toast(tr("{name} ignorato", name=item["name"]),
                            tr("Lo ritrovi in Strumenti › Aggiornamenti ignorati."), "info")

        def _open_ignored(self):
            if self.is_busy:
                return
            win = ctk.CTkToplevel(self, fg_color=C["bg"])
            win.title(tr("Aggiornamenti ignorati"))
            win.geometry("620x520")
            win.transient(self)
            win.after(10, lambda: (dark_title_bar(win), composited(win)))
            win.after(50, win.grab_set)  # finestra modale: subito dopo la creazione su Windows
            self._label(win, tr("Aggiornamenti ignorati"), 20, "bold").pack(anchor="w", padx=28, pady=(24, 2))
            self._label(win, tr("Ripristina una voce per vederla di nuovo alla prossima scansione."), 13, "regular",
                        C["text2"]).pack(anchor="w", padx=28)
            box = SmoothScrollFrame(win, fg_color=C["surface"], corner_radius=16, border_width=1,
                                         border_color=C["line"], scrollbar_button_color=C["line_hover"])
            box.pack(fill="both", expand=True, padx=24, pady=(16, 24))
            self._fill_ignored(box)

        def _fill_ignored(self, box):
            for w in box.winfo_children():
                w.destroy()
            entries = list(reversed(ignore_list.load_entries()))
            if not entries:
                self._label(box, tr("Nessun aggiornamento ignorato."), 14, "regular", C["text2"]).pack(
                    anchor="w", padx=16, pady=16)
                return
            for n, e in enumerate(entries):
                if n:
                    self._sep(box).pack(fill="x", padx=8)
                row = ctk.CTkFrame(box, fg_color="transparent")
                row.pack(fill="x", padx=8, pady=10)
                row.grid_columnconfigure(0, weight=1)
                if e["scope"] == "device":
                    what = tr("Tutte le versioni")
                elif e["scope"] == "version":
                    what = tr("Versione {version}", version=e["version"])
                else:
                    what = tr("Rifiutato da Windows") + (f" · {e['version']}" if e.get("version") else "")
                title = e.get("name") or tr("Aggiornamenti rifiutati da Windows ({count})", count=len(e["keys"]))
                when = f"  ·  {fmt_when(datetime.fromisoformat(e['time']))}" if e.get("time") else ""
                self._label(row, title, 14, "semibold", wraplength=420).grid(row=0, column=0, sticky="w")
                self._label(row, what + when, 12, "regular", C["text2"]).grid(row=1, column=0, sticky="w")
                ctk.CTkButton(
                    row, text=tr("Ripristina"), width=96, height=32, corner_radius=16, fg_color=C["hover"],
                    hover_color=C["line"], text_color=C["text"], font=self.F(13, "semibold"),
                    command=lambda i=e["id"]: self._restore_ignored(box, i),
                ).grid(row=0, column=1, rowspan=2, padx=(12, 0))

        def _restore_ignored(self, box, entry_id: str):
            try:
                ignore_list.remove_entry(entry_id)
            except OSError as e:
                self.show_toast(tr("Impostazione non salvata"), str(e), "error")
                return
            self._fill_ignored(box)
            self.show_toast(tr("Ripristinato"), tr("Sarà di nuovo proposto alla prossima scansione."), "success")

        def _copy_hwid(self, hwid: str):
            self.clipboard_clear()
            self.clipboard_append(hwid)
            self.show_toast(tr("ID hardware copiato"), hwid, "info")

        def _build_tools(self, parent):
            self._label(parent, tr("Strumenti"), 20, "bold").pack(anchor="w", pady=(40, 14))
            grid = ctk.CTkFrame(parent, fg_color="transparent")
            grid.pack(fill="x")
            for c in range(4):
                grid.grid_columnconfigure(c, weight=1, uniform="tiles")

            tools = [
                ("backup", tr("Backup driver"), tr("Esporta tutti i driver di terze parti"),
                 lambda: self.run_in_background(backup_current_drivers, tr("Backup dei driver"))),
                ("shield", tr("Punto di ripristino"), tr("Crea un checkpoint di Windows"),
                 lambda: self.run_in_background(create_system_restore_point, tr("Creazione punto di ripristino"))),
                ("history", tr("Ripristina backup"), tr("Reinstalla da una cartella di backup"), self._select_and_restore_backup),
                ("delete", tr("Pulisci DriverStore"), tr("Rimuove i pacchetti driver obsoleti"),
                 lambda: self.run_in_background(self._task_cleanup_driverstore, tr("Pulizia del DriverStore"))),
                ("package", tr("Runtime di gioco"), tr("Visual C++ e .NET tramite winget"),
                 lambda: self.run_in_background(update_game_runtimes, tr("Aggiornamento dei runtime"))),
                ("palette", tr("Cache shader"), tr("Svuota DXCache, GLCache e D3DSCache"),
                 lambda: self.run_in_background(clean_gpu_shader_cache, tr("Pulizia della cache shader"))),
                ("hide", tr("Aggiornamenti ignorati"), tr("Versioni e periferiche nascoste"), self._open_ignored),
                ("bolt", tr("Modalità MSI"), tr("Interrupt a bassa latenza per la GPU"),
                 lambda: self.run_in_background(self._task_msi_mode, tr("Modalità MSI"))),
            ]
            for i, (glyph, title, desc, cmd) in enumerate(tools):
                self._tile(grid, glyph, title, desc, cmd).grid(row=i // 4, column=i % 4, sticky="nsew", padx=6, pady=6)

        def _tile(self, parent, glyph: str, title: str, desc: str, command):
            f = ctk.CTkFrame(parent, fg_color=C["surface"], corner_radius=16, border_width=1, border_color=C["line"])
            tk.Frame.configure(f, cursor="hand2")
            widgets = [f]
            icon = None
            if self.ff_icon:
                icon = self._label(f, GLYPH[glyph], 20, "icon", C["accent_ink"])
                icon.pack(anchor="w", padx=18, pady=(18, 0))
                widgets.append(icon)
            t = self._label(f, title, 15, "semibold")
            t.pack(anchor="w", padx=18, pady=(12 if icon else 18, 0))
            d = self._label(f, desc, 13, "regular", C["text2"], wraplength=190)
            d.pack(anchor="w", padx=18, pady=(2, 18))
            widgets += [t, d]
            self.tiles.append((t, d, icon))

            def on_enter(_e):
                self._hover(f, 1.0, C["surface"], C["tile_hover"], border=True)

            def on_leave(_e):
                if not self._pointer_inside(f):
                    self._hover(f, 0.0, C["surface"], C["tile_hover"], border=True)

            def on_press(_e):
                if not self.is_busy:
                    f.configure(fg_color=C["hover"])

            def on_release(_e):
                f.configure(fg_color=C["tile_hover"] if self._pointer_inside(f) else C["surface"])
                if self._pointer_inside(f) and not self.is_busy:
                    command()

            for w in widgets:
                w.bind("<Enter>", on_enter)
                w.bind("<Leave>", on_leave)
                w.bind("<ButtonPress-1>", on_press)
                w.bind("<ButtonRelease-1>", on_release)
            return f

        def _pointer_inside(self, widget) -> bool:
            w = self.winfo_containing(*self.winfo_pointerxy())
            while w is not None:
                if w is widget:
                    return True
                w = w.master
            return False

        def _hover(self, frame, target: float, c_from: str, c_to: str, border: bool = False):
            """Transizione morbida di colore (180 ms) per riquadri e righe."""
            cur = getattr(frame, "_hp", 0.0)
            tw = getattr(frame, "_htw", None)
            if tw:
                tw.cancel()

            def step(e):
                p = cur + (target - cur) * e
                frame._hp = p
                opts = {"fg_color": mix(c_from, c_to, p)}
                if border:
                    opts["border_color"] = mix(C["line"], C["line_hover"], p)
                frame.configure(**opts)

            frame._htw = Tween(self, 180, step)

        def _fade_text(self, label, text: str, color: str, ms: int = 320, delay: int = 0, bg: str = None):
            """Cambia il testo con una dissolvenza in entrata del colore."""
            if label.cget("text") == text and delay == 0:
                label.configure(text_color=color)
                return
            start = bg or C["bg"]
            label.configure(text=text, text_color=start)

            def run():
                Tween(self, ms, lambda e: label.configure(text_color=mix(start, color, e)))

            self.after(delay, run) if delay else run()

        # --- Notifiche -----------------------------------------------------------
        def _build_toast(self):
            self.toast = ctk.CTkFrame(self, corner_radius=20, fg_color=C["toast"], bg_color=C["bg"])
            self.toast_dot = ctk.CTkFrame(self.toast, width=10, height=10, corner_radius=5, fg_color=TOAST_DOTS["info"])
            self.toast_dot.grid(row=0, column=0, rowspan=2, padx=(18, 12))
            self.toast_title = ctk.CTkLabel(self.toast, text="", font=self.F(14, "semibold"), text_color="#FFFFFF",
                                            anchor="w", justify="left", wraplength=460)
            self.toast_title.grid(row=0, column=1, sticky="w", padx=(0, 22), pady=(14, 14))
            self.toast_msg = ctk.CTkLabel(self.toast, text="", font=self.F(13), text_color=C["toast_text2"],
                                          anchor="w", justify="left", wraplength=460)
            for w in (self.toast, self.toast_dot, self.toast_title, self.toast_msg):
                w.bind("<Button-1>", self._hide_toast)

        def _place_toast(self, y: float):
            self._toast_y = y
            tk.Frame.place(self.toast, relx=0.5, rely=1.0, anchor="n", y=int(y))

        def show_toast(self, title: str, message: str = "", kind: str = "success"):
            """Notifica in basso al centro: entra con un leggero rimbalzo, esce dopo qualche secondo o al clic."""
            msg = message if len(message) <= 220 else message[:217] + "…"
            self.toast_title.configure(text=title)
            self.toast_dot.configure(fg_color=TOAST_DOTS.get(kind, TOAST_DOTS["info"]))
            if msg:
                self.toast_msg.configure(text=msg)
                self.toast_title.grid_configure(pady=(14, 0))
                self.toast_msg.grid(row=1, column=1, sticky="w", padx=(0, 22), pady=(2, 14))
            else:
                self.toast_title.grid_configure(pady=(14, 14))
                self.toast_msg.grid_remove()

            if self._toast_tween:
                self._toast_tween.cancel()
            if self._toast_hide_id:
                self.after_cancel(self._toast_hide_id)
                self._toast_hide_id = None

            self.toast.update_idletasks()
            scale = ctk.ScalingTracker.get_widget_scaling(self)
            target = -(self.toast.winfo_reqheight() + 28 * scale)
            start = target + 14 * scale if self._toast_visible else 8
            self._toast_visible = True
            self._place_toast(start)
            self.toast.lift()
            self._toast_tween = Tween(self, 620, lambda e: self._place_toast(start + (target - start) * e), ease_out_back)

            duration = min(9000, 3400 + max(0, len(title) + len(msg) - 70) * 40)
            self._toast_hide_id = self.after(duration, self._hide_toast)

        def _hide_toast(self, _event=None):
            if not self._toast_visible:
                return
            if self._toast_hide_id:
                self.after_cancel(self._toast_hide_id)
                self._toast_hide_id = None
            if self._toast_tween:
                self._toast_tween.cancel()
            start = self._toast_y

            def done():
                self._toast_visible = False
                tk.Frame.place_forget(self.toast)

            self._toast_tween = Tween(self, 240, lambda e: self._place_toast(start + (8 - start) * e), ease_in_cubic, done)

        # --- Stato ---------------------------------------------------------------
        def _intro(self):
            """Apertura: la finestra si dissolve in entrata e il contenuto sale di poco."""
            def step(e):
                self.attributes("-alpha", e)
                self.col.pack_configure(pady=(int(72 - 24 * e), 96))

            # Rete di sicurezza: la finestra non deve mai restare invisibile
            self.after(1500, lambda: self.attributes("-alpha", 1.0))
            Tween(self, 560, step)

        def update_live_subtitle(self, text: str):
            if self.is_busy:
                self.lbl_sub.configure(text=text, text_color=C["text2"])

        def _refresh_hero(self):
            gpu_new = [g for g in self.gpus if g["update"] is True]
            n = len(self.deep_updates) + len(gpu_new)
            n_prob = len(self.problem_devices)
            fixable = sum(1 for d in self.problem_devices if d.get("update_id"))
            if n_prob:
                title = tr("1 periferica con problemi") if n_prob == 1 else tr("{count} periferiche con problemi", count=n_prob)
            elif n == 0:
                title = tr("Tutto aggiornato")
            elif n == 1:
                title = tr("1 aggiornamento disponibile")
            else:
                title = tr("{count} aggiornamenti disponibili", count=n)

            if not self.gpus:
                gpu = tr("Nessuna scheda video NVIDIA, AMD o Intel rilevata.")
            elif len(gpu_new) == 1:
                g = gpu_new[0]
                gpu = (tr("È disponibile il driver {version} per {name}.", version=g["remote"], name=g["name"])
                       if g["remote"] else f"{g['name']}: {g['note']}")
            elif gpu_new:
                gpu = tr("{count} schede video hanno un driver nuovo.", count=len(gpu_new))
            elif any(g["update"] is None for g in self.gpus):
                gpu = tr("Per una scheda video il controllo non è stato possibile.")
            else:
                gpu = tr("La scheda video è aggiornata.") if len(self.gpus) == 1 else tr("Le schede video sono aggiornate.")
            k = len(self.deep_updates)
            per = (tr("Tutte le periferiche hanno l'ultimo driver WHQL.") if k == 0 else
                   tr("Una periferica ha un driver più recente disponibile.") if k == 1 else
                   tr("{count} periferiche hanno un driver più recente disponibile.", count=k))

            if n_prob:
                prob = (tr("Nessuna ha un driver sul Microsoft Update Catalog.") if fixable == 0 else
                        tr("Per una c'è un driver da installare.") if fixable == 1 else
                        tr("Per {count} c'è un driver da installare.", count=fixable))
                upd = "" if n == 0 else (tr(" C'è anche 1 aggiornamento disponibile.") if n == 1
                                         else " " + tr("Ci sono anche {count} aggiornamenti disponibili.", count=n))
                sub = prob + upd
            else:
                sub = f"{gpu} {per}"

            eyebrow = (tr("Ultima scansione · oggi alle {time}", time=f"{self.last_scan:%H:%M}") if self.last_scan
                       else tr("Nessuna scansione completata"))
            self._fade_text(self.lbl_eyebrow, eyebrow, C["text2"])
            self._fade_text(self.lbl_title, title, C["text"])
            self._fade_text(self.lbl_sub, sub, C["text2"])

        def _set_busy(self, busy: bool, title: str = tr("Operazione in corso")):
            self.is_busy = busy
            state = "disabled" if busy else "normal"
            self.btn_scan.configure(state=state, fg_color=C["accent_soft"] if busy else C["accent"],
                                    text=tr("Scansione…") if busy and title == tr("Scansione in corso") else tr("Scansiona"))
            self.btn_gpu.configure(state=state)
            for t, d, icon in self.tiles:
                t.configure(text_color=C["muted"] if busy else C["text"])
                if icon:
                    icon.configure(text_color=C["muted"] if busy else C["accent_ink"])
            for b in self.undo_btns:
                b.configure(state=state)
            if busy:
                self.btn_install.configure(state="disabled", fg_color=C["accent_soft"])
                self.btn_fix.configure(state="disabled", fg_color=C["accent_soft"])
                self.scanbar.start()
                self._fade_text(self.lbl_title, title, C["text"])
                self.lbl_sub.configure(text=tr("Un momento…"), text_color=C["text2"])
            else:
                self._update_history_ui()  # un'installazione o un annullamento può averla cambiata
                self._refresh_install_btn()
                self.scanbar.stop()
                self._refresh_hero()

        def run_in_background(self, target_func, title: str = tr("Operazione in corso")):
            if self.is_busy:
                return
            # Impostato subito nel thread UI: due click ravvicinati non avviano due operazioni
            self.is_busy = True
            self._set_busy(True, title)

            def wrapper():
                pythoncom.CoInitialize()
                try:
                    target_func()
                except Exception as e:
                    self.after(0, self.show_toast, tr("Errore"), str(e), "error")
                finally:
                    pythoncom.CoUninitialize()
                    self.after(0, self._set_busy, False)

            threading.Thread(target=wrapper, daemon=True).start()

        # --- Aggiornamento delle viste -------------------------------------------
        def _update_gpus_ui(self):
            for w in self.gpu_blocks:
                w.destroy()
            self.nv_options.pack_forget()
            self.gpu_blocks = []

            if not self.gpus:
                lbl = self._label(self.gpu_box, "", 17, "bold", wraplength=300)
                lbl.pack(anchor="w", pady=(4, 0))
                self._fade_text(lbl, tr("Nessuna scheda NVIDIA, AMD o Intel rilevata"), C["text"], bg=C["surface"])
                self.gpu_blocks.append(lbl)
                return

            for i, gpu in enumerate(self.gpus):
                self.gpu_blocks.append(self._gpu_block(gpu, first=(i == 0)))
                if gpu["vendor"] == "nvidia" and gpu["can_install"] and not self.nv_options.winfo_manager():
                    self.nv_options.pack(fill="x")  # subito sotto la scheda NVIDIA

            nv = self.nv_info
            if nv:
                if nv["update"]:
                    self.btn_gpu.configure(text=tr("Aggiorna a {version}", version=nv["remote"]), fg_color=C["accent"],
                                           hover_color=C["accent_hover"], text_color="#FFFFFF")
                else:
                    self.btn_gpu.configure(text=tr("Reinstalla driver"), fg_color=C["hover"],
                                           hover_color=C["line"], text_color=C["text"])
            for gpu in self.gpus:
                if gpu["update"] is True:
                    detail = tr("Driver {version}.", version=gpu["remote"]) if gpu["remote"] else gpu["note"]
                    self.show_toast(tr("Nuovo driver per {name}", name=gpu["name"]), detail, "info")

        def _update_peripherals_ui(self):
            for widget in self.per_rows.winfo_children():
                widget.destroy()
            self.checkbox_vars.clear()

            if not self.deep_updates:
                self.per_footer.pack_forget()
                self._build_empty_state()
                return

            for idx, item in enumerate(self.deep_updates):
                var = ctk.BooleanVar(value=True)
                self.checkbox_vars.append((var, item))
                self._peripheral_row(item, var, delay=idx * 60)
            self.per_footer.pack(fill="x", padx=2)  # padx: lascia visibile il bordo della card
            self._refresh_install_btn()

        def _build_empty_state(self):
            self._sep(self.per_rows).pack(fill="x")
            box = ctk.CTkFrame(self.per_rows, fg_color="transparent")
            box.pack(fill="x", pady=(40, 34))
            circle = ctk.CTkFrame(box, width=52, height=52, corner_radius=26, fg_color=C["ok_bg"])
            circle.pack()
            circle.pack_propagate(False)  # resta un cerchio 52×52, non si adatta al testo
            ctk.CTkLabel(circle, text=GLYPH["check"] if self.ff_icon else "✓", text_color=C["ok_ink"],
                         font=self.F(22, "icon" if self.ff_icon else "bold")).place(relx=0.5, rely=0.5, anchor="center")
            t = ctk.CTkLabel(box, text="", font=self.F(17, "semibold"), text_color=C["surface"])
            t.pack(pady=(12, 0))
            d = ctk.CTkLabel(box, text="", font=self.F(14), text_color=C["surface"], wraplength=340)
            d.pack(pady=(4, 0))
            self._fade_text(t, tr("Tutto aggiornato"), C["text"], bg=C["surface"])
            self._fade_text(d, tr("Ogni periferica ha già l'ultimo driver WHQL disponibile."), C["text2"],
                            bg=C["surface"], delay=60)

        def _peripheral_row(self, item: dict, var, delay: int):
            self._sep(self.per_rows).pack(fill="x")
            row = ctk.CTkFrame(self.per_rows, fg_color=C["surface"], corner_radius=0)
            row.pack(fill="x")
            row.grid_columnconfigure(1, weight=1)
            tk.Frame.configure(row, cursor="hand2")

            cb = ctk.CTkCheckBox(
                row, text="", variable=var, width=24, checkbox_width=22, checkbox_height=22, corner_radius=11,
                border_width=2, border_color=C["muted"], fg_color=C["accent"], hover_color=C["accent_hover"],
                checkmark_color="#FFFFFF", command=self._refresh_install_btn,
            )
            cb.grid(row=0, column=0, rowspan=4, sticky="n", padx=(24, 12), pady=(16, 0))

            name = self._label(row, "", 15, "semibold")
            name.grid(row=0, column=1, sticky="w", padx=(0, 12), pady=(15, 0))
            ign = ctk.CTkButton(
                row, text=tr("Ignora"), width=76, height=28, corner_radius=14, fg_color=C["hover"],
                hover_color=C["line"], text_color=C["text2"], font=self.F(12, "semibold"),
                command=lambda: self._ignore_menu(ign, item),
            )
            ign.grid(row=0, column=2, rowspan=2, sticky="ne", padx=(0, 20), pady=(14, 0))
            hwid = self._label(row, "", 12, "regular", wraplength=520)
            hwid.grid(row=1, column=1, sticky="w", padx=(0, 24), pady=(2, 0))
            ver = ctk.CTkFrame(row, fg_color="transparent")
            ver.grid(row=2, column=1, sticky="w", padx=(0, 24), pady=(6, 0))
            check = self._label(row, "", 12, "regular", wraplength=640)
            check.grid(row=3, column=1, sticky="w", padx=(0, 24), pady=(4, 16))
            v_from = self._label(ver, "", 13)
            v_from.pack(side="left")
            arrow = self._label(ver, "", 13)
            arrow.pack(side="left", padx=8)
            v_to = self._label(ver, "", 13, "semibold")
            v_to.pack(side="left")
            v_date = self._label(ver, "", 13)
            v_date.pack(side="left", padx=(8, 0))

            local = f"{item['local_ver']}"
            fades = [
                (name, item["name"], C["text"]), (hwid, item["hwid"], C["text2"]),
                (v_from, local, C["text2"]), (arrow, "→", C["text2"]),
                (v_to, item["remote_ver"], C["accent_ink"]), (v_date, f"· {fmt_iso_date(item['remote_date'])}", C["text2"]),
                (check, *verify_line(item)),
            ]
            for lbl, text, color in fades:
                self._fade_text(lbl, text, color, ms=420, delay=delay + 40, bg=C["surface"])

            def toggle(_e=None):
                var.set(not var.get())
                self._refresh_install_btn()

            def on_enter(_e):
                self._hover(row, 1.0, C["surface"], C["row_hover"])

            def on_leave(_e):
                if not self._pointer_inside(row):
                    self._hover(row, 0.0, C["surface"], C["row_hover"])

            for w in (row, name, hwid, ver, v_from, arrow, v_to, v_date, check):
                w.bind("<Button-1>", toggle)
            for w in (row, cb, name, hwid, ver, v_from, arrow, v_to, v_date, check):
                w.bind("<Enter>", on_enter, add="+")
                w.bind("<Leave>", on_leave, add="+")

        def _refresh_install_btn(self):
            for btn, pairs, label in ((self.btn_install, self.checkbox_vars, tr("Installa selezionati")),
                                      (self.btn_fix, self.problem_vars, tr("Installa driver"))):
                n = sum(1 for var, _ in pairs if var.get())
                if n:
                    btn.configure(text=f"{label} ({n})", fg_color=C["accent"],
                                  state="disabled" if self.is_busy else "normal")
                else:
                    btn.configure(text=tr("Nessuna selezione"), fg_color=C["accent_soft"], state="disabled")

        # --- Operazioni ----------------------------------------------------------
        def _task_full_scan(self):
            c = FastWMI().prefetch()  # una sola lettura di WMI per tutta la scansione

            # Il controllo delle schede video aspetta solo la rete: gira in parallelo al resto
            def gpus():
                self.gpus = check_all_gpus(c)
                self.nv_info = nvidia_info(self.gpus)
                self.after(0, self._update_gpus_ui)
            gpu_thread = threading.Thread(target=gpus, daemon=True)
            gpu_thread.start()

            # Windows Update risponde in 5-10 s: anche questa ricerca gira in parallelo
            wu = {"items": []}
            drivers = c.Win32_PnPSignedDriver()  # già letti: oggetti semplici, usabili dall'altro thread

            def windows_update():
                pythoncom.CoInitialize()
                try:
                    wu["items"], _ = wu_drivers.search_drivers(drivers, frozenset(load_ignored_updates()))
                finally:
                    pythoncom.CoUninitialize()
            wu_thread = threading.Thread(target=windows_update, daemon=True)
            wu_thread.start()

            problems = scan_problem_devices(c)
            self.problem_devices = problems
            self.after(0, self._update_problems_ui)

            # Le periferiche in errore sono già nella loro card: non ripeterle tra gli aggiornamenti
            catalog = deep_scan_peripherals(c, {d["device_id"] for d in problems if d.get("device_id")})
            gpu_thread.join()
            self.deep_updates = catalog
            self.last_scan = datetime.now()
            self.after(0, self._update_peripherals_ui)  # il Catalog si vede subito, Windows Update si aggiunge

            wu_thread.join()
            if wu["items"]:
                self.deep_updates = wu_drivers.merge(catalog, wu["items"])
                self.after(0, self._update_peripherals_ui)
            mark_seen(summarize(self.gpus, problems, self.deep_updates))

        def _task_msi_mode(self):
            c = FastWMI()
            enable_gpu_msi_mode(c)

        def _select_and_restore_backup(self):
            if self.is_busy:
                return
            chosen = filedialog.askdirectory(
                initialdir=str(BACKUP_DIR),
                title=tr("Seleziona la cartella di Backup Driver da ripristinare")
            )
            if chosen and messagebox.askyesno(
                tr("Ripristina da Backup"),
                tr("Reinstallare i driver della cartella:\n{folder}\n\n"
                   "Se il driver più recente è ancora installato, Windows potrebbe mantenerlo attivo.\n\n"
                   "Procedere?", folder=chosen)
            ):
                self.run_in_background(lambda: restore_driver_backup_folder(chosen), tr("Ripristino dal backup"))

        def _ask_yes_no(self, title: str, message: str) -> bool:
            """Chiede conferma dal thread di lavoro: la finestra si apre nel thread UI, il lavoro attende la risposta."""
            result = {"v": False}
            done = threading.Event()

            def ask():
                try:
                    result["v"] = messagebox.askyesno(title, message)
                finally:
                    done.set()

            self.after(0, ask)
            done.wait()
            return result["v"]

        def _task_cleanup_driverstore(self):
            c = FastWMI()
            candidates = find_obsolete_driver_packages(c)
            if candidates:
                lines = "\n".join(
                    f" • {o['driver']}  {o['provider']} / {o['class']}  {o['version']}  " + tr("(resta {version})", version=o["kept_version"])
                    for o in candidates[:15]
                )
                if len(candidates) > 15:
                    lines += "\n " + tr("… e altri {count}", count=len(candidates) - 15)
                ok = self._ask_yes_no(
                    tr("Pulisci DriverStore"),
                    tr("Trovati {count} pacchetti driver obsoleti (per ognuno resta il più recente).\n"
                       "I driver in uso non vengono toccati.\n\n{lines}\n\n"
                       "Prima verranno creati un punto di ripristino e un backup. Procedere?",
                       count=len(candidates), lines=lines)
                )
                if not ok:
                    print(tr("! Pulizia DriverStore annullata."))
                    return
                create_system_restore_point("DriverCore Pre-DriverStore Cleanup")  # non bloccante
                if not backup_current_drivers():
                    print(tr("✖ Backup driver non riuscito: pulizia annullata."))
                    return
                remove_obsolete_driver_packages(candidates)
            dism_component_cleanup()  # DISM sui componenti di sistema

        def _on_update_gpu(self):
            """Gestore del pulsante (thread UI): chiede conferma, poi avvia il lavoro in background."""
            if self.is_busy:
                return
            if not self.nv_info:
                self.show_toast(tr("GPU non disponibile"), tr("Esegui prima una scansione."), "warning")
                return
            mode = "SLIM" if self.slim_mode else "STANDARD"
            extra = tr(" + installazione pulita (-clean)") if self.clean_mode else ""
            if not messagebox.askyesno(
                tr("Aggiorna GPU NVIDIA"),
                tr("Verrà scaricato e installato il driver NVIDIA {version}\n"
                   "Modalità: {mode}\n\n"
                   "Prima verranno creati un punto di ripristino e un backup dei driver.\n"
                   "Lo schermo può lampeggiare durante l'installazione.\n\n"
                   "Procedere?", version=self.nv_info["remote"], mode=mode + extra)
            ):
                return
            info = dict(self.nv_info)
            slim, clean = self.slim_mode, self.clean_mode
            self.run_in_background(lambda: self._task_update_nvidia(info, slim, clean), tr("Aggiornamento della GPU"))

        def _on_install_problems(self):
            self._on_install_selected(self.problem_vars)

        def _on_install_selected(self, pairs=None):
            """Gestore del pulsante (thread UI): legge la selezione qui, non nel thread di lavoro."""
            if self.is_busy:
                return
            pairs = self.checkbox_vars if pairs is None else pairs
            selected = [item for var, item in pairs if var.get()]
            if not selected:
                self.show_toast(tr("Nessuna selezione"), tr("Seleziona almeno una periferica dalla lista."), "warning")
                return
            names = "\n".join(f" • {i['name']}  ➔  {i['remote_ver']}" for i in selected[:12])
            if len(selected) > 12:
                names += "\n " + tr("… e altri {count}", count=len(selected) - 12)
            if not messagebox.askyesno(
                tr("Installa driver selezionati"),
                tr("Verranno installati {count} driver dal Microsoft Update Catalog:\n\n{names}\n\n"
                   "Prima verranno creati un punto di ripristino e un backup dei driver.\n\n"
                   "Procedere?", count=len(selected), names=names)
            ):
                return
            self.run_in_background(lambda: self._task_install_peripherals(selected), tr("Installazione dei driver"))

        def _task_update_nvidia(self, nv_info: dict, slim: bool, clean: bool):
            create_system_restore_point("DriverCore Pre-NVIDIA Update")  # non bloccante: avvisa se non riesce
            if not backup_current_drivers():
                print(tr("✖ Backup driver non riuscito: aggiornamento NVIDIA annullato."))
                return
            exe_path = download_file(nv_info["url"])
            if not exe_path:
                return
            installed = install_nvidia_driver(exe_path, clean_install=clean, slim_mode=slim, gpu=nv_info)
            if installed:
                clean_gpu_shader_cache()
            self._task_full_scan()

        def _task_install_peripherals(self, selected: list):
            create_system_restore_point("DriverCore Pre-Peripherals Update")  # non bloccante
            if not backup_current_drivers():
                print(tr("✖ Backup driver non riuscito: installazione annullata."))
                return
            install_catalog_cab_updates([i for i in selected if i.get("source") != "wu"])
            wu_drivers.install([i for i in selected if i.get("source") == "wu"])
            self._task_full_scan()

    if __name__ == "__main__":
        if SELFTEST:
            # Verifica del pacchetto: costruisce l'interfaccia nascosta, senza scansione, ed esce
            DriverManagerGUI._task_full_scan = lambda self: None
            app = DriverManagerGUI()
            app.withdraw()
            app.update()
            _ready = time.time()

            def _selftest_done():
                (LOG_DIR / "selftest.log").write_text(
                    f"ok {datetime.now():%Y-%m-%d %H:%M:%S} frozen={FROZEN} tiles={len(app.tiles)} "
                    f"lang={LANG} sample={tr('Scansiona')!r} python={_PY_START - _process_start():.2f}s "
                    f"pronta={_ready - _process_start():.2f}s", encoding="utf-8")
                app.destroy()
            app.after(1200, _selftest_done)
            app.mainloop()
        else:
            if not single_instance.claim():  # un'altra istanza è partita nello stesso istante
                single_instance.request_focus()
                sys.exit(0)
            app = DriverManagerGUI()
            single_instance.watch(app)
            app.mainloop()

except Exception:
    err_msg = traceback.format_exc()
    (LOG_DIR / "gui_error.log").write_text(f"[{datetime.now():%Y-%m-%d %H:%M:%S}]\n{err_msg}", encoding="utf-8")
    if SELFTEST:
        (LOG_DIR / "selftest.log").write_text(f"errore\n{err_msg}", encoding="utf-8")
    else:
        ctypes.windll.user32.MessageBoxW(0, err_msg, "DriverCore", 0x10)
