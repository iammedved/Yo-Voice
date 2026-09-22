"""Одна кнопка включения/выключения: клавиша или кнопка мыши."""

from __future__ import annotations

import logging
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

log = logging.getLogger("yo.bind")

DEFAULT_KIND = "key"
DEFAULT_CODE = 49  # grave / ё (X11 keycode; Windows maps to VK_OEM_3)
SCROLL_BUTTONS = {4, 5}
OVERLAY_UI_BUTTONS = {1, 3}  # drag / menu; extra mouse buttons still count
KEY_LABELS = {49: "ё", 0xC0: "ё"}
BUTTON_LABELS = {1: "ЛКМ", 2: "СКМ", 3: "ПКМ"}
# Named keys for CLI `bind`. Values are Win32 VKs; X11 49 is kept for ё/grave.
_NAMED_KEYS = {
    "ё": DEFAULT_CODE,
    "`": DEFAULT_CODE,
    "grave": DEFAULT_CODE,
    "tilde": DEFAULT_CODE,
    "yo": DEFAULT_CODE,
    "oem3": 0xC0,
    "oem_3": 0xC0,
    "vk_oem_3": 0xC0,
    "space": 0x20,
    "spc": 0x20,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "enter": 0x0D,
    "return": 0x0D,
    "back": 0x08,
    "backspace": 0x08,
    "bksp": 0x08,
    "insert": 0x2D,
    "ins": 0x2D,
    "delete": 0x2E,
    "del": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "pgup": 0x21,
    "pageup": 0x21,
    "pgdn": 0x22,
    "pagedown": 0x22,
    "pause": 0x13,
    "break": 0x13,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "caps": 0x14,
    "capslock": 0x14,
    "scrolllock": 0x91,
    "apps": 0x5D,
    "menu": 0x5D,
    "printscreen": 0x2C,
    "prtsc": 0x2C,
    "prtscr": 0x2C,
}
_NAMED_BUTTONS = {
    "x1": 8,
    "x2": 9,
    "mousex1": 8,
    "mousex2": 9,
    "back": 8,
    "forward": 9,
}


@dataclass(frozen=True)
class ToggleBind:
    kind: str
    code: int


DEFAULT_BIND = ToggleBind(kind=DEFAULT_KIND, code=DEFAULT_CODE)


def optional_bind(kind: str | None, code: int | None) -> ToggleBind | None:
    kind_s = str(kind or "").strip().lower()
    if kind_s not in {"key", "button"}:
        return None
    try:
        num = int(code or 0)
    except (TypeError, ValueError):
        return None
    if num <= 0:
        return None
    if kind_s == "button" and num in SCROLL_BUTTONS:
        return None
    return ToggleBind(kind=kind_s, code=num)


def _key_alias(code: int) -> int:
    """ё/grave is stored as X11 49 or VK_OEM_3 (0xC0); treat them as one key."""
    n = int(code)
    if n in (DEFAULT_CODE, 0xC0):
        return 0xC0
    return n


def binds_conflict(left: ToggleBind | None, right: ToggleBind | None) -> bool:
    if left is None or right is None:
        return False
    if left.kind != right.kind:
        return False
    if left.kind == "key":
        return _key_alias(left.code) == _key_alias(right.code)
    return left.code == right.code


def listen_press_action(*, listening: bool, current_task: str, pressed_task: str) -> str:
    current = "translate" if current_task == "translate" else "transcribe"
    pressed = "translate" if pressed_task == "translate" else "transcribe"
    if not listening:
        return "start"
    if pressed == "transcribe":
        return "stop"
    if current == "translate":
        return "stop"
    return "switch"


def restore_clipboard_after_paste(*, task: str) -> bool:
    """Linux dictation restores the previous clipboard; translate leaves English.

    Windows keeps the recognized text on the clipboard so Ctrl+V still works
    when SendInput is blocked (UIPI / elevated daemon).
    """
    if sys.platform == "win32":
        return False
    return task != "translate"


def normalize_bind(kind: str | None, code: int | None, *, fallback: ToggleBind = DEFAULT_BIND) -> ToggleBind:
    kind_s = str(kind or fallback.kind).strip().lower()
    if kind_s not in {"key", "button"}:
        kind_s = fallback.kind
    try:
        num = int(fallback.code if code is None else code)
    except (TypeError, ValueError):
        num = fallback.code
        kind_s = fallback.kind
    if num <= 0:
        return fallback
    if kind_s == "button" and num in SCROLL_BUTTONS:
        return fallback
    return ToggleBind(kind=kind_s, code=num)


def format_bind(bind: ToggleBind) -> str:
    if bind.kind == "button":
        return BUTTON_LABELS.get(bind.code, f"мышь {bind.code}")
    if bind.code in KEY_LABELS:
        return KEY_LABELS[bind.code]
    if 0x70 <= bind.code <= 0x87:
        return f"F{bind.code - 0x6F}"
    label = _keysym_label(bind.code)
    return label or f"клавиша {bind.code}"


