"""Вставка текста в активное поле через буфер и Ctrl+V / Ctrl+Shift+V."""

from __future__ import annotations

import sys

if sys.platform == "win32":
    from yo.inject_win import TERMINAL_HINTS, Injector
else:
    from yo.inject_linux import TERMINAL_HINTS, Injector
