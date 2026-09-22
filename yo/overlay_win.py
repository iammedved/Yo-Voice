"""Бесфокусный overlay: логотип ЙО и волны, без рамки (tkinter / Windows)."""

from __future__ import annotations

import ctypes
import logging
import math
import time
import tkinter as tk
from ctypes import wintypes
from types import SimpleNamespace

from yo.capture import NO_MIC_HINT
from yo.paths import orb_path
from yo.phrases import display_label, wave_allowed
from yo.spectrum import voice_loudness, wave_amplitude
from yo.winapi import hwnd_int, set_dpi_aware

log = logging.getLogger("yo.overlay")

WIDTH = 200
HEIGHT = 186
MASCOT_HEIGHT = 118
WAVE_GAP = 4
STATUS_HEIGHT = 16
WAVE_HEIGHT = 40
WAVE_BARS = 52
_CHROMA = "#00FF01"

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008
WS_EX_LAYERED = 0x00080000
MA_NOACTIVATE = 3
GA_ROOT = 2
HWND_TOPMOST = wintypes.HWND(-1)
HWND_NOTOPMOST = wintypes.HWND(-2)
HWND_TOP = wintypes.HWND(0)
DWMWA_CLOAKED = 14
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040
SWP_NOOWNERZORDER = 0x0200
SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
LWA_COLORKEY = 0x00000001
MONITOR_DEFAULTTONEAREST = 2
_CHROMA_RGB = (0, 255, 1)
_CHROMA_COLORREF = 0x0001FF00  # #00FF01 as 0x00BBGGRR
_SKIP_ATTACH_CLASSES = {
    "progman",
    "workerw",
    "shelldll_defview",
    "shell_traywnd",
    "shell_secondarytraywnd",
    "notifyiconoverflowwindow",
    "toplevelwindowforoverflowxamlisland",
    "dv2controlhost",
    "tasklistthumbnailwnd",
    "traynotifywnd",
}
SPI_GETWORKAREA = 0x0030
GWLP_WNDPROC = -4
GWLP_HWNDPARENT = -8
WM_MOUSEACTIVATE = 0x0021
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")


class RECT(ctypes.Structure):
    _fields_ = (
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    )


class MONITORINFO(ctypes.Structure):
    _fields_ = (
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
    )


user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
user32.SystemParametersInfoW.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
user32.SetWindowPos.restype = wintypes.BOOL
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.SetLayeredWindowAttributes.argtypes = [
    wintypes.HWND,
    wintypes.COLORREF,
    ctypes.c_ubyte,
    wintypes.DWORD,
]
user32.SetLayeredWindowAttributes.restype = wintypes.BOOL
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.MonitorFromWindow.restype = wintypes.HMONITOR
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.c_void_p]
user32.GetMonitorInfoW.restype = wintypes.BOOL
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.AttachThreadInput.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL
user32.IsHungAppWindow.argtypes = [wintypes.HWND]
user32.IsHungAppWindow.restype = wintypes.BOOL
dwmapi.DwmGetWindowAttribute.argtypes = [
    wintypes.HWND,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
]
dwmapi.DwmGetWindowAttribute.restype = ctypes.HRESULT
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
user32.CallWindowProcW.argtypes = [
    ctypes.c_void_p,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.CallWindowProcW.restype = LRESULT

if ctypes.sizeof(ctypes.c_void_p) == 8:
    _get_long = user32.GetWindowLongPtrW
    _set_long = user32.SetWindowLongPtrW
    _get_long.argtypes = [wintypes.HWND, ctypes.c_int]
    _get_long.restype = ctypes.c_ssize_t
    _set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _set_long.restype = ctypes.c_ssize_t
else:
    _get_long = user32.GetWindowLongW
    _set_long = user32.SetWindowLongW
    _get_long.argtypes = [wintypes.HWND, ctypes.c_int]
    _get_long.restype = ctypes.c_long
    _set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    _set_long.restype = ctypes.c_long


def _work_area() -> tuple[int, int, int, int]:
    rect = RECT()
    if user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
        return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
    return 0, 0, 0, 0


def _window_class(hwnd: int) -> str:
    if not hwnd:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    try:
        n = int(user32.GetClassNameW(hwnd, buf, 256) or 0)
    except Exception:
        return ""
    return (buf.value or "").lower() if n else ""


def _skip_attach(klass: str) -> bool:
    """Tray/desktop/XAML islands deadlock Tk or sit in the wrong z-band."""
    k = (klass or "").lower()
    return k in _SKIP_ATTACH_CLASSES or "overflowxamlisland" in k or "inputsite" in k


def _window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    if not hwnd:
        return None
    rect = RECT()
    try:
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
    except Exception:
        return None
    return None


def _monitor_work_area(hwnd: int = 0) -> tuple[int, int, int, int]:
    if hwnd:
        try:
            mon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)
            if mon and user32.GetMonitorInfoW(mon, ctypes.byref(info)):
                r = info.rcWork
                return int(r.left), int(r.top), int(r.right), int(r.bottom)
        except Exception:
            pass
    return _work_area()


