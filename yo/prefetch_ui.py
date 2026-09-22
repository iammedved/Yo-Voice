"""Окно скачивания модели. Процент берётся из байтов, не из таймера."""

from __future__ import annotations

import logging
import queue
import threading
from datetime import datetime

from yo.fetchprog import PrefetchResult, percent, prefetch_whisper

log = logging.getLogger("yo.prefetch")


def run_prefetch_window() -> tuple[int, bool]:
    """Скачать модель и показать 1..100. Вернуть (код, уже_была_на_диске).

    Код 0 — файлы сверены. Уже_была_на_диске значит качать было нечего:
    вызывающий не должен из-за этого перезапускать программу.
    """
    import tkinter as tk
    from tkinter import ttk

    events: queue.Queue = queue.Queue()
    holder: dict = {"result": None, "error": None, "closed": False}

    def worker() -> None:
        try:
            holder["result"] = prefetch_whisper(
                lambda done, total, phase: events.put(("progress", int(done), int(total), phase))
            )
        except Exception as exc:
            holder["error"] = exc
            log.exception("модель распознавания не скачалась")
        events.put(("end",))

    root = tk.Tk()
    root.title("Ёхо — модель распознавания")
    root.resizable(False, False)
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass
    frame = ttk.Frame(root, padding=16)
    frame.pack(fill="both", expand=True)
    status = tk.StringVar(value="Скачивание модели распознавания")
    ttk.Label(frame, textvariable=status).pack(anchor="w")
    value = tk.IntVar(value=1)
    ttk.Progressbar(frame, maximum=100, variable=value, length=360).pack(pady=(10, 6))
    pct_var = tk.StringVar(value="1%")
    ttk.Label(frame, textvariable=pct_var).pack(anchor="w")

    def apply(done: int, total: int, phase: str) -> None:
        shown = percent(done, total)
        if phase != "check" and shown >= 100:
            shown = 99
        value.set(shown)
        pct_var.set(f"{shown}%")
        if phase == "check":
            status.set("Проверка файлов модели")
        else:
            status.set("Скачивание модели распознавания")

    def poll() -> None:
        if holder["closed"]:
            return
        try:
            while True:
                event = events.get_nowait()
                if event[0] == "end":
                    root.destroy()
                    return
                _kind, done, total, phase = event
                apply(done, total, phase)
        except queue.Empty:
            pass
        root.after(50, poll)

    def on_close() -> None:
        holder["closed"] = True
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    threading.Thread(target=worker, daemon=True, name="yo-prefetch").start()
    root.after(50, poll)
    root.mainloop()

    if holder["closed"] and holder["result"] is None and holder["error"] is None:
        return 1, False
    error = holder["error"]
    if error is not None:
        _show_download_error(error)
        return 1, False
    result = holder["result"]
    if not isinstance(result, PrefetchResult):
        return 1, False
    return 0, bool(result.already_present)


def _show_download_error(exc: BaseException) -> None:
    try:
        from yo.report import build_report
        from yo.report_ui import show_report

        report = build_report(
            "скачивание модели распознавания",
            exc,
            block="model",
            now=datetime.now(),
        )
        show_report(report)
    except Exception:
        log.exception("не удалось показать отчёт о загрузке")
