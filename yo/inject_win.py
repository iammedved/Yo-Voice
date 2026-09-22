"""Вставка текста в активное поле через буфер и Ctrl+V / Ctrl+Shift+V (Windows)."""

from __future__ import annotations

import ctypes
import logging
import time
from ctypes import wintypes
from pathlib import Path

from yo.winapi import (
    allow_set_foreground,
    focused_hwnd,
    hwnd_int as _hwnd_int,
    is_same_or_child,
    window_label,
    window_root,
)

log = logging.getLogger("yo.inject")

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_V = 0x56
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
GA_ROOT = 2
GA_ROOTOWNER = 3
WM_PASTE = 0x0302

TERMINAL_EXES = {
    "windowsterminal.exe",
    "windowsterminalpreview.exe",
    "openconsole.exe",
    "wt.exe",
    "wt",
}
TERMINAL_HINTS = (
    "windowsterminal.exe",
    "windowsterminalpreview.exe",
    "windows terminal",
    "openconsole",
)
TERMINAL_CLASSES = {
    "cascadia_hosting_window_class",
    "pseudoconsolewindow",
}
CONSOLE_CLASSES = {"consolewindowclass"}
CONSOLE_EXES = {"powershell.exe", "conhost.exe", "cmd.exe", "pwsh.exe"}
KEY_EVENT = 0x0001
STD_INPUT_HANDLE = 0xFFFFFFF6  # (DWORD)-10
# Desktop / tray / lock surfaces that ignore Ctrl+V and WM_PASTE.
SHELL_JUNK_CLASSES = {
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
NATIVE_EDIT_CLASSES = {
    "edit",
    "richedit",
    "richedit20a",
    "richedit20w",
    "richedit50w",
    "richeditd2dpt",
}
_STUCK_MODIFIER_VKS = (VK_CONTROL, VK_SHIFT, 0x12, 0x5B, 0x5C)

ULONG_PTR = ctypes.c_size_t

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )


class _INPUTUNION(ctypes.Union):
    _fields_ = (
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    )


class INPUT(ctypes.Structure):
    _fields_ = (
        ("type", wintypes.DWORD),
        ("union", _INPUTUNION),
    )


class _UCHAR(ctypes.Union):
    _fields_ = (("UnicodeChar", wintypes.WCHAR), ("AsciiChar", ctypes.c_char))


class KEY_EVENT_RECORD(ctypes.Structure):
    _fields_ = (
        ("bKeyDown", wintypes.BOOL),
        ("wRepeatCount", wintypes.WORD),
        ("wVirtualKeyCode", wintypes.WORD),
        ("wVirtualScanCode", wintypes.WORD),
        ("uChar", _UCHAR),
        ("dwControlKeyState", wintypes.DWORD),
    )


class INPUT_RECORD(ctypes.Structure):
    class _EVENT(ctypes.Union):
        _fields_ = (("KeyEvent", KEY_EVENT_RECORD),)

    _anonymous_ = ("Event",)
    _fields_ = (("EventType", wintypes.WORD), ("Event", _EVENT))


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.GetCurrentProcessId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.AttachThreadInput.restype = wintypes.BOOL
user32.GetFocus.restype = wintypes.HWND
user32.PostMessageW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.PostMessageW.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.LockSetForegroundWindow.argtypes = [wintypes.UINT]
user32.LockSetForegroundWindow.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.BringWindowToTop.restype = wintypes.BOOL
user32.SetFocus.argtypes = [wintypes.HWND]
user32.SetFocus.restype = wintypes.HWND
user32.GetFocus.restype = wintypes.HWND
kernel32.SetLastError.argtypes = [wintypes.DWORD]
kernel32.SetLastError.restype = None
kernel32.AttachConsole.argtypes = [wintypes.DWORD]
kernel32.AttachConsole.restype = wintypes.BOOL
kernel32.FreeConsole.argtypes = []
kernel32.FreeConsole.restype = wintypes.BOOL
kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
kernel32.GetStdHandle.restype = wintypes.HANDLE
kernel32.WriteConsoleInputW.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(INPUT_RECORD),
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.WriteConsoleInputW.restype = wintypes.BOOL
user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = wintypes.SHORT


def _key_event(vk: int, flags: int = 0) -> INPUT:
    try:
        scan = int(user32.MapVirtualKeyW(vk, 0) or 0)
    except Exception:
        scan = 0
    event = INPUT()
    event.type = INPUT_KEYBOARD
    event.union.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    return event


def _process_exe(hwnd: int) -> str:
    if not hwnd:
        return ""
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return Path(buf.value).name.lower()
        return ""
    finally:
        kernel32.CloseHandle(handle)


def _window_text(hwnd: int) -> str:
    if not hwnd:
        return ""
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value.lower()


