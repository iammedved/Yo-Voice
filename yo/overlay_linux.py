"""Бесфокусный overlay: логотип ЙО и волны, без рамки."""

from __future__ import annotations

import math
import time

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

from yo.capture import NO_MIC_HINT  # noqa: E402
from yo.paths import orb_path  # noqa: E402
from yo.phrases import display_label, wave_allowed  # noqa: E402
from yo.spectrum import voice_loudness, wave_amplitude  # noqa: E402

WIDTH = 200
HEIGHT = 186
MASCOT_HEIGHT = 118
WAVE_GAP = 4
STATUS_HEIGHT = 16
WAVE_HEIGHT = 40
WAVE_BARS = 52


class Overlay:
    def __init__(self, on_click=None, saved_pos=None, on_move=None, on_settings=None) -> None:
        self.on_click = on_click
        self.on_move = on_move
        self.on_settings = on_settings
        self.rms = 0.0
        self.wave = [0.12] * WAVE_BARS
        self.wave_target = [0.12] * WAVE_BARS
        self._bars: list[list[float]] = []
        self._pending_amp = 0.0
        self._last_tick = 0.0
        self.status = ""
        self.preview = ""
        self.mic_missing = False
        self.hint = ""
        self.live = False
        self.live_since: float | None = None
        self.task = "transcribe"
        self.visible = False
        self._tick_id = None
        self._pixbuf = _load_orb()
        self._drag = None
        self._user_pos = saved_pos
        self._phase = 0.0
        self._speed = 0.08
        self._speed_target = 0.08

        self.window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.window.set_decorated(False)
        self.window.set_app_paintable(True)
        self.window.set_accept_focus(False)
        self.window.set_focus_on_map(False)
        self.window.set_skip_taskbar_hint(True)
        self.window.set_skip_pager_hint(True)
        self.window.set_keep_above(True)
        self.window.set_resizable(False)
        self.window.set_default_size(WIDTH, HEIGHT)
        self.window.set_size_request(WIDTH, HEIGHT)
        self.window.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
        self.window.set_title("Весёлый жираф")
        self.window.stick()

        screen = self.window.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None:
            self.window.set_visual(visual)

        self.window.connect("draw", self._on_draw)
        self.window.connect("button-press-event", self._on_press)
        self.window.connect("button-release-event", self._on_release)
        self.window.connect("motion-notify-event", self._on_motion)
        self.window.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.BUTTON_MOTION_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.window.set_role("yo-overlay")

    def native_id(self) -> int | None:
        gdk_win = self.window.get_window()
        if gdk_win is None:
            return None
        try:
            return int(gdk_win.get_xid())
        except Exception:
            return None

    def set_anchor(self, hwnd: int | None) -> None:
        return None

    def show_listening(self, status: str = "") -> None:
        self.status = status
        self.visible = True
        if not self.live:
            self._bars = []
            self._pending_amp = 0.0
        self._last_tick = 0.0
        self._place()
        self.window.realize()
        gdk_win = self.window.get_window()
        if gdk_win is not None:
            gdk_win.set_override_redirect(True)
        self.window.show_all()
        self.window.set_keep_above(True)
        if self._tick_id is None:
            self._tick_id = GLib.timeout_add(16, self._tick)

    def hide(self) -> None:
        self.visible = False
        self.preview = ""
        self.status = ""
        self.hint = ""
        self.mic_missing = False
        self.live = False
        self.live_since = None
        self.task = "transcribe"
        self.window.hide()
        self._persist_pos()
        sid = self._tick_id
        self._tick_id = None
        if sid is not None:
            try:
                GLib.source_remove(sid)
            except Exception:
                pass

    def set_task(self, task: str) -> None:
        self.task = "translate" if task == "translate" else "transcribe"

    def set_status(self, status: str) -> None:
        self.status = status
        if self.visible:
            self.window.queue_draw()

    def set_live(self, live: bool) -> None:
        self.live = bool(live)
        self.live_since = time.monotonic() if self.live else None
        if not self.live:
            self._bars = []
            self._pending_amp = 0.0
        if self.visible:
            self.window.queue_draw()

    def set_preview(self, text: str) -> None:
        self.preview = text

    def set_mic_missing(self, missing: bool) -> None:
        self.mic_missing = bool(missing)
        if self.mic_missing:
            self.hint = NO_MIC_HINT
            self._bars = []
        elif self.hint == NO_MIC_HINT:
            self.hint = ""
        if self.visible:
            self.window.queue_draw()

    def set_hint(self, text: str) -> None:
        self.hint = (text or "").strip()
        if self.hint:
            self._bars = []
        if self.visible:
            self.window.queue_draw()

    def set_levels(self, rms_value: float, bands: list[float] | None = None, pcm=None) -> None:
        self.rms = float(rms_value)
        amp = wave_amplitude(self.rms)
        self._pending_amp += (amp - self._pending_amp) * 0.28
        self._speed_target = _voice_speed(self.rms, pcm)

    def _tick(self) -> bool:
        if not self.visible:
            self._tick_id = None
            return False
        now = time.monotonic()
        dt = 0.016 if self._last_tick <= 0 else min(0.05, now - self._last_tick)
        self._last_tick = now
        self._speed += (self._speed_target - self._speed) * 0.16
        if not wave_allowed(live=self.live, hint=self.hint, mic_missing=self.mic_missing):
            self._bars = []
            self.window.queue_draw()
            return True
        # ~15–28 px/s: вдвое медленнее прежнего, громче — чуть быстрее
        px_per_sec = 14.0 + 14.0 * self._speed
        step = 5.0
        width = _wave_width(self)
        for bar in self._bars:
            bar[0] -= px_per_sec * dt
        self._bars = [bar for bar in self._bars if bar[0] + 3.0 > -step]
        if not self._bars:
            self._bars.append([width, self._pending_amp])
        while self._bars[-1][0] < width:
            self._bars.append([self._bars[-1][0] + step, self._pending_amp])
            if len(self._bars) > 90:
                break
        self.window.queue_draw()
        return True

    def _persist_pos(self) -> None:
        if self._user_pos is None or self.on_move is None:
            return
        try:
            self.on_move(*self._user_pos)
        except Exception:
            pass

    def _place(self) -> None:
        if self._user_pos is not None:
            x, y = self._user_pos
            self.window.move(int(x), int(y))
            return
        screen = self.window.get_screen()
        display = self.window.get_display()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        geo = monitor.get_geometry() if monitor is not None else None
        if geo is None:
            sw, sh = screen.get_width(), screen.get_height()
            x = (sw - WIDTH) // 2
            y = sh - HEIGHT - 72
        else:
            x = geo.x + (geo.width - WIDTH) // 2
            y = geo.y + geo.height - HEIGHT - 72
        self.window.move(x, y)

    def _on_press(self, _widget, event) -> bool:
        button = getattr(event, "button", 1)
        if button == 3:
            if self.on_settings is not None:
                self.on_settings(event)
            return True
        if button != 1:
            return False
        wx, wy = self.window.get_position()
        self._drag = (event.x_root, event.y_root, wx, wy)
        gdk_win = self.window.get_window()
        if gdk_win is not None:
            try:
                seat = self.window.get_display().get_default_seat()
                seat.grab(
                    gdk_win,
                    Gdk.SeatCapabilities.POINTER,
                    False,
                    None,
                    event,
                    None,
                )
            except Exception:
                pass
        return True

    def _on_motion(self, _widget, event) -> bool:
        if self._drag is None:
            return False
        x0, y0, wx, wy = self._drag
        nx = int(wx + event.x_root - x0)
        ny = int(wy + event.y_root - y0)
        self.window.move(nx, ny)
        self._user_pos = (nx, ny)
        return True

    def _on_release(self, _widget, event) -> bool:
        self._drag = None
        try:
            self.window.get_display().get_default_seat().ungrab()
        except Exception:
            pass
        self._persist_pos()
        return True

    def _on_draw(self, _widget, cr) -> bool:
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        _draw_scene(cr, self)
        return False


