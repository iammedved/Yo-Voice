"""Main-thread idle/timeout/clipboard without importing GTK on Windows."""

from __future__ import annotations

import sys

if sys.platform == "win32":
    from yo.clip_win import clipboard_get, clipboard_set
    from yo.loop_win import idle_add, loop_init, loop_main, loop_quit, source_remove, timeout_add, tk_root
else:
    from yo.loop_linux import (
        clipboard_get,
        clipboard_set,
        idle_add,
        loop_init,
        loop_main,
        loop_quit,
        source_remove,
        timeout_add,
        tk_root,
    )

__all__ = [
    "clipboard_get",
    "clipboard_set",
    "idle_add",
    "loop_init",
    "loop_main",
    "loop_quit",
    "source_remove",
    "timeout_add",
    "tk_root",
]
