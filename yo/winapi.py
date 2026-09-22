"""Win32 helpers for Ёхо. ctypes only, no pywin32."""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes
from pathlib import Path

log = logging.getLogger("yo.winapi")

# CPython omits several GDI/USER handle aliases from ctypes.wintypes.
for _name in ("HCURSOR", "HICON", "HBRUSH", "HHOOK", "HINSTANCE"):
    if not hasattr(wintypes, _name):
        setattr(wintypes, _name, wintypes.HANDLE)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

ULONG_PTR = ctypes.c_size_t
LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

HWND_MESSAGE = wintypes.HWND(-3)
HWND_TOPMOST = wintypes.HWND(-1)

WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000
SWP_NOACTIVATE = 0x0010
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_SHOWWINDOW = 0x0040
SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0
AC_SRC_ALPHA = 1
BI_RGB = 0
DIB_RGB_COLORS = 0
WM_APP = 0x8000
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_QUIT = 0x0012
WM_MOUSEACTIVATE = 0x0021
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_MOUSEMOVE = 0x0200
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_XBUTTONDOWN = 0x020B
WM_XBUTTONUP = 0x020C
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_KEYUP = 0x0101
WM_SYSKEYUP = 0x0105
MA_NOACTIVATE = 3
WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
LLKHF_INJECTED = 0x10
LLMHF_INJECTED = 0x01
HC_ACTION = 0
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_CAPITAL = 0x14
VK_NUMLOCK = 0x90
VK_SCROLL = 0x91
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LMENU = 0xA4
VK_RMENU = 0xA5
VK_OEM_3 = 0xC0
VK_V = 0x56
X11_GRAVE = 49
XBUTTON1 = 0x0001
XBUTTON2 = 0x0002
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SPI_GETWORKAREA = 0x0030
PM_REMOVE = 0x0001
GA_ROOT = 2
GA_ROOTOWNER = 3

MODIFIER_VKS = frozenset(
    {
        VK_SHIFT,
        VK_CONTROL,
        VK_MENU,
        VK_LWIN,
        VK_RWIN,
        VK_CAPITAL,
        VK_NUMLOCK,
        VK_SCROLL,
        VK_LSHIFT,
        VK_RSHIFT,
        VK_LCONTROL,
        VK_RCONTROL,
        VK_LMENU,
        VK_RMENU,
    }
)

TERMINAL_EXES = (
    "windowsterminal.exe",
    "windowsterminalpreview.exe",
    "windows terminal.exe",
    "wt.exe",
    "conhost.exe",
    "alacritty.exe",
    "wezterm.exe",
    "wezterm-gui.exe",
    "windowsterminal",
)
TERMINAL_CLASSES = (
    "cascadia_hosting_window_class",
    "consolewindowclass",
    "c_terminal_win",
)


class POINT(ctypes.Structure):
    _fields_ = (("x", wintypes.LONG), ("y", wintypes.LONG))


class SIZE(ctypes.Structure):
    _fields_ = (("cx", wintypes.LONG), ("cy", wintypes.LONG))