def _pos_outside_rect(
    x: int,
    y: int,
    width: int,
    height: int,
    rect: tuple[int, int, int, int],
) -> bool:
    left, top, right, bottom = rect
    return x + width < left or x > right or y + height < top or y > bottom


def _window_cloaked(hwnd: int) -> bool:
    if not hwnd:
        return False
    val = wintypes.DWORD(0)
    try:
        hr = int(
            dwmapi.DwmGetWindowAttribute(
                hwnd,
                DWMWA_CLOAKED,
                ctypes.byref(val),
                ctypes.sizeof(val),
            )
            or 0
        )
    except Exception:
        return False
    return hr == 0 and int(val.value) != 0


def _flatten_to_chroma(im):
    """RGBA → opaque RGB keyed to #00FF01. Mid-alpha fur must not tint lime."""
    from PIL import Image

    rgba = im.convert("RGBA")
    w, h = rgba.size
    src = rgba.load()
    out = Image.new("RGB", (w, h), _CHROMA_RGB)
    dst = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = src[x, y]
            if a < 40:
                continue
            if g >= 240 and r <= 40 and b <= 40:
                continue
            dst[x, y] = (r, g, b)
    return out


def _load_orb(master: tk.Misc) -> tk.PhotoImage | None:
    path = orb_path()
    if not path.exists():
        return None
    try:
        from PIL import Image, ImageTk

        im = Image.open(path).convert("RGBA")
        src_w, src_h = im.size
        if src_h > MASCOT_HEIGHT > 0:
            width = max(1, int(round(src_w * (MASCOT_HEIGHT / src_h))))
            im = im.resize((width, MASCOT_HEIGHT), Image.Resampling.LANCZOS)
        keyed = _flatten_to_chroma(im)
        return ImageTk.PhotoImage(keyed, master=master)
    except Exception:
        pass
    try:
        pix = tk.PhotoImage(file=str(path), master=master)
    except tk.TclError:
        return None
    src_h = int(pix.height())
    if src_h > MASCOT_HEIGHT:
        factor = max(1, int(round(src_h / MASCOT_HEIGHT)))
        pix = pix.subsample(factor, factor)
    return pix


def _voice_speed(rms_value: float, pcm) -> float:
    loud = voice_loudness(rms_value)
    if pcm is None or len(pcm) < 8:
        return loud
    zc = 0
    prev = float(pcm[0])
    for sample in pcm[1:]:
        value = float(sample)
        if prev == 0.0 or (prev < 0.0) != (value < 0.0):
            zc += 1
        prev = value
    rate = min(1.0, (zc / max(1, len(pcm) - 1)) * 8.0)
    return min(1.0, 0.55 * loud + 0.45 * rate)