def _window_class(hwnd: int) -> str:
    if not hwnd:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value.lower()


def _is_native_edit_class(klass: str) -> bool:
    k = (klass or "").lower()
    return k in NATIVE_EDIT_CLASSES or k.startswith("richedit")


def is_unpasteable_hwnd(hwnd: int, overlay: int = 0) -> bool:
    """True for overlay, desktop, tray overflow, lock — not a text field."""
    handle = _hwnd_int(hwnd)
    if not handle:
        return True
    ov = _hwnd_int(overlay)
    if ov and (handle == ov or is_same_or_child(handle, ov)):
        return True
    klass = _window_class(handle)
    if _is_native_edit_class(klass):
        return False
    root = window_root(handle)
    root_klass = _window_class(root) if root else ""
    if klass in SHELL_JUNK_CLASSES or root_klass in SHELL_JUNK_CLASSES:
        return True
    if klass == "syslistview32":
        return True
    blob = f"{klass} {root_klass}"
    if "overflowxamlisland" in blob or "notifyiconoverflow" in blob:
        return True
    exe = _process_exe(handle)
    if exe == "lockapp.exe":
        return True
    if exe == "explorer.exe" and ("inputsite" in klass or "inputsite" in root_klass):
        return True
    if klass in ("tktoplevel", "tkchild"):
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
        if pid.value and pid.value == kernel32.GetCurrentProcessId():
            return True
    return False


def usable_paste_target(hwnd: int | None, overlay: int = 0) -> int:
    handle = _hwnd_int(hwnd)
    if not handle:
        return 0
    try:
        if not user32.IsWindow(handle):
            return 0
    except Exception:
        return 0
    if is_unpasteable_hwnd(handle, overlay):
        return 0
    return handle


def choose_paste_hwnd(saved: int, live: int, overlay: int = 0) -> tuple[int, str]:
    """Снимок слушания важнее чужого окна. Живой фокус — только то же окно."""
    target = usable_paste_target(saved, overlay)
    current = usable_paste_target(live, overlay)
    if target and current and target != current:
        try:
            same = window_root(current) == window_root(target)
        except Exception:
            same = False
        if same:
            return current, "same-root"
        return target, "keep-snapshot"
    if target:
        return target, "snapshot"
    if current:
        return current, "live-fallback"
    return 0, "none"


def _related_hwnds(hwnd: int) -> list[int]:
    seen: list[int] = []
    for getter in (
        lambda h: h,
        lambda h: _hwnd_int(user32.GetAncestor(h, GA_ROOT)),
        lambda h: _hwnd_int(user32.GetAncestor(h, GA_ROOTOWNER)),
    ):
        try:
            value = _hwnd_int(getter(hwnd))
        except Exception:
            continue
        if value and value not in seen:
            seen.append(value)
    return seen


