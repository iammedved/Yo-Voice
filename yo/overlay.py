"""Бесфокусный overlay: логотип ЙО и волны, без рамки."""

from __future__ import annotations

import sys

WIDTH = 200
HEIGHT = 186
MASCOT_HEIGHT = 118
WAVE_GAP = 4
STATUS_HEIGHT = 16
WAVE_HEIGHT = 40
WAVE_BARS = 52

if sys.platform == "win32":
    from yo.overlay_win import Overlay, run_demo
else:
    from yo.overlay_linux import Overlay, run_demo