class Overlay:
    def __init__(self, on_click=None, saved_pos=None, on_move=None, on_settings=None) -> None:
        self.on_click = on_click
        self.on_move = on_move
        self.on_settings = on_settings
        self.rms = 0.0
        self.wave = [0.12] * WAVE_BARS
        self.wave_target = [0.12] * WAVE_BARS
        self._bars: list[list[float]] = []
        self._pending_amp = 0.0
        self._last_tick = 0.0
        self.status = ""
        self.preview = ""
        self.mic_missing = False
        self.hint = ""
        self.live = False
        self.live_since: float | None = None
        self.task = "transcribe"
        self.visible = False
        self._tick_id: str | None = None
        self._drag = None
        self._dragged = False
        self._user_pos = saved_pos
        self._phase = 0.0
        self._speed = 0.08
        self._speed_target = 0.08
        self._wndproc = None
        self._old_proc = 0
        self._topmost_id: str | None = None
        self._parked = False
        self._wave_image = None
        self._amp_shown = 0.0
        self._anchor_hwnd = 0

        set_dpi_aware()
        root = getattr(tk, "_default_root", None)
        if root is None:
            self.window = tk.Tk()
        else:
            self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.title("Весёлый жираф")
        self.window.resizable(False, False)
        self.window.overrideredirect(True)
        # Tk -topmost on deiconify steals FG; WS_EX_TOPMOST is set in _apply_exstyle.
        try:
            self.window.attributes("-toolwindow", True)
        except tk.TclError:
            pass
        self.window.configure(bg=_CHROMA)
        try:
            self.window.attributes("-transparentcolor", _CHROMA)
        except tk.TclError:
            pass
        self.window.geometry(f"{WIDTH}x{HEIGHT}+0+0")

        self._canvas = tk.Canvas(
            self.window,
            width=WIDTH,
            height=HEIGHT,
            highlightthickness=0,
            bd=0,
            bg=_CHROMA,
        )
        self._canvas.pack(fill="both", expand=True)
        self._photo = _load_orb(self.window)
        self._pixbuf = self._photo

        for widget in (self.window, self._canvas):
            widget.bind("<ButtonPress-1>", self._on_press)
            widget.bind("<ButtonPress-3>", self._on_press)
            widget.bind("<B1-Motion>", self._on_motion)
            widget.bind("<ButtonRelease-1>", self._on_release)

    def native_id(self) -> int | None:
        try:
            hwnd = hwnd_int(self.window.winfo_id())
        except tk.TclError:
            return None
        if not hwnd:
            return None
        root = hwnd_int(user32.GetAncestor(hwnd, GA_ROOT))
        return root or hwnd

    def set_anchor(self, hwnd: int | None) -> None:
        """Window the cat must ride (paste target), not whatever is FG now."""
        self._anchor_hwnd = hwnd_int(hwnd) if hwnd else 0

    def show_listening(self, status: str = "") -> None:
        self.status = status
        self.visible = True
        if not self.live:
            self._bars = []
            self._pending_amp = 0.0
        self._last_tick = 0.0
        self._place()
        self._map_window()
        if self._tick_id is None:
            self._tick_id = self.window.after(33, self._tick)

    def hide(self) -> None:
        self.visible = False
        self.preview = ""
        self.status = ""
        self.hint = ""
        self.mic_missing = False
        self.live = False
        self.live_since = None
        self.task = "transcribe"
        self._parked = False
        self._cancel_topmost_pulse()
        hwnd = self.native_id() or 0
        if hwnd:
            self._unown_overlay(hwnd)
        try:
            self.window.withdraw()
        except tk.TclError:
            pass
        if hwnd:
            try:
                user32.ShowWindow(hwnd, SW_HIDE)
            except Exception:
                pass
        self._persist_pos()
        sid = self._tick_id
        self._tick_id = None
        if sid is not None:
            try:
                self.window.after_cancel(sid)
            except Exception:
                pass

    def park(self) -> None:
        """Withdraw without clearing listening state so Ctrl+V can hit the field."""
        self._parked = True
        self._cancel_topmost_pulse()
        hwnd = self.native_id() or 0
        if hwnd:
            self._unown_overlay(hwnd)
        try:
            self.window.withdraw()
        except tk.TclError:
            pass
        if hwnd:
            try:
                user32.ShowWindow(hwnd, SW_HIDE)
            except Exception:
                pass
        sid = self._tick_id
        self._tick_id = None
        if sid is not None:
            try:
                self.window.after_cancel(sid)
            except Exception:
                pass

    def unpark(self) -> None:
        if not self.visible:
            return
        self._parked = False
        self._map_window()
        if self._tick_id is None:
            self._tick_id = self.window.after(33, self._tick)

    def set_task(self, task: str) -> None:
        self.task = "translate" if task == "translate" else "transcribe"

    def set_status(self, status: str) -> None:
        self.status = status
        if self.visible:
            self._paint()

    def set_live(self, live: bool) -> None:
        self.live = bool(live)
        self.live_since = time.monotonic() if self.live else None
        if not self.live:
            self._bars = []
            self._pending_amp = 0.0
        if self.visible:
            self._paint()

    def set_preview(self, text: str) -> None:
        self.preview = text

    def set_mic_missing(self, missing: bool) -> None:
        self.mic_missing = bool(missing)
        if self.mic_missing:
            self.hint = NO_MIC_HINT
            self._bars = []
        elif self.hint == NO_MIC_HINT:
            self.hint = ""
        if self.visible:
            self._paint()

    def set_hint(self, text: str) -> None:
        self.hint = (text or "").strip()
        if self.hint:
            self._bars = []
        if self.visible:
            self._paint()

    def set_levels(self, rms_value: float, bands: list[float] | None = None, pcm=None) -> None:
        self.rms = float(rms_value)
        amp = wave_amplitude(self.rms)
        self._pending_amp += (amp - self._pending_amp) * 0.28
        self._speed_target = _voice_speed(self.rms, pcm)

    def _tick(self) -> None:
        self._tick_id = None
        if not self.visible:
            return
        now = time.monotonic()
        dt = 0.016 if self._last_tick <= 0 else min(0.033, now - self._last_tick)
        self._last_tick = now
        self._speed += (self._speed_target - self._speed) * 0.16
        self._amp_shown += (self._pending_amp - self._amp_shown) * 0.18
        if not wave_allowed(live=self.live, hint=self.hint, mic_missing=self.mic_missing):
            self._bars = []
            self._paint()
            self._tick_id = self.window.after(33, self._tick)
            return
        px_per_sec = 8.0 + 8.0 * self._speed
        step = 5.0
        width = self._wave_width()
        amp = self._amp_shown
        for bar in self._bars:
            bar[0] -= px_per_sec * dt
        self._bars = [bar for bar in self._bars if bar[0] + 3.0 > -step]
        if not self._bars:
            self._bars.append([width, amp])
        while self._bars[-1][0] < width:
            self._bars.append([self._bars[-1][0] + step, amp])
            if len(self._bars) > 90:
                break
        self._paint()
        self._tick_id = self.window.after(33, self._tick)

    def _persist_pos(self) -> None:
        if self._user_pos is None or self.on_move is None:
            return
        try:
            self.on_move(*self._user_pos)
        except Exception:
            pass

    def _clamp_pos(
        self,
        x: int,
        y: int,
        area: tuple[int, int, int, int] | None = None,
    ) -> tuple[int, int]:
        left, top, right, bottom = area or _work_area()
        if right - left < WIDTH or bottom - top < HEIGHT:
            return int(x), int(y)
        x = min(max(int(x), left), right - WIDTH)
        y = min(max(int(y), top), bottom - HEIGHT)
        return x, y

    def _place(self) -> None:
        anchor = self._root_hwnd(self._anchor_hwnd)
        area = _monitor_work_area(anchor)
        win = _window_rect(anchor) if anchor else None
        if self._user_pos is not None:
            x, y = self._user_pos
            relocated = False
            if win and _pos_outside_rect(x, y, WIDTH, HEIGHT, win):
                left, top, right, bottom = win
                x = left + max(0, (right - left - WIDTH) // 2)
                y = bottom - HEIGHT - 16
                relocated = True
            x, y = self._clamp_pos(x, y, area=area)
            if not relocated:
                self._user_pos = (x, y)
            self.window.geometry(f"{WIDTH}x{HEIGHT}+{x}+{y}")
            return
        if win:
            left, top, right, bottom = win
            x = left + max(0, (right - left - WIDTH) // 2)
            y = bottom - HEIGHT - 16
        elif area[2] > area[0] and area[3] > area[1]:
            left, top, right, bottom = area
            x = left + (right - left - WIDTH) // 2
            y = bottom - HEIGHT - 16
        else:
            try:
                sw = int(self.window.winfo_screenwidth())
                sh = int(self.window.winfo_screenheight())
            except tk.TclError:
                sw, sh = 1280, 720
            x = (sw - WIDTH) // 2
            y = sh - HEIGHT - 72
        x, y = self._clamp_pos(x, y, area=area)
        self.window.geometry(f"{WIDTH}x{HEIGHT}+{x}+{y}")

    def _root_hwnd(self, hwnd: int | None) -> int:
        handle = hwnd_int(hwnd) if hwnd else 0
        if not handle:
            return 0
        try:
            root = hwnd_int(user32.GetAncestor(handle, GA_ROOT))
        except Exception:
            root = 0
        return root or handle

    def _is_attachable(self, hwnd: int) -> bool:
        handle = hwnd_int(hwnd)
        if not handle:
            return False
        overlay = self.native_id() or 0
        if overlay and handle == overlay:
            return False
        try:
            if not user32.IsWindow(handle):
                return False
            if user32.IsIconic(handle) or user32.IsHungAppWindow(handle):
                return False
        except Exception:
            return False
        if _skip_attach(_window_class(handle)) or _window_cloaked(handle):
            return False
        return True

    def _resolve_anchor(self, fg: int = 0) -> int:
        """Paste-target window first; live FG only if that target is junk.

        Tray overflow / desktop as FG must not hide the cat behind Grok.
        """
        overlay = self.native_id() or 0
        for candidate in (self._anchor_hwnd, fg):
            hwnd = self._root_hwnd(candidate)
            if hwnd and hwnd != overlay and self._is_attachable(hwnd):
                return hwnd
        return 0

    def _attach_to_foreground(self, hwnd: int | None = None) -> tuple[int, int] | None:
        """Join the captured window thread so ShowWindow/SetWindowPos is honoured.

        Pass the paste-target/anchor hwnd, not live FG after deiconify.
        Re-reading GetForegroundWindow after an unattached show often returns
        the overlay itself or tray overflow, so the cat stays behind a
        maximized/snapped console. Never attach to explorer overflow / XAML
        islands — that deadlocks Tk.
        """
        overlay = self.native_id() or 0
        fg = self._root_hwnd(hwnd)
        if not fg:
            try:
                fg = hwnd_int(user32.GetForegroundWindow())
            except Exception:
                fg = 0
            fg = self._root_hwnd(fg)
        if not fg or (overlay and fg == overlay) or not self._is_attachable(fg):
            return None
        our_tid = int(kernel32.GetCurrentThreadId() or 0)
        fg_tid = int(user32.GetWindowThreadProcessId(fg, None) or 0)
        if not our_tid or not fg_tid or our_tid == fg_tid:
            return None
        if user32.AttachThreadInput(our_tid, fg_tid, True):
            return (our_tid, fg_tid)
        return None

    def _detach_from_foreground(self, pair: tuple[int, int] | None) -> None:
        if not pair:
            return
        try:
            user32.AttachThreadInput(pair[0], pair[1], False)
        except Exception:
            pass

    def _unown_overlay(self, hwnd: int) -> None:
        """Drop the hidden Tk owner so TOPMOST is not stuck in the desktop band."""
        if not hwnd:
            return
        try:
            owner = int(_get_long(hwnd, GWLP_HWNDPARENT) or 0)
        except Exception:
            return
        if owner:
            _set_long(hwnd, GWLP_HWNDPARENT, 0)

    def _set_topmost_noactivate(self, hwnd: int, *, show: bool = False) -> None:
        if not hwnd:
            return
        self._unown_overlay(hwnd)
        flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER
        if show:
            flags |= SWP_SHOWWINDOW
        user32.SetWindowPos(
            hwnd,
            HWND_TOPMOST,
            0,
            0,
            0,
            0,
            flags,
        )

    def _own_to_foreground(self, hwnd: int, owner: int) -> bool:
        """Ride the target window's z-band (maximized/snapped/fullscreen console).

        Unowned TOPMOST from a background process is ignored by conhost, so
        the cat stays behind a maximized or snapped Grok PowerShell window.
        An owned WS_POPUP with HWND_TOP follows the owner's z-band.
        """
        owner = self._root_hwnd(owner)
        if not hwnd or not owner or owner == hwnd or not self._is_attachable(owner):
            return False
        try:
            if not user32.IsWindow(owner):
                return False
        except Exception:
            return False
        self._unown_overlay(hwnd)
        _set_long(hwnd, GWLP_HWNDPARENT, owner)
        try:
            now = int(_get_long(hwnd, GWLP_HWNDPARENT) or 0)
        except Exception:
            now = 0
        if now != owner:
            return False
        user32.SetWindowPos(
            hwnd,
            HWND_NOTOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        )
        user32.SetWindowPos(
            hwnd,
            HWND_TOP,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )
        log.info("оверлей привязан к окну hwnd=%s", owner)
        return True

    def _restore_foreground(self, prev: int) -> None:
        overlay = self.native_id() or 0
        if not prev or not overlay or prev == overlay:
            return
        if _skip_attach(_window_class(prev)):
            return
        try:
            from yo.winapi import allow_set_foreground

            current = hwnd_int(user32.GetForegroundWindow())
            if current == overlay and user32.IsWindow(prev):
                allow_set_foreground()
                user32.SetForegroundWindow(prev)
        except Exception:
            pass

    def _arm_topmost_pulse(self) -> None:
        if self._topmost_id is not None or self._parked:
            return
        try:
            self._topmost_id = self.window.after(1200, self._pulse_topmost)
        except tk.TclError:
            self._topmost_id = None

    def _cancel_topmost_pulse(self) -> None:
        sid = self._topmost_id
        self._topmost_id = None
        if sid is not None:
            try:
                self.window.after_cancel(sid)
            except Exception:
                pass

    def _pulse_topmost(self) -> None:
        self._topmost_id = None
        if not self.visible or self._parked:
            return
        try:
            hwnd = self.native_id() or 0
            if hwnd:
                flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER
                try:
                    owner = int(_get_long(hwnd, GWLP_HWNDPARENT) or 0)
                except Exception:
                    owner = 0
                insert = HWND_TOP if owner else HWND_TOPMOST
                user32.SetWindowPos(
                    hwnd,
                    insert,
                    0,
                    0,
                    0,
                    0,
                    flags,
                )
                self._apply_chroma(hwnd)
        except tk.TclError:
            return
        self._arm_topmost_pulse()

    def _map_window(self) -> None:
        self._parked = False
        fg = 0
        try:
            fg = hwnd_int(user32.GetForegroundWindow())
        except Exception:
            fg = 0
        # Join the paste-target (Grok) even if live FG is tray overflow.
        anchor = self._resolve_anchor(fg)
        attached = None
        hwnd = 0
        did_attach = False
        owned = False
        try:
            self.window.update_idletasks()
            self._apply_exstyle()
            self.window.deiconify()
            # lift() steals focus; Ctrl+V would land on the cat, not the field.
            # Tk topmost after map also steals FG — Win32 SetWindowPos only.
            hwnd = self.native_id() or 0
            if hwnd:
                self._unown_overlay(hwnd)
                # Attach to the paste-target/anchor, then show while attached.
                # Do not hold attach across deiconify / _paint — deadlock.
                attached = self._attach_to_foreground(anchor)
                did_attach = attached is not None
                try:
                    user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
                    if anchor:
                        owned = self._own_to_foreground(hwnd, anchor)
                    if not owned:
                        self._set_topmost_noactivate(hwnd, show=True)
                    restore_to = anchor if self._is_attachable(anchor) else fg
                    self._restore_foreground(restore_to)
                finally:
                    self._detach_from_foreground(attached)
                    attached = None
                self._apply_chroma(hwnd)
            self._paint()
        except tk.TclError:
            pass
        finally:
            self._detach_from_foreground(attached)
        restore_to = anchor if self._is_attachable(anchor) else fg
        self._restore_foreground(restore_to)
        self._arm_topmost_pulse()
        log.info(
            "оверлей показан fg=%s anchor=%s attach=%s owned=%s overlay=%s",
            fg,
            anchor,
            did_attach,
            owned,
            hwnd,
        )

    def _apply_chroma(self, hwnd: int = 0) -> None:
        try:
            self.window.attributes("-transparentcolor", _CHROMA)
        except tk.TclError:
            pass
        hwnd = hwnd or self.native_id() or 0
        if not hwnd:
            return
        try:
            style = int(_get_long(hwnd, GWL_EXSTYLE) or 0)
            if not (style & WS_EX_LAYERED):
                _set_long(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)
            user32.SetLayeredWindowAttributes(hwnd, _CHROMA_COLORREF, 0, LWA_COLORKEY)
        except Exception:
            pass

    def _apply_exstyle(self) -> None:
        try:
            hwnd = hwnd_int(self.window.winfo_id())
        except tk.TclError:
            return
        if not hwnd:
            return
        root = hwnd_int(user32.GetAncestor(hwnd, GA_ROOT))
        hwnd = root or hwnd
        try:
            self._unown_overlay(hwnd)
            style = int(_get_long(hwnd, GWL_EXSTYLE))
            style |= WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_LAYERED
            _set_long(hwnd, GWL_EXSTYLE, style)
            user32.SetWindowPos(
                hwnd,
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_NOOWNERZORDER,
            )
            self._apply_chroma(hwnd)
            # Do not subclass Tk's WNDPROC. ctypes + tk_popup/Tk internals
            # released the GIL (PyEval_RestoreThread thread state NULL).
        except Exception:
            pass

    def _subclass_noactivate(self, hwnd: int) -> None:
        if self._wndproc is not None or not hwnd:
            return
        old = int(_get_long(hwnd, GWLP_WNDPROC) or 0)
        if not old:
            return
        self._old_proc = old

        def wndproc(h, msg, wp, lp):
            if int(msg) == WM_MOUSEACTIVATE:
                return MA_NOACTIVATE
            return user32.CallWindowProcW(ctypes.c_void_p(self._old_proc), h, msg, wp, lp)

        self._wndproc = WNDPROC(wndproc)
        _set_long(hwnd, GWLP_WNDPROC, ctypes.cast(self._wndproc, ctypes.c_void_p).value)

    def _on_press(self, event) -> None:
        button = int(getattr(event, "num", 1) or 1)
        if button == 3:
            event = SimpleNamespace(button=3, x_root=event.x_root, y_root=event.y_root)
            if self.on_settings is not None:
                self.on_settings(event)
            return
        if button != 1:
            return
        try:
            wx, wy = int(self.window.winfo_x()), int(self.window.winfo_y())
        except tk.TclError:
            wx, wy = 0, 0
        self._drag = (event.x_root, event.y_root, wx, wy)
        self._dragged = False

    def _on_motion(self, event) -> None:
        if self._drag is None:
            return
        x0, y0, wx, wy = self._drag
        dx = event.x_root - x0
        dy = event.y_root - y0
        if abs(dx) > 4 or abs(dy) > 4:
            self._dragged = True
        nx, ny = self._clamp_pos(int(wx + dx), int(wy + dy))
        try:
            self.window.geometry(f"+{nx}+{ny}")
        except tk.TclError:
            return
        self._user_pos = (nx, ny)

    def _on_release(self, event) -> None:
        dragged = self._dragged
        self._drag = None
        self._dragged = False
        self._persist_pos()
        button = int(getattr(event, "num", 1) or 1)
        if not dragged and button == 1 and self.on_click is not None:
            try:
                self.on_click()
            except Exception:
                pass

    def _wave_width(self) -> float:
        pix = self._photo
        if pix is not None:
            return min(WIDTH - 20, max(96.0, pix.width() * 0.92))
        return float(WIDTH - 28)

    def _paint(self) -> None:
        if not self.visible:
            return
        try:
            canvas = self._canvas
            canvas.delete("all")
        except tk.TclError:
            return
        mascot_bottom = min(self._draw_mascot(), 4.0 + MASCOT_HEIGHT)
        wave_w = self._wave_width()
        wave_x = (WIDTH - wave_w) / 2
        status_y = mascot_bottom + WAVE_GAP
        waves_on = wave_allowed(
            live=self.live, hint=self.hint, mic_missing=self.mic_missing
        )
        status_h = float(STATUS_HEIGHT) if waves_on else max(
            float(STATUS_HEIGHT), HEIGHT - status_y - 4.0
        )
        status_w = float(WIDTH - 12)
        status_x = (WIDTH - status_w) / 2.0
        self._draw_status(status_x, status_y, status_w, status_h)
        if waves_on:
            self._draw_waves(
                wave_x, status_y + STATUS_HEIGHT + WAVE_GAP, wave_w, WAVE_HEIGHT
            )

    def _draw_mascot(self) -> float:
        top = 4.0
        pix = self._photo
        if pix is None:
            self._canvas.create_text(
                WIDTH / 2,
                top + 40,
                text="ЙО",
                fill="#e6f2ff",
                font=("Segoe UI", 18, "bold"),
            )
            return top + 80
        self._canvas.create_image(WIDTH / 2, top, image=pix, anchor="n")
        return top + pix.height()

    def _draw_status(self, x: float, y: float, width: float, height: float) -> None:
        label = display_label(
            live=self.live,
            now=time.monotonic(),
            live_since=self.live_since,
            hint=self.hint,
            mic_missing=self.mic_missing,
            status=self.status,
            task=self.task,
        )
        if not label:
            return
        canvas = self._canvas
        cx = x + width / 2.0
        wrap = max(24, int(width - 8))
        max_h = max(12.0, float(height))
        fill = "#f4f7fb"
        stroke = "#0c0e12"
        item = None
        shadows: list[int] = []
        size = 10
        while size >= 8:
            for sid in shadows:
                canvas.delete(sid)
            if item is not None:
                canvas.delete(item)
            shadows = []
            font = ("Segoe UI", size)
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                shadows.append(
                    canvas.create_text(
                        cx + dx,
                        y + dy,
                        text=label,
                        fill=stroke,
                        font=font,
                        width=wrap,
                        anchor="n",
                        justify="center",
                    )
                )
            item = canvas.create_text(
                cx,
                y,
                text=label,
                fill=fill,
                font=font,
                width=wrap,
                anchor="n",
                justify="center",
            )
            bbox = canvas.bbox(item)
            if bbox is None or (bbox[3] - bbox[1]) <= max_h:
                break
            size -= 1
        bbox = canvas.bbox(item) if item is not None else None
        if bbox is None:
            return
        bg = canvas.create_rectangle(
            bbox[0] - 7,
            bbox[1] - 3,
            bbox[2] + 7,
            bbox[3] + 3,
            fill="#14171c",
            outline="#2c333c",
            width=1,
        )
        canvas.tag_lower(bg, shadows[0] if shadows else item)

    def _edge_fade(self, bx: float, width: float) -> float:
        fade = max(1.0, width * 0.14)
        if bx < fade:
            t = max(0.0, bx / fade)
        elif bx > width - fade:
            t = max(0.0, (width - bx) / fade)
        else:
            return 1.0
        return t * t * (3.0 - 2.0 * t)

    def _make_wave_image(self, width: int, height: int):
        if width < 8 or height < 8:
            return None
        try:
            from PIL import Image, ImageDraw, ImageTk
        except Exception:
            return None
        im = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(im)
        bar_w = 3
        mid = height / 2.0
        for bx, amp in self._bars:
            if bx + bar_w < 0 or bx > width:
                continue
            edge = self._edge_fade(float(bx), float(width))
            if edge < 0.04:
                continue
            h = max(4.0, min(1.0, float(amp)) * height * 0.6) * (0.2 + 0.8 * edge)
            if h < 1.5:
                continue
            by = mid - h / 2.0
            shade = 0.30 + min(1.0, float(amp)) * 0.70
            gray = int(184 + 40 * shade)
            gray = max(80, min(230, gray))
            alpha = int(255 * edge)
            x0 = int(round(bx))
            y0 = int(round(by))
            x1 = max(x0 + 1, int(round(bx + bar_w)))
            y1 = max(y0 + 1, int(round(by + h)))
            box = [x0, y0, x1, y1]
            fill = (gray, gray, gray, alpha)
            try:
                draw.rounded_rectangle(box, radius=1, fill=fill)
            except Exception:
                draw.rectangle(box, fill=fill)
        keyed = _flatten_to_chroma(im)
        photo = ImageTk.PhotoImage(keyed, master=self.window)
        self._wave_image = photo
        return photo

    def _draw_waves(self, x: float, y: float, width: float, height: float) -> None:
        if not wave_allowed(live=self.live, hint=self.hint, mic_missing=self.mic_missing):
            return
        photo = self._make_wave_image(max(8, int(round(width))), max(8, int(round(height))))
        if photo is not None:
            self._canvas.create_image(x, y, image=photo, anchor="nw")
            return
        bar_w = 3.0
        mid = y + height / 2.0
        for bx, amp in self._bars:
            if bx + bar_w < 0 or bx > width:
                continue
            edge = self._edge_fade(float(bx), float(width))
            if edge < 0.04:
                continue
            h = max(4.0, min(1.0, float(amp)) * height * 0.6) * (0.2 + 0.8 * edge)
            if h < 1.5:
                continue
            by = mid - h / 2.0
            if edge < 0.12:
                color = _CHROMA
            else:
                shade = 0.30 + min(1.0, float(amp)) * 0.70
                gray = int(184 + 40 * shade)
                gray = max(80, min(230, gray))
                color = f"#{gray:02x}{gray:02x}{gray:02x}"
            self._canvas.create_rectangle(
                x + bx,
                by,
                x + bx + bar_w,
                by + h,
                outline="",
                fill=color,
            )


def _draw_mascot(overlay: Overlay) -> float:
    return overlay._draw_mascot()


def _draw_status(overlay: Overlay, x, y, width, height) -> None:
    overlay._draw_status(x, y, width, height)


def _draw_waves(overlay: Overlay, x, y, width, height) -> None:
    overlay._draw_waves(x, y, width, height)


def _draw_scene(overlay: Overlay) -> None:
    _draw_mascot(overlay)
    _draw_status(overlay, 0, 0, 0, 0)
    _draw_waves(overlay, 0, 0, 0, 0)


def run_demo(seconds: float = 8.0) -> None:
    overlay = Overlay()
    overlay.show_listening()
    overlay.set_live(True)
    started = time.monotonic()

    def tick() -> None:
        elapsed = time.monotonic() - started
        if elapsed > seconds:
            overlay.hide()
            overlay.window.quit()
            return
        env = 0.5 + 0.5 * math.sin(elapsed * 3.1)
        speak = abs(math.sin(elapsed * 1.3)) > 0.15
        level = (0.02 + 0.09 * env) if speak else 0.004
        bands = [
            abs(math.sin(elapsed * 2.2 + i * 0.45)) * (env if speak else 0.12)
            for i in range(12)
        ]
        samples = [
            (0.35 * env * math.sin(elapsed * 28 + i * 0.31) if speak else 0.004 * math.sin(i))
            for i in range(WAVE_BARS)
        ]
        overlay.set_levels(level, bands, samples)
        overlay.window.after(16, tick)

    overlay.window.after(16, tick)
    overlay.window.mainloop()


if __name__ == "__main__":
    run_demo()
