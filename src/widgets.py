"""Widget animati dell'interfaccia: timer a 1 ms, Tween, scorrimento fluido, interruttore, barra di scansione."""
import ctypes
import ctypes.wintypes
import sys
import time

import _tkinter
import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from theme import ANIMATE, C, ease_in_out_cubic, ease_out_back, ease_out_quint, mix


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

class SmoothScrollFrame(ctk.CTkScrollableFrame):
    """Rotellina con scorrimento fluido: la pagina rallenta dolcemente verso il punto di arrivo, a ritmo con
    il monitor, invece di saltare di 20 px a ogni scatto. Scatti ravvicinati si sommano, come su macOS."""
    STEP_PX = 96       # pixel per scatto della rotellina (120 di delta)
    FOLLOW = 0.22      # frazione della distanza residua percorsa in un frame da 16,7 ms

    FOLLOW_DRAG = 0.55  # con la barra: la pagina segue il cursore quasi subito, con un filo di morbidezza

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._target = None
        self._pos = 0.0
        self._scroll_id = None
        self._last = 0.0
        self._follow = self.FOLLOW
        self._dragging = False
        if sys.platform.startswith("win") and ANIMATE:
            # anche la barra passa dallo scorrimento fluido (prima spostava la pagina di colpo)
            self._scrollbar.configure(command=self._on_scrollbar)
            self._parent_canvas.configure(yscrollcommand=self._on_canvas_scrolled)
            self._scrollbar.bind("<ButtonPress-1>", lambda e: setattr(self, "_dragging", True))
            self._scrollbar.bind("<ButtonRelease-1>", self._drag_end)

    def _on_canvas_scrolled(self, first, last):
        # mentre si trascina, il cursore lo muove la barra stessa: la pagina, che arriva un attimo dopo,
        # non deve riportarlo indietro (tremolio)
        if not self._dragging:
            self._scrollbar.set(first, last)

    def _drag_end(self, _event=None):
        self._dragging = False
        self._scrollbar.set(*self._parent_canvas.yview())

    def _on_scrollbar(self, *args):
        if args and args[0] == "moveto":
            self._glide_to(float(args[1]) * self._content_height(), self.FOLLOW_DRAG)
        elif args and args[0] == "scroll" and len(args) == 3 and args[2] == "units":
            # rotellina sopra la barra: CTkScrollbar manda -delta/40 unità
            self._glide_to(self._base() + int(args[1]) * self.STEP_PX / 3, self.FOLLOW)
        else:
            self._parent_canvas.yview(*args)

    def _base(self) -> float:
        """Punto di partenza: la destinazione in corso, o la posizione attuale se la pagina è ferma."""
        return self._target if self._scroll_id is not None else self._parent_canvas.canvasy(0)

    def _glide_to(self, top: float, follow: float):
        if self._parent_canvas.yview() == (0.0, 1.0):
            return
        if self._scroll_id is None:  # parte da dove si trova ora
            self._pos = self._parent_canvas.canvasy(0)
        self._target = min(self._max_top(), max(0.0, top))
        self._follow = follow
        if self._scroll_id is None:
            SmoothTimer.acquire()
            self._last = time.perf_counter()
            self._scroll_tick()

    def _content_height(self) -> float:
        region = str(self._parent_canvas.cget("scrollregion")).split()
        return float(region[3]) - float(region[1]) if len(region) == 4 else 0.0

    def _max_top(self) -> float:
        return max(0.0, self._content_height() - self._parent_canvas.winfo_height())

    def _mouse_wheel_all(self, event):
        if self._shift_pressed or not sys.platform.startswith("win") or not ANIMATE:
            return super()._mouse_wheel_all(event)
        if self._check_if_valid_scroll(event.widget):
            self._glide_to(self._base() - event.delta / 120 * self.STEP_PX, self.FOLLOW)

    def _blank_strip(self, moved: int):
        """Riempie col colore di sfondo la striscia appena entrata dal bordo (meno di 0,1 ms).

        Spostando il contenuto Windows copia i pixel già disegnati; la striscia nuova resta con le righe vecchie
        finché Tk non la ridisegna (~10 ms). Su un monitor a 200 Hz lo schermo si aggiorna nel frattempo e si
        vede testo duplicato e "stirato". Con la striscia vuota, nel caso peggiore il bordo resta vuoto per
        un fotogramma: non si nota.
        """
        if not moved:
            return
        cv = self._parent_canvas
        w, h = cv.winfo_width(), cv.winfo_height()
        n = min(h, abs(moved) + 2)
        top = h - n if moved > 0 else 0
        u, g = ctypes.windll.user32, ctypes.windll.gdi32
        hwnd = cv.winfo_id()
        hdc = u.GetDCEx(hwnd, None, 0x2)  # DCX_CACHE: disegna anche sopra le finestre figlie
        if not hdc:
            return
        try:
            r, gg, bb = (v >> 8 for v in cv.winfo_rgb(cv.cget("bg")))
            brush = g.CreateSolidBrush(r | (gg << 8) | (bb << 16))
            rect = ctypes.wintypes.RECT(0, top, w, top + n)
            u.FillRect(hdc, ctypes.byref(rect), brush)
            g.DeleteObject(brush)
        finally:
            u.ReleaseDC(hwnd, hdc)
        # i widget sotto la striscia non sanno di essere stati coperti: vanno ridisegnati (RDW_INVALIDATE |
        # RDW_ALLCHILDREN; il ridisegno vero e proprio lo fa _paint_now con RDW_UPDATENOW)
        u.RedrawWindow(hwnd, ctypes.byref(rect), None, 0x0001 | 0x0080)

    def _paint_now(self, moved: int):
        """Sposta e ridisegna subito, nello stesso fotogramma (Tk lo farebbe al giro successivo)."""
        self.update_idletasks()  # sposta il contenuto
        try:
            self._blank_strip(moved)
            hwnd = ctypes.windll.user32.GetParent(self.winfo_toplevel().winfo_id())
            ctypes.windll.user32.RedrawWindow(hwnd, None, None, 0x0100 | 0x0080)  # UPDATENOW | ALLCHILDREN
        except Exception:
            return
        while self.tk.dooneevent(_tkinter.WINDOW_EVENTS | _tkinter.DONT_WAIT):  # eventi Expose generati sopra
            pass
        self.update_idletasks()  # ridisegno dei widget esposti

    def _scroll_tick(self):
        try:
            ctypes.windll.dwmapi.DwmFlush()  # attende l'aggiornamento dello schermo: si parte a inizio fotogramma
        except Exception:
            pass
        now = time.perf_counter()
        frames = max(1.0, (now - self._last) * 60)  # se un frame arriva tardi si recupera il ritardo
        self._last = now
        diff = self._target - self._pos
        if abs(diff) < 1.5:  # ultimo pixel e mezzo: si arriva subito invece di strisciare
            self._pos = self._target
        else:
            self._pos += diff * (1 - (1 - self._follow) ** frames)
        total = self._content_height()
        try:
            if total > 0:
                before = round(self._parent_canvas.canvasy(0))
                self._parent_canvas.yview_moveto(round(self._pos) / total)
                self._paint_now(round(self._parent_canvas.canvasy(0)) - before)
        except tk.TclError:
            self._pos = self._target
        if self._pos == self._target:
            self._scroll_id = None
            SmoothTimer.release()
        else:
            # il ritmo lo dà DwmFlush (frequenza del monitor), non un timer fisso
            self._scroll_id = self.after(1, self._scroll_tick)

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
