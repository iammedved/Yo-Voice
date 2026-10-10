"""Не включать диктовку, пока на экране игра.

Steam: окно принадлежит игре из steamapps или процессу, который запустил steam.exe.
Чужой эксклюзивный полноэкранный режим Windows сообщает отдельно. Библиотека Steam
и обычные окна не считаются игрой, чтобы после Alt+Tab диктовка снова работала.
"""

from __future__ import annotations

import sys
from pathlib import Path

# SHQueryUserNotificationState: exclusive Direct3D (игра на весь экран).
QUNS_RUNNING_D3D_FULL_SCREEN = 3

# Сам клиент Steam, не игра. Оверлей обрабатывается отдельно: он поверх игры.
STEAM_CLIENT_EXES = frozenset(
    {
        "steam.exe",
        "steamwebhelper.exe",
        "steamservice.exe",
        "steamerrorreporter.exe",
        "streaming_client.exe",
        "steamxboxutil.exe",
        "steamxboxutil64.exe",
        "steamsysinfo.exe",
        "steamcmd.exe",
    }
)

# Эти окна не считаем игрой, даже если Windows ещё держит флаг полноэкранного D3D.
_NOT_A_GAME = STEAM_CLIENT_EXES | frozenset(
    {
        "explorer.exe",
        "yo-voice.exe",
        "searchhost.exe",
        "shellexperiencehost.exe",
        "textinputhost.exe",
    }
)

_game_hold = False


def set_game_hold(holding: bool) -> None:
    global _game_hold
    _game_hold = bool(holding)


def game_hold_active() -> bool:
    return _game_hold


def _exe_name(name: str, image_path: str = "") -> str:
    raw = (name or "").strip() or (image_path or "").strip()
    if not raw:
        return ""
    return Path(raw.replace("/", "\\")).name.lower()


def is_steam_game(exe_name: str, image_path: str, parent_exe: str) -> bool:
    """Активное окно — игра Steam, а не библиотека и не служебный процесс."""
    name = _exe_name(exe_name, image_path)
    if name == "gameoverlayui.exe":
        return True
    if not name or name in STEAM_CLIENT_EXES:
        return False
    path = (image_path or "").replace("/", "\\").lower()
    if "\\steamapps\\" in path:
        return True
    return _exe_name(parent_exe) == "steam.exe"


def window_covers_monitor(
    window: tuple[int, int, int, int] | None,
    monitors: list[tuple[int, int, int, int]] | None,
    *,
    slack: int = 8,
) -> bool:
    if window is None or not monitors:
        return False
    left, top, right, bottom = window
    if right <= left or bottom <= top:
        return False
    pad = max(0, int(slack))
    for monitor in monitors:
        ml, mt, mr, mb = monitor
        if mr <= ml or mb <= mt:
            continue
        if left <= ml + pad and top <= mt + pad and right >= mr - pad and bottom >= mb - pad:
            return True
    return False


def should_hold_dictation(
    *,
    exe_name: str,
    image_path: str,
    parent_exe: str,
    notification_state: int = 0,
    covers_screen: bool = False,
) -> bool:
    if is_steam_game(exe_name, image_path, parent_exe):
        return True
    if int(notification_state) != QUNS_RUNNING_D3D_FULL_SCREEN or not covers_screen:
        return False
    name = _exe_name(exe_name, image_path)
    if name in _NOT_A_GAME:
        return False
    return True


def foreground_holds_dictation() -> bool:
    """Сейчас на экране игра. На Linux всегда нет. Ошибка проверки — не блокировать."""
    if sys.platform != "win32":
        return False
    try:
        return _foreground_holds_win()
    except Exception:
        return False


def foreground_is_steam_game() -> bool:
    """Только Steam, без опроса оболочки. Это можно звать из низкоуровневого хука."""
    if sys.platform != "win32":
        return False
    try:
        return _foreground_steam_win()
    except Exception:
        return False


def hotkey_yields_to_game() -> bool:
    if game_hold_active():
        return True
    return foreground_is_steam_game()


def _foreground_holds_win() -> bool:
    proc = _foreground_process()
    if proc is None:
        return False
    exe_name, image_path, parent_exe, hwnd, user32 = proc
    return should_hold_dictation(
        exe_name=exe_name,
        image_path=image_path,
        parent_exe=parent_exe,
        notification_state=_notification_state(),
        covers_screen=_window_covers_its_monitor(user32, hwnd),
    )


def _foreground_steam_win() -> bool:
    # Хук клавиатуры не должен звать GetWindowRect: это может подвесить ввод.
    proc = _foreground_process()
    if proc is None:
        return False
    exe_name, image_path, parent_exe, _hwnd, _user32 = proc
    return is_steam_game(exe_name, image_path, parent_exe)


def _win_dlls():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    return user32, kernel32


def _foreground_process():
    import ctypes
    from ctypes import wintypes

    user32, _kernel32 = _win_dlls()
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    root = user32.GetAncestor(hwnd, 2)  # GA_ROOT
    if root:
        hwnd = root
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    image = _process_image(int(pid.value))
    parent = _process_image(_parent_pid(int(pid.value)))
    exe_name = Path(image).name if image else ""
    parent_exe = Path(parent).name if parent else ""
    return exe_name, image, parent_exe, hwnd, user32


def _process_image(pid: int) -> str:
    if pid <= 0:
        return ""
    import ctypes
    from ctypes import wintypes

    _user32, kernel32 = _win_dlls()
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ""
        return buf.value or ""
    finally:
        kernel32.CloseHandle(handle)


def _parent_pid(pid: int) -> int:
    if pid <= 0:
        return 0
    import ctypes

    class PROCESS_BASIC_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("Reserved1", ctypes.c_void_p),
            ("PebBaseAddress", ctypes.c_void_p),
            ("Reserved2_0", ctypes.c_void_p),
            ("Reserved2_1", ctypes.c_void_p),
            ("UniqueProcessId", ctypes.c_size_t),
            ("InheritedFromUniqueProcessId", ctypes.c_size_t),
        ]

    _user32, kernel32 = _win_dlls()
    ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
    ntdll.NtQueryInformationProcess.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_void_p,
    ]
    ntdll.NtQueryInformationProcess.restype = ctypes.c_long
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return 0
    try:
        info = PROCESS_BASIC_INFORMATION()
        status = ntdll.NtQueryInformationProcess(
            handle,
            0,
            ctypes.byref(info),
            ctypes.sizeof(info),
            None,
        )
        if int(status) != 0:
            return 0
        return int(info.InheritedFromUniqueProcessId)
    finally:
        kernel32.CloseHandle(handle)


def _notification_state() -> int:
    import ctypes

    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.SHQueryUserNotificationState.argtypes = [ctypes.POINTER(ctypes.c_int)]
    shell32.SHQueryUserNotificationState.restype = ctypes.HRESULT
    state = ctypes.c_int()
    if int(shell32.SHQueryUserNotificationState(ctypes.byref(state))) != 0:
        return 0
    return int(state.value)


def _window_covers_its_monitor(user32, hwnd) -> bool:
    import ctypes
    from ctypes import wintypes

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", RECT),
            ("rcWork", RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    rect = RECT()
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = ctypes.c_void_p
    monitor = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
    if not monitor:
        return False
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return False
    mon = info.rcMonitor
    return window_covers_monitor(
        (rect.left, rect.top, rect.right, rect.bottom),
        [(mon.left, mon.top, mon.right, mon.bottom)],
    )
