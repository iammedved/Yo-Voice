"""Restore stdio for a windowed frozen EXE (console parent or redirected pipes)."""

from __future__ import annotations

import os
import sys


def _prepend_cuda_path() -> None:
    """PATH/add_dll_directory until yo.cuda_env runs — ctranslate2 loads cublas by name."""
    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return
    extra = [meipass]
    for rel in (
        "nvidia/cublas/bin",
        "nvidia/cudnn/bin",
        "nvidia/cuda_runtime/bin",
        "nvidia/cuda_nvrtc/bin",
        "ctranslate2",
    ):
        extra.append(os.path.join(meipass, *rel.split("/")))
    extra = [p for p in extra if os.path.isdir(p)]
    if not extra:
        return
    current = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join(extra + ([current] if current else []))
    if hasattr(os, "add_dll_directory"):
        for directory in extra:
            try:
                os.add_dll_directory(directory)
            except OSError:
                pass


_prepend_cuda_path()


if sys.platform == "win32":
    import ctypes
    import msvcrt
    import os
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    STD_OUTPUT_HANDLE = -11
    STD_ERROR_HANDLE = -12
    FILE_TYPE_DISK = 1
    FILE_TYPE_CHAR = 2
    FILE_TYPE_PIPE = 3
    ATTACH_PARENT_PROCESS = 0xFFFFFFFF

    kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel32.GetStdHandle.restype = wintypes.HANDLE
    kernel32.GetFileType.argtypes = [wintypes.HANDLE]
    kernel32.GetFileType.restype = wintypes.DWORD
    kernel32.AttachConsole.argtypes = [wintypes.DWORD]
    kernel32.AttachConsole.restype = wintypes.BOOL
    kernel32.GetConsoleWindow.restype = wintypes.HWND

    def _file_type(std_id: int) -> int:
        handle = kernel32.GetStdHandle(std_id)
        if not handle:
            return 0
        return int(kernel32.GetFileType(handle))

    def _bind(name: str, std_id: int, mode: str) -> None:
        if getattr(sys, name) is not None:
            return
        ftype = _file_type(std_id)
        if ftype in (FILE_TYPE_DISK, FILE_TYPE_PIPE, FILE_TYPE_CHAR):
            try:
                handle = int(kernel32.GetStdHandle(std_id))
                osfd = msvcrt.open_osfhandle(handle, os.O_APPEND if "w" in mode else os.O_RDONLY)
                setattr(sys, name, open(osfd, mode, encoding="utf-8", errors="replace", buffering=1))
                return
            except OSError:
                pass
        try:
            con = "CONOUT$" if "w" in mode else "CONIN$"
            setattr(sys, name, open(con, mode, encoding="utf-8", errors="replace", buffering=1))
        except OSError:
            pass

    if _file_type(STD_OUTPUT_HANDLE) == 0 and not kernel32.GetConsoleWindow():
        kernel32.AttachConsole(ATTACH_PARENT_PROCESS)

    _bind("stdout", STD_OUTPUT_HANDLE, "w")
    _bind("stderr", STD_ERROR_HANDLE, "w")
    # Windowed subsystem: never leave stdout/stderr as None (tqdm/HF crash).
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="replace")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="replace")
