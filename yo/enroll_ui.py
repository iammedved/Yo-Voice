"""Окно записи образца голоса для «только мой голос» (Tk, Windows)."""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from yo.speaker import ENROLL_TEXT, quality_note, run_enrollment

log = logging.getLogger("yo.enroll")


def open_enroll_window(parent, *, microphone: str = "", on_done: Callable[[bool], None] | None = None) -> None:
    from yo.loop import idle_add

    win = tk.Toplevel(parent)
    win.title("Ёхо — мой голос")
    win.resizable(False, False)
    try:
        win.attributes("-topmost", True)
    except Exception:
        pass
    frame = ttk.Frame(win, padding=14)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text=ENROLL_TEXT, wraplength=420, justify="left").pack(anchor="w")
    status = tk.StringVar(value="Нажмите «Начать» и читайте текст около 25 секунд.")
    ttk.Label(frame, textvariable=status, wraplength=420, foreground="#555").pack(anchor="w", pady=(10, 6))
    start = ttk.Button(frame, text="Начать")
    start.pack(anchor="e")
    state = {"busy": False}

    def set_status(text: str) -> None:
        def apply() -> bool:
            try:
                status.set(text)
            except Exception:
                pass
            return False

        idle_add(apply)

    def finish(ok: bool, text: str) -> bool:
        state["busy"] = False
        try:
            status.set(text)
            start.configure(state="normal", text="Записать заново" if ok else "Попробовать ещё раз")
        except Exception:
            pass
        if on_done is not None:
            on_done(ok)
        return False

    def work() -> None:
        try:
            quality, seconds = run_enrollment(set_status, microphone=microphone)
        except Exception as exc:
            log.exception("запись образца голоса не удалась")
            idle_add(finish, False, f"Не получилось: {exc}")
            return
        log.info("образец голоса записан: %.0f с речи, качество %.2f", seconds, quality)
        idle_add(
            finish,
            True,
            f"Готово: {seconds:.0f} с речи, {quality_note(quality)}. Теперь Ёхо слушает только вас.",
        )

    def begin() -> None:
        if state["busy"]:
            return
        state["busy"] = True
        start.configure(state="disabled")
        status.set("готовлюсь…")
        threading.Thread(target=work, daemon=True, name="yo-enroll").start()

    start.configure(command=begin)
