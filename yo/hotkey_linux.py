"""Глобальный перехват одной кнопки: клавиша или мышь, X11."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from Xlib import X, display
from Xlib.error import BadAccess

from yo.bind import OVERLAY_UI_BUTTONS, ToggleBind, normalize_bind

log = logging.getLogger("yo.hotkey")


class HotkeyWatcher(threading.Thread):
    def __init__(
        self,
        bind: ToggleBind | int | None = None,
        on_press: Callable[[], None] | None = None,
        *,
        binds: list[tuple[ToggleBind, Callable[[], None]]] | None = None,
        overlay_xid_fn: Callable[[], int | None] | None = None,
    ) -> None:
        super().__init__(daemon=True, name="yo-hotkey")
        if binds is None:
            if bind is None or on_press is None:
                raise ValueError("bind and on_press are required")
            if isinstance(bind, int):
                bind = normalize_bind("key", bind)
            binds = [(bind, on_press)]
        self.binds = list(binds)
        self.bind = self.binds[0][0]
        self.keycode = self.bind.code
        self.kind = self.bind.kind
        self.on_press = self.binds[0][1]
        self._overlay_xid_fn = overlay_xid_fn
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
        if threading.current_thread() is not self and self.is_alive():
            self.join(timeout=1.5)

    def _ungrab(self) -> None:
        if self._dpy is None or self._root is None:
            return
        for bind, _cb in self.binds:
            for mask in self._masks:
                try:
                    if bind.kind == "button":
                        self._root.ungrab_button(bind.code, mask)
                    else:
                        self._root.ungrab_key(bind.code, mask)
                except Exception:
                    pass
        try:
            self._dpy.flush()
        except Exception:
            pass
        try:
            self._dpy.close()
        except Exception:
            pass
        self._dpy = None
        self._root = None
        self.grabbed = False

    def run(self) -> None:
        dpy = display.Display()
        self._dpy = dpy
        root = dpy.screen().root
        self._root = root
        try:
            for bind, _cb in self.binds:
                for mask in self._masks:
                    if bind.kind == "button":
                        root.grab_button(
                            bind.code,
                            mask,
                            True,
                            X.ButtonPressMask,
                            X.GrabModeAsync,
                            X.GrabModeAsync,
                            0,
                            0,
                        )
                    else:
                        root.grab_key(bind.code, mask, True, X.GrabModeAsync, X.GrabModeAsync)
            dpy.flush()
            self.grabbed = True
        except BadAccess:
            self.error = "клавиша уже занята другим приложением"
            log.error("%s", self.error)
            self._ungrab()
            return

        event_mask = 0
        for bind, _cb in self.binds:
            event_mask |= X.ButtonPressMask if bind.kind == "button" else X.KeyPressMask
        if event_mask:
            try:
                root.change_attributes(event_mask=event_mask)
            except Exception:
                log.exception("не удалось подписаться на события корня")
        last = 0.0
        handlers = {(bind.kind, bind.code): cb for bind, cb in self.binds}
        try:
            while self._running:
                if dpy.pending_events() == 0:
                    time.sleep(0.02)
                    continue
                ev = dpy.next_event()
                kind = "button" if ev.type == X.ButtonPress else "key" if ev.type == X.KeyPress else ""
                if not kind:
                    continue
                code = int(getattr(ev, "detail", 0) or 0)
                cb = handlers.get((kind, code))
                if cb is None:
                    continue
                if kind == "key":
                    state = int(getattr(ev, "state", 0))
                    if state & (X.ControlMask | X.Mod1Mask | X.Mod4Mask | X.ShiftMask):
                        continue
                elif code in OVERLAY_UI_BUTTONS and self._hits_overlay(ev):
                    continue
                now = time.monotonic()
                if now - last < 0.35:
                    continue
                last = now
                try:
                    cb()
                except Exception:
                    log.exception("ошибка обработки горячей клавиши")
        finally:
            self._ungrab()

    def _hits_overlay(self, ev) -> bool:
        if self._overlay_xid_fn is None:
            return False
        try:
            xid = self._overlay_xid_fn()
        except Exception:
            return False
        if not xid:
            return False
        for target in (getattr(ev, "child", None), getattr(ev, "window", None)):
            if target is None:
                continue
            if getattr(target, "id", None) == xid:
                return True
        return False