def _load_orb():
    path = orb_path()
    if not path.exists():
        return None
    try:
        pix = GdkPixbuf.Pixbuf.new_from_file(str(path))
        src_w, src_h = pix.get_width(), pix.get_height()
        if src_h <= 0:
            return pix
        height = MASCOT_HEIGHT
        width = max(1, int(round(src_w * (height / src_h))))
        return pix.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)
    except Exception:
        return None


def _wave_width(overlay: Overlay) -> float:
    pix = overlay._pixbuf
    if pix is not None:
        return min(WIDTH - 20, max(96.0, pix.get_width() * 0.92))
    return float(WIDTH - 28)


def _draw_scene(cr, overlay: Overlay) -> None:
    w = WIDTH
    mascot_bottom = _draw_mascot(cr, overlay, w / 2, 4)
    if mascot_bottom > 4.0 + MASCOT_HEIGHT:
        mascot_bottom = 4.0 + MASCOT_HEIGHT
    wave_w = _wave_width(overlay)
    wave_x = (w - wave_w) / 2
    status_y = mascot_bottom + WAVE_GAP
    waves_on = wave_allowed(
        live=overlay.live, hint=overlay.hint, mic_missing=overlay.mic_missing
    )
    status_h = float(STATUS_HEIGHT) if waves_on else max(
        float(STATUS_HEIGHT), HEIGHT - status_y - 4.0
    )
    status_w = float(WIDTH - 12)
    status_x = (WIDTH - status_w) / 2.0
    _draw_status(cr, overlay, status_x, status_y, status_w, status_h)
    if waves_on:
        _draw_waves(cr, overlay, wave_x, status_y + STATUS_HEIGHT + WAVE_GAP, wave_w, WAVE_HEIGHT)


