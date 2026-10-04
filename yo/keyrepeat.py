"""Одно нажатие — одно переключение, даже если клавишу держат.

Pure logic shared by the X11 and Win32 hotkey watchers, so it can be
tested without a display or Windows.
"""

from __future__ import annotations

# X11 key repeat sends a press every ~25-40 ms. A key that is still marked
# held but has been silent for longer lost its release event.
REPEAT_GAP_MS = 1000


def _elapsed_ms(now: int, before: int) -> int:
    # X server time is a 32-bit millisecond counter and wraps.
    return (int(now) - int(before)) & 0xFFFFFFFF


class X11RepeatFilter:
    """Tell a real key press from X11 auto-repeat.

    Without detectable auto-repeat the server sends Release+Press pairs with
    the same timestamp while the key is held; with it, only more Presses.
    Both are repeats and must not toggle dictation again.
    """

    def __init__(self) -> None:
        self._held: dict[int, int] = {}
        self._released: dict[int, int] = {}

    def press(self, code: int, time_ms: int) -> bool:
        """Return True when this press should fire the hotkey."""
        code = int(code)
        time_ms = int(time_ms)
        released = self._released.pop(code, None)
        if released is not None and _elapsed_ms(time_ms, released) <= 1:
            self._held[code] = time_ms
            return False
        last = self._held.get(code)
        self._held[code] = time_ms
        if last is not None and _elapsed_ms(time_ms, last) < REPEAT_GAP_MS:
            return False
        return True

    def release(self, code: int, time_ms: int) -> None:
        code = int(code)
        self._held.pop(code, None)
        self._released[code] = int(time_ms)


def win_key_action(*, down: bool, up: bool, bound: bool, held: bool, mods_down: bool) -> str:
    """What the Win32 low-level hook does with one bound-key event.

    Returns "fire" (eat the key and toggle), "eat" (swallow quietly) or
    "pass" (let the key reach the focused app).

    The release of a key whose press was eaten is always eaten and always
    clears the held mark, even if Shift went down in between. Otherwise the
    mark sticks and the next real press is mistaken for auto-repeat.
    """
    if not bound:
        return "pass"
    if up:
        return "eat" if held else "pass"
    if not down:
        return "pass"
    if held:
        return "eat"
    if mods_down:
        return "pass"
    return "fire"
