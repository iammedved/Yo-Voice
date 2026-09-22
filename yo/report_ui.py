"""Окно отчёта. Одна кнопка открывает задачу на GitHub."""

from __future__ import annotations

import logging

from yo.report import Report, issue_url

log = logging.getLogger("yo.report")

# Above this length the prefilled link is also copied, still one button.
ISSUE_URL_LIMIT = 1800


def show_report(report: Report) -> str:
    """Показать поля отчёта. Возвращает ``send`` или ``close``."""
    import tkinter as tk
    import webbrowser
    from tkinter import ttk

    result = {"value": "close"}
    parent, own_loop = _host(tk)
    win = parent if own_loop else tk.Toplevel(parent)
    try:
        win.title("Ёхо — отчёт")
        win.minsize(460, 280)
        try:
            win.attributes("-topmost", True)
        except tk.TclError:
            pass

        frame = ttk.Frame(win, padding=14)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        rows = (
            ("Когда", report.when),
            ("Блок", report.block),
            ("Код", report.code),
            ("Что делали", report.what),
            ("Почему", report.why),
        )
        for row, (label, value) in enumerate(rows):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="ne", padx=(0, 10), pady=2)
            _put_value(tk, ttk, frame, row, value)

        detail_row = len(rows)
        ttk.Label(frame, text="Подробности").grid(
            row=detail_row, column=0, sticky="ne", padx=(0, 10), pady=2
        )
        _put_detail(tk, ttk, frame, detail_row, report.detail)

        url = issue_url(report)
        long_url = len(url) > ISSUE_URL_LIMIT
        if long_url:
            hint = ttk.Label(
                frame,
                text="Ссылка длинная: кнопка ещё скопирует текст в буфер обмена.",
                wraplength=440,
                justify="left",
            )
            hint.grid(row=detail_row + 1, column=0, columnspan=2, sticky="w", pady=(10, 0))

        buttons = ttk.Frame(frame)
        buttons.grid(row=detail_row + 2, column=0, columnspan=2, sticky="w", pady=(12, 0))

        def on_close() -> None:
            result["value"] = "close"
            win.destroy()

        def on_send() -> None:
            if long_url:
                _copy_text(win, report.text())
            try:
                webbrowser.open(url)
            except Exception:
                log.exception("не удалось открыть страницу отчёта")
            result["value"] = "send"
            win.destroy()

        send_btn = ttk.Button(buttons, text="Отправить разработчику", command=on_send)
        send_btn.pack(side="left")
        ttk.Button(buttons, text="Закрыть", command=on_close).pack(side="left", padx=(8, 0))
        win.protocol("WM_DELETE_WINDOW", on_close)
        win.bind("<Escape>", lambda _event: on_close())

        win.update_idletasks()
        _place(win)
        try:
            win.lift()
            send_btn.focus_set()
        except tk.TclError:
            pass

        if own_loop:
            win.mainloop()
        else:
            parent.wait_window(win)
    finally:
        if own_loop:
            try:
                if win.winfo_exists():
                    win.destroy()
            except Exception:
                pass
    return result["value"]


def _host(tk):
    try:
        from yo.loop import tk_root

        return tk_root(), False
    except Exception:
        pass
    existing = getattr(tk, "_default_root", None)
    if existing is not None:
        return existing, False
    return tk.Tk(), True


def _place(win) -> None:
    width = max(win.winfo_width(), 480)
    height = win.winfo_height()
    screen_w = win.winfo_screenwidth()
    screen_h = win.winfo_screenheight()
    x = max(0, (screen_w - width) // 2)
    y = max(0, (screen_h - height) // 3)
    win.geometry(f"+{x}+{y}")


def _put_value(tk, ttk, frame, row: int, value: str) -> None:
    holder = ttk.Frame(frame)
    holder.grid(row=row, column=1, sticky="ew", pady=2)
    if len(value) > 240 or "\n" in value:
        _readonly_text(tk, ttk, holder, value, height=4)
        return
    ttk.Label(holder, text=value, wraplength=420, justify="left").pack(anchor="w")


def _put_detail(tk, ttk, frame, row: int, value: str) -> None:
    holder = ttk.Frame(frame)
    holder.grid(row=row, column=1, sticky="nsew", pady=2)
    frame.rowconfigure(row, weight=1)
    if not value:
        ttk.Label(holder, text="").pack(anchor="w")
        return
    _readonly_text(tk, ttk, holder, value, height=8)


def _readonly_text(tk, ttk, holder, value: str, *, height: int) -> None:
    box = ttk.Frame(holder)
    box.pack(fill="both", expand=True)
    text = tk.Text(box, height=height, width=52, wrap="word", relief="solid", borderwidth=1)
    scroll = ttk.Scrollbar(box, command=text.yview)
    text.configure(yscrollcommand=scroll.set)
    text.insert("1.0", value)
    text.configure(state="disabled")
    text.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")


def _copy_text(widget, text: str) -> None:
    widget.clipboard_clear()
    widget.clipboard_append(text)
    widget.update()
