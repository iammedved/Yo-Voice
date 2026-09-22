"""Unicode clipboard get/set via Win32."""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

from yo.winapi import CF_UNICODETEXT, GMEM_MOVEABLE, kernel32, user32

# 64-bit HGLOBAL must not go through ctypes' default c_int conversion.
HGLOBAL = getattr(wintypes, "HGLOBAL", wintypes.HANDLE)
kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
kernel32.GlobalAlloc.restype = HGLOBAL
kernel32.GlobalLock.argtypes = (HGLOBAL,)
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = (HGLOBAL,)
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalFree.argtypes = (HGLOBAL,)
kernel32.GlobalFree.restype = HGLOBAL
kernel32.GlobalSize.argtypes = (HGLOBAL,)
kernel32.GlobalSize.restype = ctypes.c_size_t
user32.OpenClipboard.argtypes = (wintypes.HWND,)
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.argtypes = ()
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = ()
user32.EmptyClipboard.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = (wintypes.UINT,)
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
user32.SetClipboardData.restype = wintypes.HANDLE


def _open_clipboard(retries: int = 50) -> bool:
    delay = 0.02
    for _ in range(max(1, retries)):
        if user32.OpenClipboard(None):
            return True
        time.sleep(delay)
        delay = min(0.08, delay + 0.01)
    return False


def clipboard_get() -> str | None:
    if not _open_clipboard():
        return None
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return None
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _clipboard_set_once(text: str) -> None:
    payload = (text or "").encode("utf-16-le") + b"\x00\x00"
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(payload))
    if not handle:
        raise OSError("GlobalAlloc clipboard")
    ptr = kernel32.GlobalLock(handle)
    if not ptr:
        kernel32.GlobalFree(handle)
        raise OSError("GlobalLock clipboard")
    try:
        ctypes.memmove(ptr, payload, len(payload))
    finally:
        kernel32.GlobalUnlock(handle)
    if not _open_clipboard():
        kernel32.GlobalFree(handle)
        raise OSError("OpenClipboard")
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            raise OSError("SetClipboardData")
        handle = None  # owned by clipboard
    finally:
        user32.CloseClipboard()
        if handle:
            kernel32.GlobalFree(handle)


def clipboard_set(text: str) -> None:
    wanted = text or ""
    previous = clipboard_get()
    last_err = "clipboard_set"
    for attempt in range(3):
        try:
            _clipboard_set_once(wanted)
            got = clipboard_get()
            if got == wanted:
                return
            last_err = f"clipboard verify mismatch attempt={attempt}"
        except OSError as exc:
            last_err = str(exc)
        time.sleep(0.03)
    if previous is not None:
        try:
            _clipboard_set_once(previous)
        except OSError:
            pass
    raise OSError(last_err)
