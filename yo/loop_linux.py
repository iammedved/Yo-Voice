"""GLib/GTK main loop wrappers used on Linux."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk


def loop_init() -> None:
    Gtk.init([])


def idle_add(fn: Callable, *args: Any):
    return GLib.idle_add(fn, *args)


def timeout_add(ms: int, fn: Callable, *args: Any):
    return GLib.timeout_add(ms, fn, *args)


def source_remove(sid) -> None:
    if sid is None:
        return
    try:
        GLib.source_remove(sid)
    except Exception:
        pass


def loop_main() -> None:
    Gtk.main()


def loop_quit() -> None:
    Gtk.main_quit()


def tk_root():
    raise RuntimeError("tk root is Windows-only")


def clipboard_get() -> str | None:
    clip = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    return clip.wait_for_text()


def clipboard_set(text: str) -> None:
    clip = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    clip.set_text(text, -1)
    clip.store()