def _draw_mascot(cr, overlay: Overlay, cx, top) -> float:
    pix = overlay._pixbuf
    if pix is None:
        cr.select_font_face("Ubuntu", 0, 1)
        cr.set_font_size(28)
        cr.set_source_rgba(0.9, 0.95, 1.0, 0.9)
        cr.move_to(cx - 10, top + 40)
        cr.show_text("ЙО")
        return top + 80
    pw, ph = pix.get_width(), pix.get_height()
    px = cx - pw / 2
    py = top
    Gdk.cairo_set_source_pixbuf(cr, pix, px, py)
    cr.paint()
    return top + ph


def _voice_speed(rms_value: float, pcm) -> float:
    loud = voice_loudness(rms_value)
    if pcm is None or len(pcm) < 8:
        return loud
    zc = 0
    prev = float(pcm[0])
    for sample in pcm[1:]:
        value = float(sample)
        if prev == 0.0 or (prev < 0.0) != (value < 0.0):
            zc += 1
        prev = value
    rate = min(1.0, (zc / max(1, len(pcm) - 1)) * 8.0)
    return min(1.0, 0.55 * loud + 0.45 * rate)


def _envelope(pcm, n: int) -> list[float]:
    length = len(pcm)
    out = [0.0] * n
    if length <= 0:
        return out
    step = max(1.0, length / n)
    gain = 16.0
    for i in range(n):
        a = int(i * step)
        b = int((i + 1) * step)
        if b <= a:
            b = min(length, a + 1)
        peak = 0.0
        for sample in pcm[a:b]:
            v = float(sample)
            if v < 0:
                v = -v
            if v > peak:
                peak = v
        out[i] = min(1.0, peak * gain)
    return out


