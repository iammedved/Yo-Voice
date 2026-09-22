"""Tk + Win32 main loop: idle/timeout like GLib, without GTK."""

from __future__ import annotations

import ctypes
import logging
import threading
import tkinter as tk
from collections.abc import Callable
from typing import Any

from yo.winapi import (
    WM_APP,
    WNDCLASSW,
    WNDPROC,
    WS_EX_TOOLWINDOW,
    WS_POPUP,
    kernel32,
    set_dpi_aware,
    user32,
)

log = logging.getLogger("yo.loop")

YO_IDLE = WM_APP + 1
WM_TRAYICON = WM_APP + 5

_root: tk.Tk | None = None
_msg_hwnd = None
_wndproc_ref = None
_jobs: dict[int, tuple[Callable, tuple]] = {}
_job_i = 0
_jobs_lock = threading.Lock()
_sources: dict[int, str] = {}
_source_i = 0
_source_lock = threading.Lock()
_inited = False
_tray_handler = None
_tray_restore = None
_pending: list[int] = []
_tray_events: list[int] = []
_taskbar_created = 0
_pumping = False


def tk_root() -> tk.Tk:
    if _root is None:
        raise RuntimeError("цикл Ёхо ещё не запущен")
    return _root


def message_hwnd():
    return _msg_hwnd


def set_tray_handler(fn) -> None:
    global _tray_handler
    _tray_handler = fn


def set_tray_restore(fn) -> None:
    global _tray_restore
    _tray_restore = fn


def _wndproc(hwnd, msg, wparam, lparam):
    # ctypes WNDPROC must not call Tk/Python jobs (bpo-40075 GIL abort).
    if msg == YO_IDLE:
        with _jobs_lock:
            jid = int(wparam)
            if jid not in _pending:
                _pending.append(jid)
        return 0
    if msg == WM_TRAYICON:
        with _jobs_lock:
            _tray_events.append(int(lparam) & 0xFFFF)
        return 0
    if _taskbar_created and msg == _taskbar_created:
        with _jobs_lock:
            _tray_events.append(-1)
        return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def _drain() -> None:
    while True:
        with _jobs_lock:
            jid = _pending.pop(0) if _pending else None
        if jid is None:
            break
        _run_job(jid)
    while True:
        with _jobs_lock:
            event = _tray_events.pop(0) if _tray_events else None
        if event is None:
            break
        if event == -1:
            cb = _tray_restore
            if cb is not None:
                try:
                    cb()
                except Exception:
                    log.exception("ошибка восстановления трея")
            continue
        cb = _tray_handler
        if cb is not None:
            try:
                cb(event)
            except Exception:
                log.exception("ошибка иконки в трее")


def _pump() -> None:
    global _pumping
    if _root is None:
        _pumping = False
        return
    _drain()
    _root.after(20, _pump)


def loop_init() -> None:
    global _root, _msg_hwnd, _wndproc_ref, _inited, _taskbar_created, _pumping
    if _inited and _root is not None:
        return
    set_dpi_aware()
    existing = getattr(tk, "_default_root", None)
    _root = existing if existing is not None else tk.Tk()
    _root.withdraw()
    try:
        _root.wm_attributes("-toolwindow", True)
    except Exception:
        pass
    try:
        _root.protocol("WM_DELETE_WINDOW", lambda: None)
    except Exception:
        pass
    _wndproc_ref = WNDPROC(_wndproc)
    class_name = "YoVoiceLoop"
    wc = WNDCLASSW()
    wc.lpfnWndProc = _wndproc_ref
    wc.hInstance = kernel32.GetModuleHandleW(None)
    wc.lpszClassName = class_name
    atom = user32.RegisterClassW(ctypes.byref(wc))
    if not atom:
        err = ctypes.get_last_error()
        if err not in (0, 1410):  # ERROR_CLASS_ALREADY_EXISTS
            log.warning("RegisterClassW failed winerr=%s", err)
    # Top-level popup owner so the tray menu can dismiss correctly.
    _msg_hwnd = user32.CreateWindowExW(
        WS_EX_TOOLWINDOW,
        class_name,
        "yo-loop",
        WS_POPUP,
        0,
        0,
        0,
        0,
        None,
        None,
        wc.hInstance,
        None,
    )
    if not _msg_hwnd:
        raise ctypes.WinError(ctypes.get_last_error(), "не удалось создать очередь сообщений Ёхо")
    try:
        user32.RegisterWindowMessageW.argtypes = [ctypes.c_wchar_p]
        user32.RegisterWindowMessageW.restype = ctypes.c_uint
        _taskbar_created = int(user32.RegisterWindowMessageW("TaskbarCreated"))
        if _taskbar_created:
            try:
                user32.ChangeWindowMessageFilterEx.argtypes = [
                    ctypes.c_void_p,
                    ctypes.c_uint,
                    ctypes.c_ulong,
                    ctypes.c_void_p,
                ]
                user32.ChangeWindowMessageFilterEx.restype = ctypes.c_int
                user32.ChangeWindowMessageFilterEx(_msg_hwnd, _taskbar_created, 1, None)
            except Exception:
                pass
    except Exception:
        _taskbar_created = 0
    if not _pumping:
        _pumping = True
        _root.after(20, _pump)
    _inited = True


def idle_add(fn: Callable, *args: Any) -> int:
    global _job_i
    with _jobs_lock:
        _job_i += 1
        jid = _job_i
        _jobs[jid] = (fn, args)
    hwnd = _msg_hwnd
    if hwnd:
        user32.PostMessageW(hwnd, YO_IDLE, jid, 0)
    if _root is not None and threading.current_thread() is threading.main_thread():
        _root.after(0, _drain)
    return jid


def _run_job(jid: int) -> None:
    with _jobs_lock:
        job = _jobs.pop(jid, None)
    if job is None:
        return
    fn, args = job
    try:
        fn(*args)
    except Exception:
        log.exception("ошибка idle")


def timeout_add(ms: int, fn: Callable, *args: Any) -> int:
    global _source_i
    if _root is None:
        raise RuntimeError("цикл Ёхо ещё не запущен")
    if threading.current_thread() is not threading.main_thread():
        idle_add(lambda: timeout_add(ms, fn, *args))
        return 0
    with _source_lock:
        _source_i += 1
        sid = _source_i

    delay = max(1, int(ms))

    def wrap() -> None:
        if sid not in _sources:
            return
        try:
            keep = fn(*args)
        except Exception:
            log.exception("ошибка таймера")
            _sources.pop(sid, None)
            return
        if keep:
            _sources[sid] = _root.after(delay, wrap)  # type: ignore[union-attr]
        else:
            _sources.pop(sid, None)

    _sources[sid] = _root.after(delay, wrap)
    return sid


def source_remove(sid: int | None) -> None:
    if sid is None:
        return
    after_id = _sources.pop(int(sid), None)
    if after_id is not None and _root is not None:
        try:
            _root.after_cancel(after_id)
        except Exception:
            pass


def loop_main() -> None:
    if _root is None:
        raise RuntimeError("цикл Ёхо ещё не запущен")
    _root.mainloop()


def loop_quit() -> None:
    root = _root
    if root is None:
        return
    try:
        root.quit()
    except Exception:
        pass
