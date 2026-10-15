"""Unicode clipboard get/set via Win32."""

from __future__ import annotations

import ctypes
import logging
import time
from ctypes import wintypes

from yo.cliptext import clipboard_text, describe_mismatch, same_clipboard_text
from yo.winapi import CF_UNICODETEXT, GMEM_MOVEABLE, kernel32, user32

log = logging.getLogger("yo.clip")

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
user32.GetClipboardSequenceNumber.argtypes = ()
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.GetClipboardOwner.argtypes = ()
user32.GetClipboardOwner.restype = wintypes.HWND
user32.GetOpenClipboardWindow.argtypes = ()
user32.GetOpenClipboardWindow.restype = wintypes.HWND

SET_ATTEMPTS = 3
# Clipboard history, cloud sync and the paste target all open the clipboard
# right after it changes; a long text keeps them busy longer.
READBACK_TRIES = 6


class ClipboardError(OSError):
    """The clipboard did not take the text. ``placed`` — our text got there at least once."""

    def __init__(self, message: str, *, placed: bool = False) -> None:
        super().__init__(message)
        self.placed = placed


def _open_clipboard(retries: int = 50) -> bool:
    delay = 0.02
    for _ in range(max(1, retries)):
        if user32.OpenClipboard(None):
            return True
        time.sleep(delay)
        delay = min(0.08, delay + 0.01)
    return False


def _sequence() -> int:
    try:
        return int(user32.GetClipboardSequenceNumber() or 0)
    except Exception:
        return 0


def _hwnd_exe(hwnd) -> str:
    try:
        from yo.inject_win import _process_exe
        from yo.winapi import hwnd_int

        return _process_exe(hwnd_int(hwnd)) or "?"
    except Exception:
        return "?"


def _owner_label() -> str:
    """Who owns / holds the clipboard now — for the log and the report."""
    parts: list[str] = []
    try:
        owner = user32.GetClipboardOwner()
        parts.append(f"owner={_hwnd_exe(owner) if owner else 'none'}")
    except Exception:
        pass
    try:
        holder = user32.GetOpenClipboardWindow()
        if holder:
            parts.append(f"open={_hwnd_exe(holder)}")
    except Exception:
        pass
    return " ".join(parts)


def _locked_text(handle) -> str | None:
    ptr = kernel32.GlobalLock(handle)
    if not ptr:
        return None
    try:
        # Bounded read: a block from another program may lack the final NUL.
        units = int(kernel32.GlobalSize(handle) or 0) // 2
        raw = ctypes.wstring_at(ptr, units) if units else ctypes.wstring_at(ptr)
        end = raw.find("\x00")
        return raw if end < 0 else raw[:end]
    finally:
        kernel32.GlobalUnlock(handle)


def _read_clipboard(retries: int = 50) -> tuple[bool, str | None]:
    """(opened, text). ``opened=False`` — clipboard busy, ``text=None`` — no text on it."""
    if not _open_clipboard(retries):
        return False, None
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return True, None
        return True, _locked_text(handle)
    finally:
        user32.CloseClipboard()


def clipboard_get() -> str | None:
    return _read_clipboard()[1]


def _clipboard_set_once(text: str) -> int:
    """Put ``text`` on the clipboard; return the sequence number right after."""
    payload = text.encode("utf-16-le") + b"\x00\x00"
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(payload))
    if not handle:
        raise ClipboardError(f"GlobalAlloc clipboard bytes={len(payload)} err={ctypes.get_last_error()}")
    ptr = kernel32.GlobalLock(handle)
    if not ptr:
        kernel32.GlobalFree(handle)
        raise ClipboardError("GlobalLock clipboard")
    try:
        ctypes.memmove(ptr, payload, len(payload))
    finally:
        kernel32.GlobalUnlock(handle)
    if not _open_clipboard():
        kernel32.GlobalFree(handle)
        raise ClipboardError(f"OpenClipboard busy {_owner_label()}".rstrip())
    try:
        if not user32.EmptyClipboard():
            raise ClipboardError(f"EmptyClipboard err={ctypes.get_last_error()}")
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            raise ClipboardError(f"SetClipboardData err={ctypes.get_last_error()}")
        handle = None  # owned by clipboard
        return _sequence()
    finally:
        user32.CloseClipboard()
        if handle:
            kernel32.GlobalFree(handle)


def _verify(wanted: str, seq: int) -> str | None:
    """None when the clipboard holds ``wanted``; otherwise why it does not."""
    # Same sequence number: nobody touched the clipboard after our
    # SetClipboardData, so it holds exactly the bytes we wrote.
    if seq and _sequence() == seq:
        return None
    for i in range(READBACK_TRIES):
        opened, got = _read_clipboard(retries=10)
        if opened:
            if same_clipboard_text(got, wanted):
                return None
            return f"clipboard changed by another program: {describe_mismatch(got, wanted)} {_owner_label()}".rstrip()
        time.sleep(0.05 * (i + 1))
    return f"clipboard busy {_owner_label()}".rstrip()


def clipboard_set(text: str) -> None:
    wanted = clipboard_text(text)
    if wanted != (text or ""):
        log.warning("из текста для буфера убраны символы NUL: %s", len(text or "") - len(wanted))
    previous = clipboard_get()
    last_err = "clipboard_set"
    placed = False
    for attempt in range(SET_ATTEMPTS):
        try:
            seq = _clipboard_set_once(wanted)
            placed = True
            problem = _verify(wanted, seq)
            if problem is None:
                if attempt:
                    log.info("буфер обмена принял текст с попытки %s", attempt + 1)
                return
            last_err = f"{problem} attempt={attempt}"
        except OSError as exc:
            last_err = f"{exc} attempt={attempt}"
        log.warning("буфер обмена: %s символов=%s", last_err, len(wanted))
        time.sleep(0.05 * (attempt + 1))
    # Windows keeps dictated text on the clipboard on purpose; once ours got
    # there, putting the old clipboard back would only lose the dictation.
    if not placed and previous is not None:
        try:
            _clipboard_set_once(previous)
        except OSError:
            pass
    raise ClipboardError(last_err, placed=placed)
