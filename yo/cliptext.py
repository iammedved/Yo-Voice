"""Clipboard text rules shared by Windows and Linux, without any OS calls."""

from __future__ import annotations


def clipboard_text(text: str | None) -> str:
    """Text as the clipboard can carry it: a NUL ends a CF_UNICODETEXT string."""
    return (text or "").replace("\x00", "")


def _norm(text: str) -> str:
    return text.replace("\r\n", "\n")


def same_clipboard_text(got: str | None, wanted: str) -> bool:
    """Read-back matches what we put, ignoring CRLF/LF conversion by other programs."""
    if got is None:
        return False
    return _norm(got) == _norm(wanted)


def describe_mismatch(got: str | None, wanted: str) -> str:
    """Short, text-free description of how the read-back differs (for logs and reports)."""
    if got is None:
        return f"got=no-text want={len(wanted)}"
    a, b = _norm(got), _norm(wanted)
    first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    return f"got={len(got)} want={len(wanted)} diff_at={first}"
