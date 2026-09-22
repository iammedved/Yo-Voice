"""Notification-area icon so the frozen daemon stays visibly resident."""

from __future__ import annotations

import ctypes
import logging
import sys
import threading
import time
from collections.abc import Callable
from ctypes import wintypes

from yo.winapi import WM_CONTEXTMENU, WM_LBUTTONUP, WM_RBUTTONUP, cursor_pos, user32

log = logging.getLogger("yo.tray")

TIP = "Ёхо"
ITEM_SETTINGS = "Настройки"
ITEM_LOG = "Открыть журнал"
ITEM_QUIT = "Выход"

ID_SETTINGS = 1001
ID_LOG = 1002
ID_QUIT = 1003

NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2
NIM_SETVERSION = 4
NOTIFYICON_VERSION_4 = 4
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010
NIF_SHOWTIP = 0x00000080
NIF_REALTIME = 0x00000040
NIIF_INFO = 0x00000001
NIIF_NOSOUND = 0x00000010
NIIF_RESPECT_QUIET_TIME = 0x00000080
NIN_SELECT = 0x0400
NIN_KEYSELECT = 0x0401
NIN_BALLOONSHOW = 0x0402
NIN_BALLOONHIDE = 0x0403
NIN_BALLOONTIMEOUT = 0x0404
NIN_BALLOONUSERCLICK = 0x0405
WM_LBUTTONDBLCLK = 0x0203
WM_NULL = 0x0000
INTRO_BALLOON = "Ёхо в трее. Нажмите ё, чтобы говорить."
_BALLOON_EVENTS = frozenset(
    (NIN_BALLOONSHOW, NIN_BALLOONHIDE, NIN_BALLOONTIMEOUT, NIN_BALLOONUSERCLICK)
)


def is_balloon_event(event: int) -> bool:
    return int(event) in _BALLOON_EVENTS


def is_tray_toggle_event(event: int) -> bool:
    if is_balloon_event(event):
        return False
    return int(event) in (WM_LBUTTONUP, WM_LBUTTONDBLCLK, NIN_SELECT, NIN_KEYSELECT)


def is_tray_menu_event(event: int) -> bool:
    if is_balloon_event(event):
        return False
    return int(event) in (WM_RBUTTONUP, WM_CONTEXTMENU)
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
LR_DEFAULTSIZE = 0x0040
IDI_APPLICATION = 32512
MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
TPM_RIGHTBUTTON = 0x0002
TPM_BOTTOMALIGN = 0x0020
TPM_RETURNCMD = 0x0100

shell32 = ctypes.WinDLL("shell32", use_last_error=True)


class GUID(ctypes.Structure):
    _fields_ = (
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    )


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = (
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    )


user32.LoadImageW.argtypes = (
    wintypes.HINSTANCE,
    wintypes.LPCWSTR,
    wintypes.UINT,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
)
user32.LoadImageW.restype = wintypes.HANDLE
user32.LoadIconW.argtypes = (wintypes.HINSTANCE, wintypes.LPCWSTR)
user32.LoadIconW.restype = wintypes.HICON
user32.DestroyIcon.argtypes = (wintypes.HICON,)
user32.DestroyIcon.restype = wintypes.BOOL
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.argtypes = (wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR)
user32.AppendMenuW.restype = wintypes.BOOL
user32.DestroyMenu.argtypes = (wintypes.HMENU,)
user32.DestroyMenu.restype = wintypes.BOOL
user32.TrackPopupMenu.argtypes = (
    wintypes.HMENU,
    wintypes.UINT,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    ctypes.c_void_p,
)
user32.TrackPopupMenu.restype = ctypes.c_int
user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
user32.SetForegroundWindow.restype = wintypes.BOOL
shell32.Shell_NotifyIconW.argtypes = (wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW))
shell32.Shell_NotifyIconW.restype = wintypes.BOOL
shell32.ExtractIconExW.argtypes = (
    wintypes.LPCWSTR,
    ctypes.c_int,
    ctypes.POINTER(wintypes.HICON),
    ctypes.POINTER(wintypes.HICON),
    wintypes.UINT,
)
shell32.ExtractIconExW.restype = wintypes.UINT


