"""Глобальный перехват клавиши ё / ` (keycode 49) на X11."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from Xlib import X, display
from Xlib.error import BadAccess

log = logging.getLogger("yo.hotkey")


class HotkeyWatcher(threading.Thread):
    def __init__(self, keycode: int, on_press: Callable[[], None]) -> None:
        super().__init__(daemon=True, name="yo-hotkey")
        self.keycode = keycode
        self.on_press = on_press
        self._running = True
        self.grabbed = False
        self.error: str | None = None
        self._dpy: display.Display | None = None
        self._root = None
        self._masks = (
            0,
            X.LockMask,
            X.Mod2Mask,
            X.LockMask | X.Mod2Mask,
        )

    def stop(self) -> None:
        self._running = False
        if self._dpy is not None and self._root is not None:
            for mask in self._masks:
                try:
                    self._root.ungrab_key(self.keycode, mask)
                except Exception:
                    pass
            try:
                self._dpy.flush()
            except Exception:
                pass

    def run(self) -> None:
        dpy = display.Display()
        self._dpy = dpy
        root = dpy.screen().root
        self._root = root
        try:
            for mask in self._masks:
                root.grab_key(self.keycode, mask, True, X.GrabModeAsync, X.GrabModeAsync)
            dpy.flush()
            self.grabbed = True
        except BadAccess:
            self.error = "клавиша уже занята другим приложением"
            log.error("%s", self.error)
            return

        root.change_attributes(event_mask=X.KeyPressMask)
        last = 0.0
        while self._running:
            if dpy.pending_events() == 0:
                time.sleep(0.02)
                continue
            ev = dpy.next_event()
            if ev.type != X.KeyPress:
                continue
            if getattr(ev, "detail", None) != self.keycode:
                continue
            state = int(getattr(ev, "state", 0))
            if state & (X.ControlMask | X.Mod1Mask | X.Mod4Mask | X.ShiftMask):
                continue
            now = time.monotonic()
            if now - last < 0.35:
                continue
            last = now
            try:
                self.on_press()
            except Exception:
                log.exception("ошибка обработки горячей клавиши")