def parse_bind_spec(spec: str | None) -> ToggleBind | None:
    """Parse CLI text (`F8`, `0x77`, `ё`, `mouse:8`) into a bind."""
    raw = " ".join(str(spec or "").split()).strip()
    if not raw:
        return None
    compact = "".join(ch for ch in raw.lower() if ch not in " \t-_")
    if compact in _NAMED_BUTTONS:
        return optional_bind("button", _NAMED_BUTTONS[compact])
    for prefix in ("mouse", "button", "btn", "мышь"):
        if compact.startswith(prefix):
            rest = compact[len(prefix) :].lstrip(":")
            if rest.isdigit():
                return optional_bind("button", int(rest))
            return None
    if compact in _NAMED_KEYS:
        return optional_bind("key", _NAMED_KEYS[compact])
    if compact.startswith("f") and compact[1:].isdigit():
        n = int(compact[1:])
        if 1 <= n <= 24:
            return optional_bind("key", 0x6F + n)
    if len(compact) == 1 and "a" <= compact <= "z":
        return optional_bind("key", ord(compact.upper()))
    if compact.startswith("vk"):
        compact = compact[2:]
    try:
        if compact.startswith("0x"):
            num = int(compact, 16)
        elif compact.endswith("h") and len(compact) > 1:
            num = int(compact[:-1], 16)
        else:
            num = int(compact, 10)
    except ValueError:
        return None
    if not 1 <= num <= 255:
        return None
    return optional_bind("key", num)


def accept_capture_event(
    *,
    event_type: str,
    code: int,
    overlay_hit: bool = False,
) -> ToggleBind | None:
    try:
        num = int(code)
    except (TypeError, ValueError):
        return None
    if event_type == "button" and overlay_hit and num in OVERLAY_UI_BUTTONS:
        return None
    if num <= 0:
        return None
    if event_type == "button" and num in SCROLL_BUTTONS:
        return None
    if event_type not in {"key", "button"}:
        return None
    return ToggleBind(kind=event_type, code=num)


def _keysym_label(code: int) -> str:
    if sys.platform == "win32":
        from yo.hotkey_win import vk_label

        return vk_label(code)
    try:
        from Xlib import XK, display

        dpy = display.Display()
        try:
            keysym = dpy.keycode_to_keysym(code, 0)
            name = XK.keysym_to_string(keysym) if keysym else None
            return (name or "").strip()
        finally:
            dpy.close()
    except Exception:
        return ""


def capture_bind(
    on_result: Callable[[ToggleBind | None], None],
    *,
    overlay_xid: int | None = None,
    timeout_sec: float = 15.0,
) -> None:
    if sys.platform == "win32":
        from yo.hotkey_win import capture_bind as capture_bind_win

        capture_bind_win(on_result, overlay_xid=overlay_xid, timeout_sec=timeout_sec)
        return

    def worker() -> None:
        bind: ToggleBind | None = None
        try:
            bind = _grab_next_bind(overlay_xid, timeout_sec)
        except Exception:
            log.exception("не удалось перехватить новую кнопку")
        try:
            on_result(bind)
        except Exception:
            log.exception("ошибка после выбора кнопки")

    threading.Thread(target=worker, daemon=True, name="yo-rebind").start()


def _grab_next_bind(overlay_xid: int | None, timeout_sec: float) -> ToggleBind | None:
    from Xlib import X, display

    dpy = display.Display()
    root = dpy.screen().root
    root.grab_keyboard(True, X.GrabModeAsync, X.GrabModeAsync, X.CurrentTime)
    root.grab_pointer(
        True,
        X.ButtonPressMask,
        X.GrabModeAsync,
        X.GrabModeAsync,
        0,
        0,
        X.CurrentTime,
    )
    dpy.flush()
    try:
        deadline = time.monotonic() + max(1.0, float(timeout_sec))
        while time.monotonic() < deadline:
            if dpy.pending_events() == 0:
                time.sleep(0.02)
                continue
            ev = dpy.next_event()
            accepted: ToggleBind | None = None
            if ev.type == X.KeyPress:
                accepted = accept_capture_event(event_type="key", code=int(getattr(ev, "detail", 0)))
            elif ev.type == X.ButtonPress:
                child = getattr(ev, "child", None)
                child_id = getattr(child, "id", None)
                overlay_hit = overlay_xid is not None and child_id == overlay_xid
                accepted = accept_capture_event(
                    event_type="button",
                    code=int(getattr(ev, "detail", 0)),
                    overlay_hit=bool(overlay_hit),
                )
            if accepted is not None:
                return accepted
        return None
    finally:
        try:
            dpy.ungrab_keyboard(X.CurrentTime)
            dpy.ungrab_pointer(X.CurrentTime)
            dpy.flush()
        except Exception:
            pass
        try:
            dpy.close()
        except Exception:
            pass
