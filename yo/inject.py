"""Вставка текста в активное поле через буфер и Ctrl+V / Ctrl+Shift+V."""

from __future__ import annotations

from Xlib import XK, X, display
from Xlib.ext import xtest

TERMINAL_HINTS = (
    "terminal",
    "tilix",
    "kitty",
    "alacritty",
    "xterm",
    "wezterm",
    "terminator",
    "ptyxis",
    "konsole",
    "guake",
    "tilda",
)


class Injector:
    def __init__(self) -> None:
        self.dpy = display.Display()
        self.ctrl = self.dpy.keysym_to_keycode(XK.XK_Control_L)
        self.shift = self.dpy.keysym_to_keycode(XK.XK_Shift_L)
        self.v = self.dpy.keysym_to_keycode(XK.XK_v)

    def paste(self) -> None:
        if self._focused_is_terminal():
            self._chord([self.ctrl, self.shift, self.v])
        else:
            self._chord([self.ctrl, self.v])

    def _chord(self, keycodes: list[int]) -> None:
        for code in keycodes:
            xtest.fake_input(self.dpy, X.KeyPress, code)
        self.dpy.sync()
        for code in reversed(keycodes):
            xtest.fake_input(self.dpy, X.KeyRelease, code)
        self.dpy.sync()

    def _focused_is_terminal(self) -> bool:
        try:
            focus = self.dpy.get_input_focus().focus
            if focus is None or focus.id in (0, 1):
                return False
            klass = self._wm_class(focus)
            return any(hint in klass for hint in TERMINAL_HINTS)
        except Exception:
            return False

    def _wm_class(self, window) -> str:
        atom = self.dpy.intern_atom("WM_CLASS")
        try:
            prop = window.get_full_property(atom, 0)
            if prop and prop.value:
                if isinstance(prop.value, bytes):
                    return prop.value.decode("utf-8", "replace").lower()
                return str(prop.value).lower()
        except Exception:
            pass
        try:
            parent = window.query_tree().parent
            if parent:
                return self._wm_class(parent)
        except Exception:
            pass
        return ""