def _draw_mic_hint(cr, x, y, width, height, label: str = NO_MIC_HINT) -> None:
    cr.select_font_face("Ubuntu", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    size = 14.0
    while size >= 10.0:
        cr.set_font_size(size)
        _xb, _yb, tw, th, _dx, _dy = cr.text_extents(label)
        if tw <= max(8.0, width - 8.0):
            break
        size -= 1.0
    pad_x, pad_y = 7.0, 3.0
    bx = x + (width - tw) / 2.0 - pad_x
    by = y + height / 2.0 - th / 2.0 - pad_y
    cr.set_source_rgba(0.08, 0.09, 0.11, 0.92)
    _rounded_bar(cr, bx, by, tw + pad_x * 2.0, th + pad_y * 2.0, 6.0)
    cr.fill()
    cr.set_line_width(1.0)
    cr.set_source_rgba(0.17, 0.20, 0.24, 1.0)
    _rounded_bar(cr, bx, by, tw + pad_x * 2.0, th + pad_y * 2.0, 6.0)
    cr.stroke()
    tx = x + (width - tw) / 2.0
    ty = y + height / 2.0 + th / 2.0
    cr.set_source_rgba(0.05, 0.05, 0.07, 1.0)
    for dx, dy in ((-1.0, 0.0), (1.0, 0.0), (0.0, -1.0), (0.0, 1.0)):
        cr.move_to(tx + dx, ty + dy)
        cr.show_text(label)
    cr.set_source_rgba(0.96, 0.97, 0.98, 1.0)
    cr.move_to(tx, ty)
    cr.show_text(label)


def _rounded_bar(cr, x, y, w, h, r) -> None:
    r = min(r, w / 2, h / 2)
    cr.new_path()
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.arc(x + w - r, y + r, r, 3 * math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.close_path()


def _draw_status(cr, overlay: Overlay, x, y, width, height) -> None:
    label = display_label(
        live=overlay.live,
        now=time.monotonic(),
        live_since=overlay.live_since,
        hint=overlay.hint,
        mic_missing=overlay.mic_missing,
        status=overlay.status,
        task=overlay.task,
    )
    if not label:
        return
    _draw_mic_hint(cr, x, y, width, height, label)


def _draw_waves(cr, overlay: Overlay, x, y, width, height) -> None:
    if not wave_allowed(live=overlay.live, hint=overlay.hint, mic_missing=overlay.mic_missing):
        return
    bar_w = 3.0
    mid = y + height / 2.0
    cr.push_group()
    for bx, amp in overlay._bars:
        if bx + bar_w < 0 or bx > width:
            continue
        h = max(4.0, min(1.0, float(amp)) * height * 0.6)
        by = mid - h / 2.0
        cr.set_source_rgba(0.72, 0.74, 0.76, 0.30 + min(1.0, float(amp)) * 0.70)
        _rounded_bar(cr, x + bx, by, bar_w, h, 2.0)
        cr.fill()
    cr.pop_group_to_source()
    fade = cairo.LinearGradient(x, mid, x + width, mid)
    fade.add_color_stop_rgba(0.00, 0, 0, 0, 0)
    fade.add_color_stop_rgba(0.14, 0, 0, 0, 1)
    fade.add_color_stop_rgba(0.86, 0, 0, 0, 1)
    fade.add_color_stop_rgba(1.00, 0, 0, 0, 0)
    cr.mask(fade)


def run_demo(seconds: float = 8.0) -> None:
    Gtk.init([])
    overlay = Overlay(on_click=lambda: Gtk.main_quit())
    overlay.show_listening()
    overlay.set_live(True)
    started = time.monotonic()

    def tick() -> bool:
        elapsed = time.monotonic() - started
        if elapsed > seconds:
            Gtk.main_quit()
            return False
        env = 0.5 + 0.5 * math.sin(elapsed * 3.1)
        speak = abs(math.sin(elapsed * 1.3)) > 0.15
        level = (0.02 + 0.09 * env) if speak else 0.004
        bands = [
            abs(math.sin(elapsed * 2.2 + i * 0.45)) * (env if speak else 0.12)
            for i in range(12)
        ]
        samples = [
            (0.35 * env * math.sin(elapsed * 28 + i * 0.31) if speak else 0.004 * math.sin(i))
            for i in range(WAVE_BARS)
        ]
        overlay.set_levels(level, bands, samples)
        return True

    GLib.timeout_add(16, tick)
    Gtk.main()
