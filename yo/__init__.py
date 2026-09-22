"""Yo-Voice (Ёхо) — local voice typing for Linux and Windows."""

from __future__ import annotations

import sys

__version__ = "1.0.0"

# CPython's ctypes.wintypes omits HCURSOR; WNDCLASSW in yo.winapi needs it.
if sys.platform == "win32":
    from . import winapi as _winapi  # noqa: F401