class Injector:
    def paste(self, hwnd: int | None = None, overlay_hwnd: int | None = None) -> None:
        time.sleep(0.04)
        overlay = _hwnd_int(overlay_hwnd)
        saved = _hwnd_int(hwnd)
        live = self._live_target(overlay)
        target, reason = choose_paste_hwnd(saved, live, overlay)
        if reason == "keep-snapshot":
            log.info(
                "оставляю снимок hwnd=%s %s, активное окно другое hwnd=%s %s",
                target,
                window_label(target),
                live,
                window_label(live),
            )
        elif reason == "same-root":
            log.info(
                "беру фокус того же окна hwnd=%s вместо снимка hwnd=%s",
                target,
                saved,
            )
        elif reason == "live-fallback" and saved:
            log.info(
                "цель-снимок непригодна hwnd=%s %s — беру активное окно",
                saved,
                window_label(saved),
            )
        if not target:
            log.warning("нет окна для вставки — текст остаётся в буфере")
            return
        allow_set_foreground()
        attached = self._attach_input(target)
        try:
            self._release_stuck_modifiers()
            if not self._foreground_is_target(target):
                self._focus_hwnd(target)
            else:
                try:
                    user32.SetFocus(target)
                except Exception:
                    pass
            fg_ok = self._foreground_is_target(target)
            terminal = self._is_terminal(target)
            console = self._is_classic_console(target)
            fg_now = _hwnd_int(user32.GetForegroundWindow())
            log.info(
                "вставка Ctrl+%sV в %s hwnd=%s %s fg=%s %s",
                "Shift+" if terminal else "",
                _process_exe(target) or "?",
                target,
                window_label(target),
                fg_now,
                window_label(fg_now),
            )
            sent = False
            # AttachThreadInput is only for SetForegroundWindow/SetFocus.
            # Holding it across SendInput merges Tk focus with the console,
            # so Ctrl+V lands on the withdrawn overlay instead of Grok.
            self._detach_input(attached)
            attached = []
            if fg_ok:
                if terminal:
                    sent = self._chord([VK_CONTROL, VK_SHIFT, VK_V])
                elif console:
                    sent = self._console_ctrl_v(target)
                    if not sent:
                        sent = self._chord([VK_CONTROL, VK_V])
                else:
                    sent = self._chord([VK_CONTROL, VK_V])
                if sent and overlay:
                    try:
                        fg_after = _hwnd_int(user32.GetForegroundWindow())
                        if fg_after and (
                            fg_after == overlay
                            or is_same_or_child(fg_after, overlay)
                            or window_root(fg_after) == window_root(overlay)
                        ):
                            sent = False
                            log.warning("фокус на оверлее — аккорд не дошёл")
                    except Exception:
                        pass
            else:
                log.warning(
                    "цель не на переднем плане hwnd=%s root=%s fg=%s",
                    target,
                    window_root(target),
                    fg_now,
                )
            if not sent:
                if fg_ok:
                    log.warning("SendInput не доставил клавиши err=%s", ctypes.get_last_error())
                if fg_ok or self._accepts_wm_paste(target):
                    self._wm_paste(target, overlay=overlay)
                else:
                    log.info("вставка не дошла hwnd=%s — текст в буфере", target)
        finally:
            self._detach_input(attached)

    def _live_target(self, overlay: int) -> int:
        try:
            live = focused_hwnd()
        except Exception:
            live = 0
        got = usable_paste_target(live, overlay)
        if got:
            return got
        try:
            fg = _hwnd_int(user32.GetForegroundWindow())
        except Exception:
            fg = 0
        return usable_paste_target(fg, overlay)

    def _accepts_wm_paste(self, hwnd: int) -> bool:
        return _is_native_edit_class(_window_class(hwnd))

    def _release_stuck_modifiers(self) -> None:
        ups: list[INPUT] = []
        for vk in _STUCK_MODIFIER_VKS:
            try:
                if user32.GetAsyncKeyState(vk) & 0x8000:
                    ups.append(_key_event(vk, KEYEVENTF_KEYUP))
            except Exception:
                continue
        if not ups:
            return
        arr = (INPUT * len(ups))(*ups)
        user32.SendInput(len(ups), arr, ctypes.sizeof(INPUT))

    def _attach_input(self, hwnd: int) -> list[tuple[int, int]]:
        pairs: list[tuple[int, int]] = []
        if not hwnd or not user32.IsWindow(hwnd):
            return pairs
        current = _hwnd_int(user32.GetForegroundWindow())
        pid = wintypes.DWORD(0)
        our_tid = kernel32.GetCurrentThreadId() or 0
        fg_tid = user32.GetWindowThreadProcessId(current, ctypes.byref(pid)) if current else 0
        tg_tid = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)) or 0
        if fg_tid and our_tid and fg_tid != our_tid:
            if user32.AttachThreadInput(our_tid, fg_tid, True):
                pairs.append((our_tid, fg_tid))
        if tg_tid and our_tid and tg_tid != our_tid and tg_tid != fg_tid:
            if user32.AttachThreadInput(our_tid, tg_tid, True):
                pairs.append((our_tid, tg_tid))
        return pairs

    def _detach_input(self, pairs: list[tuple[int, int]]) -> None:
        for our_tid, other in reversed(pairs):
            user32.AttachThreadInput(our_tid, other, False)

    def _focus_hwnd(self, hwnd: int) -> bool:
        if not hwnd or not user32.IsWindow(hwnd):
            return False
        try:
            if self._foreground_is_target(hwnd):
                return True
            allow_set_foreground()
            root = window_root(hwnd)
            user32.BringWindowToTop(root)
            if not user32.SetForegroundWindow(root):
                log.debug("SetForegroundWindow root=%s err=%s", root, ctypes.get_last_error())
                self._alt_unlock_foreground()
                user32.SetForegroundWindow(root)
            user32.SetFocus(hwnd)
            return self._foreground_is_target(hwnd)
        except Exception:
            log.debug("не удалось вернуть фокус hwnd=%s", hwnd, exc_info=True)
            return self._foreground_is_target(hwnd)

    def _alt_unlock_foreground(self) -> None:
        """Unlock foreground so SetForegroundWindow works after overlay hide."""
        try:
            user32.LockSetForegroundWindow(2)  # LSFW_UNLOCK
        except Exception:
            log.debug("не удалось снять блокировку переднего плана", exc_info=True)

    def _foreground_is_target(self, hwnd: int) -> bool:
        if not hwnd:
            return False
        fg = _hwnd_int(user32.GetForegroundWindow())
        if not fg:
            return False
        return window_root(fg) == window_root(hwnd)

    def _chord(self, vks: list[int]) -> bool:
        events = [_key_event(vk) for vk in vks]
        events.extend(_key_event(vk, KEYEVENTF_KEYUP) for vk in reversed(vks))
        arr = (INPUT * len(events))(*events)
        kernel32.SetLastError(0)
        n = user32.SendInput(len(events), arr, ctypes.sizeof(INPUT))
        return n == len(events)

    def _wm_paste(self, hwnd: int, overlay: int = 0) -> None:
        if not hwnd or is_unpasteable_hwnd(hwnd, overlay):
            return
        target = hwnd
        try:
            focus = _hwnd_int(user32.GetFocus())
            if focus and overlay and (focus == overlay or is_same_or_child(focus, overlay)):
                focus = 0
            if focus and (
                focus == hwnd
                or is_same_or_child(focus, hwnd)
                or is_same_or_child(hwnd, focus)
            ):
                target = focus
        except Exception:
            log.debug("не удалось взять фокус для WM_PASTE", exc_info=True)
        if not user32.PostMessageW(target, WM_PASTE, 0, 0):
            log.warning("WM_PASTE не доставлен hwnd=%s err=%s", target, ctypes.get_last_error())
        else:
            log.info("WM_PASTE hwnd=%s", target)

    def _focused_is_terminal(self) -> bool:
        return self._is_terminal(_hwnd_int(user32.GetForegroundWindow()))

    def _is_terminal(self, hwnd: int) -> bool:
        if not hwnd:
            return False
        try:
            for handle in _related_hwnds(hwnd):
                exe = _process_exe(handle)
                title = _window_text(handle)
                klass = _window_class(handle)
                if exe in TERMINAL_EXES:
                    return True
                blob = f"{exe} {title} {klass}"
                if any(hint in blob for hint in TERMINAL_HINTS):
                    return True
                if klass in TERMINAL_CLASSES:
                    return True
        except Exception:
            return False
        return False

    def _is_classic_console(self, hwnd: int) -> bool:
        if not hwnd or self._is_terminal(hwnd):
            return False
        try:
            for handle in _related_hwnds(hwnd):
                klass = _window_class(handle)
                if klass in CONSOLE_CLASSES:
                    return True
                if _process_exe(handle) in CONSOLE_EXES:
                    return True
        except Exception:
            return False
        return False

    def _console_ctrl_v(self, hwnd: int) -> bool:
        """Write clipboard text into the console input buffer as Unicode keys.

        A fake Ctrl+V chord does not run conhost's paste handler. On failure
        the caller falls back to SendInput.
        """
        if not hwnd:
            return False
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value or pid.value == kernel32.GetCurrentProcessId():
            return False
        from yo.clip_win import clipboard_get

        text = clipboard_get() or ""
        if not text or len(text) > 4000 or any(ord(ch) > 0xFFFF for ch in text):
            return False
        attached = False
        try:
            kernel32.FreeConsole()
            if not kernel32.AttachConsole(pid.value):
                log.info(
                    "AttachConsole pid=%s hwnd=%s err=%s",
                    pid.value,
                    hwnd,
                    ctypes.get_last_error(),
                )
                return False
            attached = True
            hin = kernel32.GetStdHandle(STD_INPUT_HANDLE)
            raw = int(getattr(hin, "value", hin) or 0)
            if not raw or raw in (-1, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF):
                return False
            n = len(text) * 2
            recs = (INPUT_RECORD * n)()
            for i, ch in enumerate(text):
                for down, slot in ((True, i * 2), (False, i * 2 + 1)):
                    recs[slot].EventType = KEY_EVENT
                    recs[slot].KeyEvent.bKeyDown = down
                    recs[slot].KeyEvent.wRepeatCount = 1
                    recs[slot].KeyEvent.wVirtualKeyCode = 0
                    recs[slot].KeyEvent.wVirtualScanCode = 0
                    recs[slot].KeyEvent.uChar.UnicodeChar = ch
                    recs[slot].KeyEvent.dwControlKeyState = 0
            written = wintypes.DWORD(0)
            if not kernel32.WriteConsoleInputW(hin, recs, n, ctypes.byref(written)):
                log.info(
                    "WriteConsoleInput hwnd=%s err=%s",
                    hwnd,
                    ctypes.get_last_error(),
                )
                return False
            ok = int(written.value or 0) >= n
            if ok:
                log.info(
                    "консольная вставка Unicode hwnd=%s pid=%s символов=%s",
                    hwnd,
                    pid.value,
                    len(text),
                )
            return ok
        except Exception:
            log.debug("консольная вставка не удалась hwnd=%s", hwnd, exc_info=True)
            return False
        finally:
            if attached:
                try:
                    kernel32.FreeConsole()
                except Exception:
                    pass
