"""Глобальный перехват одной кнопки: клавиша или мышь, Win32.

RegisterHotKey would swallow the key even with Shift held, so Shift+ё
could not type Ё. A low-level keyboard hook (no admin) eats only the
unmodified bind; modifiers pass through. Mouse binds use WH_MOUSE_LL.
"""

from __future__ import annotations

import ctypes
import logging
import threading
import time
from collections.abc import Callable
from ctypes import wintypes

from yo.bind import OVERLAY_UI_BUTTONS, ToggleBind, accept_capture_event, normalize_bind
from yo.winapi import hwnd_int

log = logging.getLogger("yo.hotkey")

X11_GRAVE_KEYCODE = 49
VK_OEM_3 = 0xC0
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_LWIN = 0x5B
VK_RWIN = 0x5C

WM_QUIT = 0x0012
WM_APP = 0x8000
WM_YO_KEY = WM_APP + 2
WM_YO_MOUSE = WM_APP + 1
WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
HC_ACTION = 0
PM_NOREMOVE = 0
LLKHF_INJECTED = 0x10

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONDBLCLK = 0x0206
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONDBLCLK = 0x0209
WM_XBUTTONDOWN = 0x020B
WM_XBUTTONUP = 0x020C
WM_XBUTTONDBLCLK = 0x020D
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_MBUTTONUP = 0x0208
XBUTTON1 = 0x0001
XBUTTON2 = 0x0002
GA_ROOT = 2

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class POINT(ctypes.Structure):
    _fields_ = (("x", wintypes.LONG), ("y", wintypes.LONG))


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = (
        ("pt", POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = (
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class MSG(ctypes.Structure):
    _fields_ = (
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", POINT),
    )


user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = ctypes.c_int
user32.PeekMessageW.argtypes = [
    ctypes.POINTER(MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
    wintypes.UINT,
]
user32.PeekMessageW.restype = wintypes.BOOL
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL
user32.WindowFromPoint.argtypes = [POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = wintypes.SHORT
user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.GetKeyNameTextW.argtypes = [ctypes.c_long, wintypes.LPWSTR, ctypes.c_int]
user32.GetKeyNameTextW.restype = ctypes.c_int
user32.MsgWaitForMultipleObjects.argtypes = [
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.BOOL,
    wintypes.DWORD,
    wintypes.DWORD,
]
user32.MsgWaitForMultipleObjects.restype = wintypes.DWORD
user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
user32.TranslateMessage.restype = wintypes.BOOL
user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.restype = LRESULT
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

MODIFIER_VKS = {
    VK_SHIFT,
    VK_CONTROL,
    VK_MENU,
    VK_LWIN,
    VK_RWIN,
    0x14,
    0x90,
    0x91,
    0xA0,
    0xA1,
    0xA2,
    0xA3,
    0xA4,
    0xA5,
}


def vk_from_code(code: int) -> int:
    """Map ToggleBind key code to a Win32 virtual-key.

    Linux stores X11 keycode 49 for ё/grave; that must become VK_OEM_3.
    Other values below 256 are used as virtual-key codes as-is.
    """
    n = int(code)
    if n == X11_GRAVE_KEYCODE:
        return VK_OEM_3
    if 0 < n < 256:
        return n
    return n & 0xFF


def _mods_down() -> bool:
    for vk in (VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN):
        if user32.GetAsyncKeyState(vk) & 0x8000:
            return True
    return False


def _xbutton_code(mouse_data: int) -> int | None:
    xb = (int(mouse_data) >> 16) & 0xFFFF
    if xb == XBUTTON1:
        return 8
    if xb == XBUTTON2:
        return 9
    if xb:
        return 7 + xb
    return None


def _button_from_ll(wparam: int, lparam: int) -> int | None:
    message = int(wparam)
    if message in (WM_LBUTTONDOWN, WM_LBUTTONDBLCLK):
        return 1
    if message in (WM_MBUTTONDOWN, WM_MBUTTONDBLCLK):
        return 2
    if message in (WM_RBUTTONDOWN, WM_RBUTTONDBLCLK):
        return 3
    if message in (WM_XBUTTONDOWN, WM_XBUTTONDBLCLK):
        info = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
        return _xbutton_code(info.mouseData)
    return None


def _button_up_from_ll(wparam: int, lparam: int) -> int | None:
    message = int(wparam)
    if message == WM_LBUTTONUP:
        return 1
    if message == WM_MBUTTONUP:
        return 2
    if message == WM_RBUTTONUP:
        return 3
    if message == WM_XBUTTONUP:
        info = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
        return _xbutton_code(info.mouseData)
    return None


def handlers_for_binds(
    binds: list[tuple[ToggleBind, Callable[[], None]]],
) -> dict[tuple[str, int], Callable[[], None]]:
    """Index watchers by the VK/button actually hooked.

    Stored X11 49 (ё) becomes VK_OEM_3. Digit `1` is also VK 49, so we must
    not also index the raw 49 — that would fire PTT on both ё and 1.
    """
    out: dict[tuple[str, int], Callable[[], None]] = {}
    for bind, cb in binds:
        if bind.kind == "key":
            out[("key", vk_from_code(bind.code))] = cb
        else:
            out[(bind.kind, bind.code)] = cb
    return out


class HotkeyWatcher(threading.Thread):
    def __init__(
        self,
        bind: ToggleBind | int | None = None,
        on_press: Callable[[], None] | None = None,
        *,
        binds: list[tuple[ToggleBind, Callable[[], None]]] | None = None,
        overlay_xid_fn: Callable[[], int | None] | None = None,
    ) -> None:
        super().__init__(daemon=True, name="yo-hotkey")
        if binds is None:
            if bind is None or on_press is None:
                raise ValueError("bind and on_press are required")
            if isinstance(bind, int):
                bind = normalize_bind("key", bind)
            binds = [(bind, on_press)]
        self.binds = list(binds)
        self.bind = self.binds[0][0]
        self.keycode = self.bind.code
        self.kind = self.bind.kind
        self.on_press = self.binds[0][1]
        self._overlay_xid_fn = overlay_xid_fn
        self._running = True
        self.grabbed = False
        self.error: str | None = None
        self._tid = 0
        self._ready = threading.Event()
        self._khook = None
        self._mhook = None
        self._kproc = None
        self._mproc = None
        self._keys_down: set[int] = set()
        self._handlers: dict[tuple[str, int], Callable[[], None]] = handlers_for_binds(self.binds)

    def stop(self) -> None:
        self._running = False
        tid = self._tid
        if not tid:
            self._ready.wait(timeout=1.0)
            tid = self._tid
        if tid:
            user32.PostThreadMessageW(tid, WM_QUIT, 0, 0)
        if threading.current_thread() is not self and self.is_alive():
            self.join(timeout=1.5)

    def _ungrab(self) -> None:
        for hook in (self._khook, self._mhook):
            if hook:
                try:
                    user32.UnhookWindowsHookEx(hook)
                except Exception:
                    pass
        self._khook = None
        self._mhook = None
        self._kproc = None
        self._mproc = None
        self.grabbed = False

    def can_replace(self, binds: list[tuple[ToggleBind, Callable[[], None]]]) -> bool:
        if not self.is_alive() or not self.grabbed:
            return False
        need_key = any(bind.kind != "button" for bind, _cb in binds)
        need_mouse = any(bind.kind == "button" for bind, _cb in binds)
        return bool(self._khook) == need_key and bool(self._mhook) == need_mouse

    def replace_binds(self, binds: list[tuple[ToggleBind, Callable[[], None]]]) -> None:
        """Swap the watched key/button without tearing down the hook thread."""
        self.binds = list(binds)
        self.bind = self.binds[0][0]
        self.keycode = self.bind.code
        self.kind = self.bind.kind
        self.on_press = self.binds[0][1]
        self._handlers = handlers_for_binds(self.binds)

    def _handler_for_key(self, vk: int) -> Callable[[], None] | None:
        return self._handlers.get(("key", int(vk)))

    def run(self) -> None:
        self._tid = int(kernel32.GetCurrentThreadId())
        msg = MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_NOREMOVE)

        self._handlers = handlers_for_binds(self.binds)
        key_binds = [(bind, cb) for bind, cb in self.binds if bind.kind != "button"]
        mouse_binds = [(bind, cb) for bind, cb in self.binds if bind.kind == "button"]

        try:
            if key_binds:
                self._kproc = HOOKPROC(self._keyboard_hook)
                self._khook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._kproc, None, 0)
                if not self._khook:
                    raise OSError(ctypes.get_last_error())
            if mouse_binds:
                self._mproc = HOOKPROC(self._mouse_hook)
                self._mhook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._mproc, None, 0)
                if not self._mhook:
                    raise OSError(ctypes.get_last_error())
            self.grabbed = True
        except OSError:
            self.error = "клавиша уже занята другим приложением"
            log.error("%s", self.error)
            self._ungrab()
            self._ready.set()
            return

        self._ready.set()
        last = 0.0
        try:
            while self._running:
                result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if result == 0 or result == -1:
                    break
                if msg.message == WM_YO_KEY:
                    cb = self._handler_for_key(int(msg.wParam))
                    if cb is None:
                        continue
                elif msg.message == WM_YO_MOUSE:
                    code = int(msg.wParam)
                    cb = self._handlers.get(("button", code))
                    if cb is None:
                        continue
                    if code in OVERLAY_UI_BUTTONS and self._hits_overlay():
                        continue
                else:
                    continue
                now = time.monotonic()
                if now - last < 0.35:
                    continue
                last = now
                try:
                    cb()
                except Exception:
                    log.exception("ошибка обработки горячей клавиши")
        finally:
            self._ungrab()

    def _keyboard_hook(self, ncode: int, wparam: int, lparam: int) -> int:
        try:
            if ncode == HC_ACTION:
                info = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if info.flags & LLKHF_INJECTED:
                    return int(user32.CallNextHookEx(self._khook, ncode, wparam, lparam))
                vk = int(info.vkCode)
                if vk in MODIFIER_VKS:
                    return int(user32.CallNextHookEx(self._khook, ncode, wparam, lparam))
                if _mods_down():
                    return int(user32.CallNextHookEx(self._khook, ncode, wparam, lparam))
                cb = self._handler_for_key(vk)
                if cb is not None:
                    message = int(wparam)
                    if message in (WM_KEYDOWN, WM_SYSKEYDOWN):
                        if vk in self._keys_down:
                            return 1
                        self._keys_down.add(vk)
                        if self._tid:
                            user32.PostThreadMessageW(self._tid, WM_YO_KEY, vk, 0)
                    elif message in (WM_KEYUP, WM_SYSKEYUP):
                        self._keys_down.discard(vk)
                    if message in (WM_KEYDOWN, WM_SYSKEYDOWN, WM_KEYUP, WM_SYSKEYUP):
                        return 1
        except Exception:
            log.exception("ошибка keyboard hook")
        return int(user32.CallNextHookEx(self._khook, ncode, wparam, lparam))

    def _mouse_hook(self, ncode: int, wparam: int, lparam: int) -> int:
        if ncode == HC_ACTION and self._tid:
            try:
                down = _button_from_ll(int(wparam), int(lparam))
                up = _button_up_from_ll(int(wparam), int(lparam))
            except Exception:
                down, up = None, None
            if down is not None and ("button", down) in self._handlers:
                user32.PostThreadMessageW(self._tid, WM_YO_MOUSE, down, 0)
                return 1
            if up is not None and ("button", up) in self._handlers:
                return 1
        return int(user32.CallNextHookEx(self._mhook, ncode, wparam, lparam))

    def _hits_overlay(self) -> bool:
        if self._overlay_xid_fn is None:
            return False
        try:
            xid = self._overlay_xid_fn()
        except Exception:
            return False
        if not xid:
            return False
        pt = POINT()
        if not user32.GetCursorPos(ctypes.byref(pt)):
            return False
        hwnd = user32.WindowFromPoint(pt)
        target = hwnd_int(xid)
        seen: set[int] = set()
        cur = hwnd
        for _ in range(16):
            if not cur:
                break
            value = hwnd_int(cur)
            if not value or value in seen:
                break
            seen.add(value)
            if value == target:
                return True
            cur = user32.GetParent(cur)
        root = hwnd_int(user32.GetAncestor(hwnd, GA_ROOT)) if hwnd else 0
        return root == target


def vk_label(code: int) -> str:
    if int(code) in {X11_GRAVE_KEYCODE, VK_OEM_3}:
        return "ё"
    vk = vk_from_code(code)
    scan = user32.MapVirtualKeyW(vk, 0)
    buf = ctypes.create_unicode_buffer(64)
    user32.GetKeyNameTextW(scan << 16, buf, 64)
    return (buf.value or "").strip()


def capture_bind(
    on_result: Callable[[ToggleBind | None], None],
    *,
    overlay_xid: int | None = None,
    timeout_sec: float = 15.0,
) -> None:
    def worker() -> None:
        bind: ToggleBind | None = None
        try:
            bind = _grab_next_bind(overlay_xid, timeout_sec)
        except Exception:
            log.exception("не удалось перехватить новую кнопку")
        try:
            on_result(bind)
        except Exception:
            log.exception("ошибка после выбора кнопки")

    threading.Thread(target=worker, daemon=True, name="yo-rebind").start()


def _grab_next_bind(overlay_xid: int | None, timeout_sec: float) -> ToggleBind | None:
    found: list[ToggleBind] = []
    state = {"khook": None, "mhook": None, "kproc": None, "mproc": None}
    settle_until = time.monotonic() + 0.35

    def finish(bind: ToggleBind) -> None:
        if found:
            return
        found.append(bind)
        user32.PostThreadMessageW(kernel32.GetCurrentThreadId(), WM_QUIT, 0, 0)

    def keyboard_proc(ncode, wparam, lparam):
        if ncode == HC_ACTION and int(wparam) in {WM_KEYDOWN, WM_SYSKEYDOWN}:
            if time.monotonic() < settle_until:
                return user32.CallNextHookEx(state["khook"], ncode, wparam, lparam)
            info = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if not (info.flags & LLKHF_INJECTED):
                vk = int(info.vkCode)
                if vk not in MODIFIER_VKS and not _mods_down():
                    # Keep ё as X11 49 so Linux configs and KEY_LABELS stay in sync.
                    code = X11_GRAVE_KEYCODE if vk == VK_OEM_3 else vk
                    accepted = accept_capture_event(event_type="key", code=code)
                    if accepted is not None:
                        finish(accepted)
                        return 1
        return user32.CallNextHookEx(state["khook"], ncode, wparam, lparam)

    def mouse_proc(ncode, wparam, lparam):
        if ncode == HC_ACTION:
            if time.monotonic() < settle_until:
                return user32.CallNextHookEx(state["mhook"], ncode, wparam, lparam)
            code = _button_from_ll(int(wparam), int(lparam))
            if code is not None:
                pt = POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                hwnd = user32.WindowFromPoint(pt)
                overlay_hit = False
                if overlay_xid:
                    cur = hwnd
                    target = hwnd_int(overlay_xid)
                    for _ in range(16):
                        if not cur:
                            break
                        if hwnd_int(cur) == target:
                            overlay_hit = True
                            break
                        cur = user32.GetParent(cur)
                    if not overlay_hit:
                        root = hwnd_int(user32.GetAncestor(hwnd, GA_ROOT)) if hwnd else 0
                        overlay_hit = root == target
                accepted = accept_capture_event(
                    event_type="button",
                    code=code,
                    overlay_hit=overlay_hit,
                )
                if accepted is not None:
                    finish(accepted)
                    return 1
        return user32.CallNextHookEx(state["mhook"], ncode, wparam, lparam)

    state["kproc"] = HOOKPROC(keyboard_proc)
    state["mproc"] = HOOKPROC(mouse_proc)
    state["khook"] = user32.SetWindowsHookExW(WH_KEYBOARD_LL, state["kproc"], None, 0)
    state["mhook"] = user32.SetWindowsHookExW(WH_MOUSE_LL, state["mproc"], None, 0)
    if not state["khook"] or not state["mhook"]:
        if state["khook"]:
            user32.UnhookWindowsHookEx(state["khook"])
        if state["mhook"]:
            user32.UnhookWindowsHookEx(state["mhook"])
        raise OSError("SetWindowsHookEx capture")
    deadline = time.monotonic() + max(1.0, float(timeout_sec))
    msg = MSG()
    try:
        while not found and time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            user32.MsgWaitForMultipleObjects(0, None, False, max(1, int(remaining * 1000)), 0x04FF)
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                if msg.message == WM_QUIT:
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        return found[0] if found else None
    finally:
        user32.UnhookWindowsHookEx(state["khook"])
        user32.UnhookWindowsHookEx(state["mhook"])
