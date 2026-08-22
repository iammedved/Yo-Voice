"""Выбор микрофона: меню у кота и отдельное CLI-окно без кражи фокуса."""

from __future__ import annotations

import logging

log = logging.getLogger("yo.settings")

_LIVE_MENUS: list = []


def window_flags(listening: bool) -> dict[str, bool]:
    return {"focus_on_map": False, "accept_focus": not listening}


def place_near_anchor(
    anchor: tuple[int, int, int, int],
    size: tuple[int, int],
    screen: tuple[int, int, int, int],
    gap: int = 8,
) -> tuple[int, int]:
    ax, ay, aw, ah = (int(v) for v in anchor)
    mw, mh = (int(v) for v in size)
    sx, sy, sw, sh = (int(v) for v in screen)
    gap = int(gap)
    right = sx + sw
    bottom = sy + sh
    right_x = ax + aw + gap
    if right_x + mw <= right:
        x, y = right_x, ay
    else:
        left_x = ax - gap - mw
        if left_x >= sx:
            x, y = left_x, ay
        else:
            x, y = ax, ay + ah + gap
    x = max(sx, min(x, right - mw))
    y = max(sy, min(y, bottom - mh))
    return int(x), int(y)


def _screen_rect(widget) -> tuple[int, int, int, int]:
    display = widget.get_display()
    gdk_win = widget.get_window() if hasattr(widget, "get_window") else None
    monitor = None
    if display is not None:
        if gdk_win is not None:
            monitor = display.get_monitor_at_window(gdk_win)
        if monitor is None:
            monitor = display.get_primary_monitor() or display.get_monitor(0)
    if monitor is not None:
        geo = monitor.get_geometry()
        return (int(geo.x), int(geo.y), int(geo.width), int(geo.height))
    screen = widget.get_screen()
    return (0, 0, int(screen.get_width()), int(screen.get_height()))


def _overlay_anchor(cfg) -> tuple[int, int, int, int] | None:
    if cfg.overlay_x is None or cfg.overlay_y is None:
        return None
    from yo.overlay import HEIGHT, WIDTH

    return (int(cfg.overlay_x), int(cfg.overlay_y), int(WIDTH), int(HEIGHT))


def _menu_gravity(widget, menu):
    from gi.repository import Gdk

    from yo.overlay import HEIGHT, WIDTH

    min_req, nat_req = menu.get_preferred_size()
    mw = max(int(nat_req.width or min_req.width or 0), 240)
    mh = max(int(nat_req.height or min_req.height or 0), 140)
    wx, wy = widget.get_position()
    ww = int(widget.get_allocated_width() or WIDTH)
    wh = int(widget.get_allocated_height() or HEIGHT)
    x, _y = place_near_anchor((int(wx), int(wy), ww, wh), (mw, mh), _screen_rect(widget))
    if x >= int(wx) + ww:
        return Gdk.Gravity.EAST, Gdk.Gravity.WEST
    if x + mw <= int(wx):
        return Gdk.Gravity.WEST, Gdk.Gravity.EAST
    return Gdk.Gravity.SOUTH, Gdk.Gravity.NORTH


def popup_mic_menu(widget=None, event=None, on_pick=None) -> None:
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gtk

    from yo.capture import list_capture_devices
    from yo.config import load_config, save_config

    cfg = load_config()
    wanted = (cfg.microphone or "").strip()
    menu = Gtk.Menu()
    if widget is not None:
        try:
            menu.attach_to_widget(widget, None)
        except Exception:
            log.exception("не удалось привязать меню к оверлею")

    group = []
    armed = {"ok": False}

    def add_item(ident: str, title: str) -> None:
        item = Gtk.RadioMenuItem.new_with_label(group, title)
        group[:] = item.get_group()
        if ident == wanted or (not wanted and ident == ""):
            item.set_active(True)

        def on_toggled(radio, name=ident) -> None:
            if not armed["ok"] or not radio.get_active():
                return
            current = load_config()
            current.microphone = name
            save_config(current)
            if on_pick is not None:
                on_pick(name)

        item.connect("toggled", on_toggled)
        menu.append(item)

    add_item("", "Авто")
    for device in list_capture_devices():
        ident = str(device.get("id") or "")
        if not ident:
            continue
        add_item(ident, str(device.get("label") or ident))

    armed["ok"] = True
    menu.show_all()
    _LIVE_MENUS.append(menu)

    def forget(*_args) -> None:
        try:
            _LIVE_MENUS.remove(menu)
        except ValueError:
            pass

    menu.connect("deactivate", forget)

    if event is not None:
        try:
            menu.popup_at_pointer(event)
            return
        except Exception:
            log.exception("меню не встало по указателю")
    if widget is not None:
        try:
            widget_anchor, menu_anchor = _menu_gravity(widget, menu)
            menu.popup_at_widget(widget, widget_anchor, menu_anchor, event)
            return
        except Exception:
            log.exception("меню не встало у кота")
    menu.popup(None, None, None, None, 0, Gtk.get_current_event_time())


def run_settings() -> None:
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk

    from yo.capture import list_capture_devices
    from yo.config import load_config, save_config
    from yo.ipc import daemon_alive, send_command

    listening = False
    if daemon_alive():
        try:
            listening = send_command("status") == "listening"
        except OSError:
            listening = False

    Gtk.init([])
    flags = window_flags(listening)
    win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
    win.set_title("Ёхо — микрофон")
    win.set_default_size(380, 96)
    win.set_focus_on_map(flags["focus_on_map"])
    win.set_accept_focus(flags["accept_focus"])
    win.connect("destroy", Gtk.main_quit)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    box.set_border_width(12)
    label = Gtk.Label(label="Микрофон", xalign=0)
    combo = Gtk.ComboBoxText()
    combo.append("", "Авто")
    for item in list_capture_devices():
        ident = str(item.get("id") or "")
        if not ident:
            continue
        combo.append(ident, str(item.get("label") or ident))

    cfg = load_config()
    wanted = (cfg.microphone or "").strip()
    combo.set_active_id(wanted)
    if combo.get_active_id() is None:
        combo.set_active_id("")

    armed = {"ok": False}

    def on_changed(_combo) -> None:
        if not armed["ok"]:
            return
        ident = combo.get_active_id() or ""
        current = load_config()
        current.microphone = ident
        save_config(current)
        if daemon_alive():
            try:
                send_command("reload")
            except OSError:
                log.warning("демон Ёхо не принял reload")

    combo.connect("changed", on_changed)
    armed["ok"] = True
    box.pack_start(label, False, False, 0)
    box.pack_start(combo, False, False, 0)
    win.add(box)
    anchor = _overlay_anchor(cfg)
    screen = _screen_rect(win)
    if anchor is not None:
        x, y = place_near_anchor(anchor, (380, 96), screen)
    else:
        sx, sy, sw, sh = screen
        x = sx + max(0, (sw - 380) // 2)
        y = sy + max(0, (sh - 96) // 2)
    win.move(x, y)
    win.show_all()
    Gtk.main()
