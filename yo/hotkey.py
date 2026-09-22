"""Глобальный перехват одной кнопки: клавиша или мышь (X11 или Win32)."""

from __future__ import annotations

import sys

if sys.platform == "win32":
    from yo.hotkey_win import HotkeyWatcher
else:
    from yo.hotkey_linux import HotkeyWatcher
