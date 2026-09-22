"""Microphone / rebind window on Windows. Toplevel, not tk_popup (GIL crash)."""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk

from yo.bind import format_bind, normalize_bind, optional_bind
from yo.capture import list_capture_devices
from yo.config import load_config, save_config
from yo.ipc import daemon_alive, send_command
from yo.settings import place_near_anchor, window_flags

log = logging.getLogger("yo.settings")

_LIVE_WIN: tk.Toplevel | None = None


def popup_mic_menu(
    widget=None,
    event=None,
    on_pick=None,
    on_rebind=None,
    on_rebind_translate=None,
    listening: bool | None = None,
) -> None:
    """Open the settings panel next to the cat. Name kept for Linux-parity tests."""
    run_settings_window(
        widget=widget,
        event=event,
        on_pick=on_pick,
        on_rebind=on_rebind,
        on_rebind_translate=on_rebind_translate,
        own_loop=False,
        listening=listening,
    )


def run_settings() -> None:
    from yo.loop import loop_init, loop_main, loop_quit, tk_root

    created = False
    try:
        tk_root()
    except RuntimeError:
        loop_init()
        created = True
    run_settings_window(own_loop=created)
    if created:
        try:
            loop_main()
        finally:
            loop_quit()


def run_settings_window(
    widget=None,
    event=None,
    on_pick=None,
    on_rebind=None,
    on_rebind_translate=None,
    *,
    own_loop: bool = False,
    listening: bool | None = None,
) -> None:
    global _LIVE_WIN
    from yo.loop import tk_root
    from yo.overlay import HEIGHT, WIDTH
    from yo.winapi import cursor_pos

    if listening is None:
        listening = False
        if own_loop and daemon_alive():
            try:
                listening = send_command("status") == "listening"
            except OSError:
                listening = False

    try:
        root = tk_root()
    except RuntimeError:
        log.warning("цикл Ёхо ещё не запущен — окно настроек не открыть")
        return

    if _LIVE_WIN is not None:
        try:
            if _LIVE_WIN.winfo_exists():
                try:
                    _LIVE_WIN.deiconify()
                except Exception:
                    pass
                try:
                    _LIVE_WIN.lift()
                    _LIVE_WIN.attributes("-topmost", True)
                except Exception:
                    pass
                return
        except Exception:
            pass
        _LIVE_WIN = None

    flags = window_flags(listening)
    win = tk.Toplevel(root)
    win.title("Ёхо — настройки")
    win.resizable(False, False)
    try:
        win.update_idletasks()
    except Exception:
        pass
    try:
        win.attributes("-topmost", True)
    except Exception:
        pass
    if not flags["accept_focus"]:
        try:
            win.attributes("-toolwindow", True)
        except Exception:
            pass

    frame = ttk.Frame(win, padding=14)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Микрофон").pack(anchor="w")

    values = [("", "Авто")]
    try:
        devices = list_capture_devices()
    except Exception:
        log.exception("не удалось получить список микрофонов")
        devices = []
    for item in devices:
        ident = str(item.get("id") or "")
        if ident:
            values.append((ident, str(item.get("label") or ident)))
    labels = [label for _ident, label in values]
    combo = ttk.Combobox(frame, values=labels, state="readonly", width=42)
    cfg = load_config()
    wanted = (cfg.microphone or "").strip()
    index = 0
    for i, (ident, _label) in enumerate(values):
        if ident == wanted:
            index = i
            break
    combo.current(index)
    combo.pack(fill="x", pady=(4, 10))
    armed = {"ok": False}

    def on_changed(_event=None) -> None:
        if not armed["ok"]:
            return
        sel = combo.current()
        ident = values[sel][0] if 0 <= sel < len(values) else ""
        current = load_config()
        current.microphone = ident
        save_config(current)
        if on_pick is not None:
            on_pick(ident)
        elif daemon_alive():
            try:
                send_command("reload")
            except OSError:
                log.warning("демон Ёхо не принял reload")

    combo.bind("<<ComboboxSelected>>", on_changed)

    ttk.Separator(frame).pack(fill="x", pady=(0, 10))
    ttk.Label(frame, text="Клавиша диктовки (нажать — говорить, нажать ещё раз — вставить)").pack(anchor="w")
    bind = normalize_bind(cfg.hotkey_kind, cfg.hotkey_keycode)
    bind_var = tk.StringVar(value=format_bind(bind))
    row = ttk.Frame(frame)
    row.pack(fill="x", pady=(4, 8))
    ttk.Label(row, textvariable=bind_var).pack(side="left")
    def _do_rebind() -> None:
        if on_rebind is not None:
            win.destroy()
            on_rebind()
            return
        if daemon_alive():
            try:
                send_command("rebind")
                bind_var.set("нажмите кнопку — смотрите кота")
                return
            except OSError:
                log.warning("демон Ёхо не принял rebind")
        _capture_here("transcribe")

    def _apply_captured(bind, *, target: str) -> None:
        from yo.bind import binds_conflict
        from yo.loop import idle_add

        def apply() -> None:
            if bind is None:
                bind_var.set(format_bind(normalize_bind(*_current_listen())))
                trans_var.set(_current_translate_label())
                return
            current = load_config()
            if target == "translate":
                other = normalize_bind(current.hotkey_kind, current.hotkey_keycode)
                if binds_conflict(bind, other):
                    trans_var.set("кнопка уже занята")
                    return
                current.translate_hotkey_kind = bind.kind
                current.translate_hotkey_keycode = bind.code
                trans_var.set(format_bind(bind))
            else:
                other = optional_bind(current.translate_hotkey_kind, current.translate_hotkey_keycode)
                if binds_conflict(bind, other):
                    bind_var.set("кнопка уже занята")
                    return
                current.hotkey_kind = bind.kind
                current.hotkey_keycode = bind.code
                bind_var.set(format_bind(bind))
            save_config(current)
            if daemon_alive():
                try:
                    send_command("reload")
                except OSError:
                    log.warning("демон Ёхо не принял reload")

        idle_add(apply)

    def _current_listen() -> tuple[str, int]:
        current = load_config()
        b = normalize_bind(current.hotkey_kind, current.hotkey_keycode)
        return b.kind, b.code

    def _current_translate_label() -> str:
        current = load_config()
        trans = optional_bind(current.translate_hotkey_kind, current.translate_hotkey_keycode)
        return format_bind(trans) if trans else "не назначена"

    def _capture_here(target: str) -> None:
        from yo.bind import capture_bind

        if target == "translate":
            trans_var.set("нажмите кнопку")
        else:
            bind_var.set("нажмите кнопку")
        capture_bind(lambda captured, t=target: _apply_captured(captured, target=t))

    ttk.Button(row, text="Назначить кнопку", command=_do_rebind).pack(side="right")

    trans = optional_bind(cfg.translate_hotkey_kind, cfg.translate_hotkey_keycode)
    trans_var = tk.StringVar(value=format_bind(trans) if trans else "не назначена")
    ttk.Label(frame, text="Клавиша перевода").pack(anchor="w")
    row2 = ttk.Frame(frame)
    row2.pack(fill="x", pady=(4, 8))
    ttk.Label(row2, textvariable=trans_var).pack(side="left")
    def _do_rebind_translate() -> None:
        if on_rebind_translate is not None:
            win.destroy()
            on_rebind_translate()
            return
        if daemon_alive():
            try:
                send_command("rebind-translate")
                trans_var.set("нажмите кнопку — смотрите кота")
                return
            except OSError:
                log.warning("демон Ёхо не принял rebind-translate")
        _capture_here("translate")

    ttk.Button(row2, text="Назначить кнопку перевода", command=_do_rebind_translate).pack(side="right")

    ttk.Label(
        frame,
        text="После «Назначить» кот напишет «нажмите кнопку» — нажмите новую клавишу.",
        wraplength=360,
        foreground="#555",
    ).pack(anchor="w", pady=(4, 0))

    armed["ok"] = True

    def place() -> None:
        w, h = 400, 250
        if event is not None and getattr(event, "x_root", None) is not None:
            x, y = int(event.x_root), int(event.y_root)
        elif cfg.overlay_x is not None and cfg.overlay_y is not None:
            x, y = place_near_anchor(
                (int(cfg.overlay_x), int(cfg.overlay_y), int(WIDTH), int(HEIGHT)),
                (w, h),
                (0, 0, win.winfo_screenwidth(), win.winfo_screenheight()),
            )
        else:
            x, y = cursor_pos()
        win.geometry(f"{w}x{h}+{x}+{y}")

    place()
    def forget(_event=None) -> None:
        global _LIVE_WIN
        if _LIVE_WIN is win:
            _LIVE_WIN = None

    def close() -> None:
        forget()
        try:
            win.destroy()
        except Exception:
            pass
        if own_loop:
            from yo.loop import loop_quit

            loop_quit()

    win.protocol("WM_DELETE_WINDOW", close)
    _LIVE_WIN = win
    win.bind("<Destroy>", forget)