def _makeintresource(value: int) -> wintypes.LPCWSTR:
    return ctypes.cast(value, wintypes.LPCWSTR)


def _load_icon() -> tuple[object, bool]:
    from yo.paths import assets_dir

    ico = assets_dir() / "yo-voice.ico"
    if ico.is_file():
        handle = user32.LoadImageW(None, str(ico), IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
        if handle:
            return handle, True
    large = wintypes.HICON()
    small = wintypes.HICON()
    count = shell32.ExtractIconExW(sys.executable, 0, ctypes.byref(large), ctypes.byref(small), 1)
    if count:
        if small:
            if large:
                user32.DestroyIcon(large)
            return small, True
        if large:
            return large, True
    shared = user32.LoadIconW(None, _makeintresource(IDI_APPLICATION))
    return shared, False


class TrayIcon:
    def __init__(
        self,
        on_settings: Callable[[], object] | None = None,
        on_open_log: Callable[[], object] | None = None,
        on_quit: Callable[[], object] | None = None,
        on_toggle: Callable[[], object] | None = None,
    ) -> None:
        self.on_settings = on_settings
        self.on_open_log = on_open_log
        self.on_quit = on_quit
        self.on_toggle = on_toggle
        self._hwnd = None
        self._icon = None
        self._icon_owned = False
        self._added = False
        self._callback_msg = 0
        self._balloon_pending = False
        self._balloon_text = ""
        self._clear_timer: threading.Timer | None = None
        self._pending: list[int] = []
        self._flush_armed = False
        self._menu_busy = False
        self._suppress_until = 0.0

    def start(self, *, balloon: bool = False) -> None:
        if self._added:
            return
        from yo.loop_win import WM_TRAYICON, message_hwnd, set_tray_handler, set_tray_restore

        hwnd = message_hwnd()
        if not hwnd:
            log.warning("нет окна цикла для трея")
            return
        self._hwnd = hwnd
        self._callback_msg = WM_TRAYICON
        set_tray_handler(self._on_tray)
        set_tray_restore(self.restore)
        self._icon, self._icon_owned = _load_icon()
        if not self._notify(NIM_ADD, balloon=False):
            # Icon may already exist after explorer restart; keep the handle.
            self._notify(NIM_MODIFY, balloon=False)
        self._set_version()
        self._added = True
        if balloon:
            self.show_message(INTRO_BALLOON)

    def restore(self) -> None:
        """Re-add the icon after Explorer restart. Never replay the welcome toast."""
        self._added = False
        self._balloon_pending = False
        self.start(balloon=False)

    def stop(self) -> None:
        timer = self._clear_timer
        self._clear_timer = None
        if timer is not None:
            try:
                timer.cancel()
            except Exception:
                pass
        try:
            from yo.loop_win import set_tray_handler, set_tray_restore

            set_tray_handler(None)
            set_tray_restore(None)
        except Exception:
            pass
        if self._added:
            self._notify(NIM_DELETE)
            self._added = False
        self._hwnd = None
        if self._icon_owned and self._icon:
            try:
                user32.DestroyIcon(self._icon)
            except Exception:
                pass
        self._icon = None
        self._icon_owned = False

    def _nid(self, flags: int, balloon: bool, info: str | None = None) -> NOTIFYICONDATAW:
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = flags
        nid.uCallbackMessage = self._callback_msg
        nid.hIcon = self._icon
        nid.szTip = TIP[:127]
        # NIF_INFO with empty szInfo is the documented dismiss, but on Win11
        # that re-queues the last toast (hide → show). Only set NIF_INFO when
        # there is a real body. Never default missing info back to INTRO.
        text = "" if info is None else str(info)
        if balloon and text:
            nid.uFlags |= NIF_INFO | NIF_REALTIME
            nid.szInfo = text[:255]
            nid.szInfoTitle = TIP[:63]
            nid.dwInfoFlags = NIIF_INFO | NIIF_NOSOUND | NIIF_RESPECT_QUIET_TIME
        return nid

    def _notify(self, action: int, balloon: bool = False, info: str | None = None) -> bool:
        if not self._hwnd:
            return False
        flags = NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_SHOWTIP
        nid = self._nid(flags, balloon=balloon, info=info)
        return bool(shell32.Shell_NotifyIconW(action, ctypes.byref(nid)))

    def _set_version(self) -> None:
        if not self._hwnd:
            return
        nid = self._nid(NIF_MESSAGE | NIF_ICON | NIF_TIP, balloon=False)
        nid.uVersion = NOTIFYICON_VERSION_4
        shell32.Shell_NotifyIconW(NIM_SETVERSION, ctypes.byref(nid))

    def show_message(self, text: str) -> None:
        if not self._added:
            return
        body = str(text or "")
        if not body:
            self._clear_balloon()
            return
        if self._balloon_pending and self._balloon_text == body:
            return
        self._balloon_text = body
        self._balloon_pending = True
        self._notify(NIM_MODIFY, balloon=True, info=body)
        self._arm_clear()

    def _arm_clear(self) -> None:
        timer = self._clear_timer
        if timer is not None:
            try:
                timer.cancel()
            except Exception:
                pass
        timer = threading.Timer(8.0, self._clear_balloon)
        timer.daemon = True
        self._clear_timer = timer
        timer.start()

    def _clear_balloon(self) -> None:
        timer = self._clear_timer
        self._clear_timer = None
        if timer is not None:
            try:
                timer.cancel()
            except Exception:
                pass
        self._balloon_pending = False
        self._balloon_text = ""
        # Do not Shell_NotifyIcon(NIF_INFO) here: Win11 replays the last toast.

    def _on_tray(self, event: int) -> None:
        if is_balloon_event(event):
            if event != NIN_BALLOONSHOW:
                self._clear_balloon()
            return
        if self._menu_busy or time.monotonic() < self._suppress_until:
            return
        if is_tray_menu_event(event) or is_tray_toggle_event(event):
            self._pending.append(int(event))
            self._arm_flush()

    def _arm_flush(self) -> None:
        if self._flush_armed:
            return
        self._flush_armed = True
        try:
            from yo.loop import tk_root

            tk_root().after(0, self._flush)
        except Exception:
            self._flush()

    def _flush(self) -> None:
        self._flush_armed = False
        pending = self._pending
        self._pending = []
        if self._menu_busy or time.monotonic() < self._suppress_until:
            return
        if any(is_tray_menu_event(e) for e in pending):
            self._menu_busy = True
            try:
                self._popup()
            finally:
                self._menu_busy = False
                self._suppress_until = time.monotonic() + 0.4
                self._pending.clear()
            return
        if any(is_tray_toggle_event(e) for e in pending) and self.on_toggle is not None:
            self._suppress_until = time.monotonic() + 0.25
            try:
                self.on_toggle()
            except Exception:
                log.exception("ошибка клика по трею")

    def _popup(self) -> None:
        if not self._hwnd:
            return
        menu = user32.CreatePopupMenu()
        if not menu:
            return
        try:
            user32.AppendMenuW(menu, MF_STRING, ID_SETTINGS, ITEM_SETTINGS)
            user32.AppendMenuW(menu, MF_STRING, ID_LOG, ITEM_LOG)
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(menu, MF_STRING, ID_QUIT, ITEM_QUIT)
            x, y = cursor_pos()
            user32.SetForegroundWindow(self._hwnd)
            cmd = int(
                user32.TrackPopupMenu(
                    menu,
                    TPM_RIGHTBUTTON | TPM_BOTTOMALIGN | TPM_RETURNCMD,
                    int(x),
                    int(y),
                    0,
                    self._hwnd,
                    None,
                )
            )
            user32.PostMessageW(self._hwnd, WM_NULL, 0, 0)
        finally:
            user32.DestroyMenu(menu)
        action = {
            ID_SETTINGS: self.on_settings,
            ID_LOG: self.on_open_log,
            ID_QUIT: self.on_quit,
        }.get(cmd)
        if action is None:
            return
        try:
            action()
        except Exception:
            log.exception("ошибка пункта меню трея")