class MSG(ctypes.Structure):
    _fields_ = (
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", POINT),
        ("lPrivate", wintypes.DWORD),
    )


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = (
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = (
        ("pt", POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


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


class INPUTUNION(ctypes.Union):
    _fields_ = (("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT))


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = (("type", wintypes.DWORD), ("union", INPUTUNION))


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = (
        ("BlendOp", ctypes.c_byte),
        ("BlendFlags", ctypes.c_byte),
        ("SourceConstantAlpha", ctypes.c_byte),
        ("AlphaFormat", ctypes.c_byte),
    )


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = (
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    )


class BITMAPINFO(ctypes.Structure):
    _fields_ = (("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3))


class WNDCLASSW(ctypes.Structure):
    _fields_ = (
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HCURSOR),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    )


class GUITHREADINFO(ctypes.Structure):
    _fields_ = (
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    )


user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetGUIThreadInfo.argtypes = (wintypes.DWORD, ctypes.POINTER(GUITHREADINFO))
user32.GetGUIThreadInfo.restype = wintypes.BOOL
user32.GetFocus.restype = wintypes.HWND
user32.SetFocus.argtypes = (wintypes.HWND,)
user32.SetFocus.restype = wintypes.HWND
user32.AllowSetForegroundWindow.argtypes = (wintypes.DWORD,)
user32.AllowSetForegroundWindow.restype = wintypes.BOOL
user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
user32.GetAncestor.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = (wintypes.HWND,)
user32.BringWindowToTop.restype = wintypes.BOOL
user32.AttachThreadInput.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
user32.AttachThreadInput.restype = wintypes.BOOL
user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetWindowTextW.restype = ctypes.c_int
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
ASFW_ANY = 0xFFFFFFFF
user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.WindowFromPoint.argtypes = (POINT,)
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetCursorPos.argtypes = (ctypes.POINTER(POINT),)
user32.GetCursorPos.restype = wintypes.BOOL
user32.SystemParametersInfoW.argtypes = (wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT)
user32.SystemParametersInfoW.restype = wintypes.BOOL
user32.GetSystemMetrics.argtypes = (ctypes.c_int,)
user32.GetSystemMetrics.restype = ctypes.c_int
user32.GetDpiForSystem.argtypes = ()
user32.GetDpiForSystem.restype = ctypes.c_uint
kernel32.SetLastError.argtypes = (wintypes.DWORD,)
kernel32.SetLastError.restype = None
user32.GetParent.argtypes = (wintypes.HWND,)
user32.GetParent.restype = wintypes.HWND
user32.IsWindow.argtypes = (wintypes.HWND,)
user32.IsWindow.restype = wintypes.BOOL
user32.PostThreadMessageW.argtypes = (wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.restype = LRESULT
user32.GetMessageW.argtypes = (ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
user32.DispatchMessageW.argtypes = (ctypes.POINTER(MSG),)
user32.DispatchMessageW.restype = LRESULT
user32.TranslateMessage.argtypes = (ctypes.POINTER(MSG),)
user32.PeekMessageW.argtypes = (ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT)
user32.PeekMessageW.restype = wintypes.BOOL
user32.MsgWaitForMultipleObjects.argtypes = (
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.BOOL,
    wintypes.DWORD,
    wintypes.DWORD,
)
user32.MsgWaitForMultipleObjects.restype = wintypes.DWORD
user32.UpdateLayeredWindow.argtypes = (
    wintypes.HWND,
    wintypes.HDC,
    ctypes.POINTER(POINT),
    ctypes.POINTER(SIZE),
    wintypes.HDC,
    ctypes.POINTER(POINT),
    wintypes.COLORREF,
    ctypes.POINTER(BLENDFUNCTION),
    wintypes.DWORD,
)
user32.UpdateLayeredWindow.restype = wintypes.BOOL
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateDIBSection.argtypes = (
    wintypes.HDC,
    ctypes.c_void_p,
    wintypes.UINT,
    ctypes.POINTER(ctypes.c_void_p),
    wintypes.HANDLE,
    wintypes.DWORD,
)
kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.GetFileType.argtypes = (wintypes.HANDLE,)
kernel32.GetFileType.restype = wintypes.DWORD
kernel32.GetStdHandle.argtypes = (wintypes.DWORD,)
kernel32.GetStdHandle.restype = wintypes.HANDLE
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
kernel32.CreateMutexW.restype = wintypes.HANDLE
user32.MessageBoxW.argtypes = (wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT)
user32.MessageBoxW.restype = ctypes.c_int
ERROR_ALREADY_EXISTS = 183
MB_OK = 0x00000000
MB_ICONERROR = 0x00000010
MB_SETFOREGROUND = 0x00010000
MB_TOPMOST = 0x00040000
user32.RegisterClassW.argtypes = (ctypes.POINTER(WNDCLASSW),)
user32.RegisterClassW.restype = wintypes.ATOM
user32.DefWindowProcW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.DefWindowProcW.restype = LRESULT
user32.CreateWindowExW.argtypes = (
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    wintypes.LPVOID,
)
user32.CreateWindowExW.restype = wintypes.HWND
user32.DestroyWindow.argtypes = (wintypes.HWND,)
user32.DestroyWindow.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = (
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
)


def message_box(text: str, title: str = "Ёхо", *, error: bool = False) -> None:
    flags = MB_ICONERROR if error else 0x00000040
    flags |= MB_OK | MB_SETFOREGROUND | MB_TOPMOST
    try:
        user32.MessageBoxW(None, str(text), str(title), flags)
    except Exception:
        pass


def set_dpi_aware() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


def system_dpi() -> int:
    try:
        dpi = int(user32.GetDpiForSystem())
        if dpi > 0:
            return dpi
    except Exception:
        pass
    return 96


def work_area() -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    if user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
        return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
    return 0, 0, int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))


def cursor_pos() -> tuple[int, int]:
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return int(pt.x), int(pt.y)


def hwnd_int(hwnd) -> int:
    """HWND/HANDLE → int. Never int(ctypes_obj): Python 3.12 uses the buffer protocol."""
    if hwnd is None or hwnd is False:
        return 0
    if isinstance(hwnd, int):
        return hwnd
    value = getattr(hwnd, "value", None)
    if isinstance(value, int):
        return value
    return 0


def window_root(hwnd) -> int:
    """Top-level ancestor. SetForegroundWindow needs a root, not an edit child."""
    handle = hwnd_int(hwnd)
    if not handle:
        return 0
    root = hwnd_int(user32.GetAncestor(handle, GA_ROOT))
    return root or handle


def focused_hwnd() -> int:
    """Foreground window, preferring the GUI thread's focus/caret child."""
    fg = hwnd_int(user32.GetForegroundWindow())
    tid = 0
    if fg:
        tid = user32.GetWindowThreadProcessId(fg, None) or 0
    if tid:
        info = GUITHREADINFO()
        info.cbSize = ctypes.sizeof(GUITHREADINFO)
        if user32.GetGUIThreadInfo(tid, ctypes.byref(info)):
            for candidate in (info.hwndFocus, info.hwndCaret, info.hwndActive):
                value = hwnd_int(candidate)
                if value:
                    return value
    return fg


def allow_set_foreground() -> None:
    try:
        user32.AllowSetForegroundWindow(ASFW_ANY)
    except Exception:
        pass


def window_label(hwnd: int) -> str:
    if not hwnd:
        return ""
    klass = class_name(hwnd)
    buf = ctypes.create_unicode_buffer(256)
    try:
        user32.GetWindowTextW(hwnd, buf, 256)
    except Exception:
        return klass
    title = (buf.value or "").strip()
    if klass and title:
        return f"{klass} {title}"
    return klass or title


def window_from_point(x: int, y: int) -> int:
    return hwnd_int(user32.WindowFromPoint(POINT(x, y)))


def is_same_or_child(hwnd: int, ancestor: int) -> bool:
    if not hwnd or not ancestor:
        return False
    cur = hwnd_int(hwnd)
    target = hwnd_int(ancestor)
    for _ in range(16):
        if not cur:
            return False
        if cur == target:
            return True
        cur = hwnd_int(user32.GetParent(cur))
    return False


def class_name(hwnd: int) -> str:
    if not hwnd:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(wintypes.HWND(hwnd), buf, 256)
    return buf.value or ""


def foreground_image_name() -> str:
    hwnd = hwnd_int(user32.GetForegroundWindow())
    if not hwnd:
        return ""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if handle:
        try:
            size = wintypes.DWORD(32768)
            buf = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return Path(buf.value).name.lower()
        finally:
            kernel32.CloseHandle(handle)
    return class_name(hwnd).lower()


def focused_is_terminal() -> bool:
    hwnd = hwnd_int(user32.GetForegroundWindow())
    klass = class_name(hwnd).lower()
    if any(hint in klass for hint in TERMINAL_CLASSES):
        return True
    name = foreground_image_name()
    return any(hint in name for hint in TERMINAL_EXES)


def key_down(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def extra_modifiers_down() -> bool:
    return any(key_down(vk) for vk in (VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN))


def grave_vk(code: int) -> int:
    return VK_OEM_3 if int(code) == X11_GRAVE else int(code)


def x11_button_from_win_message(wparam: int, mouse_data: int) -> int | None:
    msg = int(wparam)
    if msg in (WM_LBUTTONDOWN, WM_LBUTTONUP):
        return 1
    if msg in (WM_MBUTTONDOWN, WM_MBUTTONUP):
        return 2
    if msg in (WM_RBUTTONDOWN, WM_RBUTTONUP):
        return 3
    if msg in (WM_XBUTTONDOWN, WM_XBUTTONUP):
        which = (int(mouse_data) >> 16) & 0xFFFF
        if which == XBUTTON1:
            return 8
        if which == XBUTTON2:
            return 9
    return None


def vk_display_name(vk: int) -> str:
    if int(vk) in {X11_GRAVE, VK_OEM_3}:
        return "ё"
    scan = user32.MapVirtualKeyW(int(vk), 0)
    buf = ctypes.create_unicode_buffer(64)
    user32.GetKeyNameTextW(scan << 16, buf, 64)
    return (buf.value or "").strip()


def send_chord(vks: list[int]) -> None:
    n = len(vks) * 2
    arr = (INPUT * n)()
    for i, vk in enumerate(vks):
        arr[i].type = INPUT_KEYBOARD
        arr[i].ki = KEYBDINPUT(vk, 0, 0, 0, 0)
    for i, vk in enumerate(reversed(vks)):
        idx = len(vks) + i
        arr[idx].type = INPUT_KEYBOARD
        arr[idx].ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP, 0, 0)
    sent = user32.SendInput(n, ctypes.byref(arr), ctypes.sizeof(INPUT))
    if int(sent) != n:
        log.warning("SendInput chord %s/%s err=%s", sent, n, ctypes.get_last_error())


TOKEN_QUERY = 0x0008
TokenIntegrityLevel = 25
SECURITY_MANDATORY_HIGH_RID = 0x00003000
PROCESS_CREATE_PROCESS = 0x0080
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
PROC_THREAD_ATTRIBUTE_PARENT_PROCESS = 0x00020000
CREATE_UNICODE_ENVIRONMENT = 0x00000400


class _SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = (("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD))


class _TOKEN_MANDATORY_LABEL(ctypes.Structure):
    _fields_ = (("Label", _SID_AND_ATTRIBUTES),)


class _STARTUPINFOW(ctypes.Structure):
    _fields_ = (
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.c_void_p),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    )


class _STARTUPINFOEXW(ctypes.Structure):
    _fields_ = (("StartupInfo", _STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p))


class _PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = (
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    )


advapi32.OpenProcessToken.argtypes = (wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE))
advapi32.OpenProcessToken.restype = wintypes.BOOL
advapi32.GetTokenInformation.argtypes = (
    wintypes.HANDLE,
    ctypes.c_int,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
)
advapi32.GetTokenInformation.restype = wintypes.BOOL
advapi32.GetSidSubAuthorityCount.argtypes = (ctypes.c_void_p,)
advapi32.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
advapi32.GetSidSubAuthority.argtypes = (ctypes.c_void_p, wintypes.DWORD)
advapi32.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)
user32.GetShellWindow.restype = wintypes.HWND
kernel32.GetCurrentProcess.restype = wintypes.HANDLE
kernel32.InitializeProcThreadAttributeList.argtypes = (
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.POINTER(ctypes.c_size_t),
)
kernel32.InitializeProcThreadAttributeList.restype = wintypes.BOOL
kernel32.UpdateProcThreadAttribute.argtypes = (
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.c_size_t,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.c_void_p,
    ctypes.c_void_p,
)
kernel32.UpdateProcThreadAttribute.restype = wintypes.BOOL
kernel32.DeleteProcThreadAttributeList.argtypes = (ctypes.c_void_p,)
kernel32.CreateProcessW.argtypes = (
    wintypes.LPCWSTR,
    wintypes.LPWSTR,
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.BOOL,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.LPCWSTR,
    ctypes.c_void_p,
    ctypes.POINTER(_PROCESS_INFORMATION),
)
kernel32.CreateProcessW.restype = wintypes.BOOL


def token_integrity_rid() -> int:
    try:
        return _token_integrity_rid()
    except Exception:
        log.exception("не удалось прочитать RID целостности")
        return 0


def _token_integrity_rid() -> int:
    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(token)):
        return 0
    try:
        needed = wintypes.DWORD(0)
        advapi32.GetTokenInformation(token, TokenIntegrityLevel, None, 0, ctypes.byref(needed))
        if not needed.value:
            return 0
        buf = ctypes.create_string_buffer(needed.value)
        if not advapi32.GetTokenInformation(
            token, TokenIntegrityLevel, buf, needed.value, ctypes.byref(needed)
        ):
            return 0
        label = ctypes.cast(buf, ctypes.POINTER(_TOKEN_MANDATORY_LABEL)).contents
        sid = label.Label.Sid
        if not sid:
            return 0
        count_ptr = advapi32.GetSidSubAuthorityCount(sid)
        if not count_ptr:
            return 0
        # Python 3.12 int(ctypes_int) uses the buffer protocol (b'\x01'), not .value.
        last = int(count_ptr.contents.value) - 1
        if last < 0:
            return 0
        rid_ptr = advapi32.GetSidSubAuthority(sid, last)
        if not rid_ptr:
            return 0
        return int(rid_ptr.contents.value)
    finally:
        kernel32.CloseHandle(token)


def is_high_integrity() -> bool:
    try:
        return token_integrity_rid() >= SECURITY_MANDATORY_HIGH_RID
    except Exception:
        log.exception("не удалось прочитать уровень целостности")
        return False


def relaunch_medium_integrity(args: list[str]) -> bool:
    """If this process is elevated, start a Medium-IL copy via explorer and exit.

    SendInput from High IL cannot type into normal apps (UIPI). Clipboard still
    works; paste into the focused field needs Medium integrity.
    """
    if sys.platform != "win32":
        return False
    try:
        return _relaunch_medium_integrity(args)
    except Exception:
        log.exception("не удалось перезапуститься без прав администратора")
        return False


def _relaunch_medium_integrity(args: list[str]) -> bool:
    if not is_high_integrity():
        return False
    shell = user32.GetShellWindow()
    if not shell:
        log.warning("нет окна explorer — оставляю повышенные права")
        return False
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(shell, ctypes.byref(pid))
    if not pid.value:
        return False
    parent = kernel32.OpenProcess(PROCESS_CREATE_PROCESS | PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not parent:
        log.warning("не открыть explorer pid=%s err=%s", pid.value, ctypes.get_last_error())
        return False
    attr_size = ctypes.c_size_t(0)
    kernel32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(attr_size))
    attr = ctypes.create_string_buffer(attr_size.value)
    pi = _PROCESS_INFORMATION()
    try:
        if not kernel32.InitializeProcThreadAttributeList(attr, 1, 0, ctypes.byref(attr_size)):
            return False
        parent_handle = wintypes.HANDLE(parent)
        if not kernel32.UpdateProcThreadAttribute(
            attr,
            0,
            PROC_THREAD_ATTRIBUTE_PARENT_PROCESS,
            ctypes.byref(parent_handle),
            ctypes.sizeof(wintypes.HANDLE),
            None,
            None,
        ):
            log.warning("UpdateProcThreadAttribute failed err=%s", ctypes.get_last_error())
            return False
        si = _STARTUPINFOEXW()
        si.StartupInfo.cb = ctypes.sizeof(_STARTUPINFOEXW)
        si.lpAttributeList = ctypes.cast(attr, ctypes.c_void_p)
        exe = sys.executable
        if getattr(sys, "frozen", False):
            cmdline = " ".join([f'"{exe}"', *args])
        else:
            cmdline = " ".join([f'"{exe}"', "-m", "yo", *args])
        cmdbuf = ctypes.create_unicode_buffer(cmdline)
        cwd = str(Path(exe).resolve().parent)
        flags = EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT
        if not kernel32.CreateProcessW(
            exe,
            cmdbuf,
            None,
            None,
            False,
            flags,
            None,
            cwd,
            ctypes.byref(si),
            ctypes.byref(pi),
        ):
            log.warning("CreateProcess medium failed err=%s cmd=%s", ctypes.get_last_error(), cmdline)
            return False
        log.info("запущен процесс без прав администратора pid=%s", pi.dwProcessId)
        return True
    finally:
        try:
            kernel32.DeleteProcThreadAttributeList(attr)
        except Exception:
            pass
        kernel32.CloseHandle(parent)
        if pi.hThread:
            kernel32.CloseHandle(pi.hThread)
        if pi.hProcess:
            kernel32.CloseHandle(pi.hProcess)
