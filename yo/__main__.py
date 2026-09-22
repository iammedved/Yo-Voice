"""Точка входа: yo-voice toggle|daemon|demo|start|stop|status|settings."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path


def default_command(*, frozen: bool | None = None, platform: str | None = None) -> str:
    """Linux / source CLI defaults to toggle. Frozen Windows exe stays resident."""
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))
    if platform is None:
        platform = sys.platform
    if platform == "win32" and frozen:
        return "daemon"
    return "toggle"


def _crash_log_path() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    folder = Path(base) / "yo-voice"
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        folder = Path.cwd()
    return folder / "daemon.log"


def _append_crash(text: str) -> None:
    try:
        with _crash_log_path().open("a", encoding="utf-8") as fh:
            fh.write(text)
            if not text.endswith("\n"):
                fh.write("\n")
            fh.flush()
    except OSError:
        pass


def _message_box(text: str) -> None:
    if sys.platform != "win32":
        return
    try:
        from yo.winapi import message_box

        message_box(text)
        return
    except Exception:
        pass
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, str(text), "Ёхо", 0x00000010)
    except Exception:
        pass


def _report_fatal(exc: BaseException) -> None:
    tb = traceback.format_exc()
    _append_crash(tb)
    log_file = _crash_log_path()
    _message_box(f"Ёхо не запустилась:\n{exc}\n\nЖурнал: {log_file}")


def main(argv: list[str] | None = None) -> int:
    try:
        return _run(argv)
    except KeyboardInterrupt:
        return 130
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        _append_crash(str(code))
        return 1
    except Exception as exc:
        _report_fatal(exc)
        return 1


def _run(argv: list[str] | None = None) -> int:
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    try:
        from yo.logutil import setup_logging
        from yo.paths import xdg_cache

        os.environ.setdefault("HF_HOME", str(xdg_cache() / "hf"))
        setup_logging()
    except Exception:
        _append_crash(traceback.format_exc())
        raise
    from yo.cuda_env import setup_cuda_libs
    from yo.ipc import daemon_alive, send_command

    setup_cuda_libs()
    parser = argparse.ArgumentParser(
        prog="yo-voice",
        description="Ёхо — голосовой ввод в активное текстовое поле",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default=default_command(),
        choices=("toggle", "start", "stop", "daemon", "demo", "status", "quit", "settings", "bind", "reload"),
    )
    parser.add_argument(
        "bind_spec",
        nargs="*",
        help="для bind: имя или код клавиши (F8, 0x77, ё, mouse:8)",
    )
    parser.add_argument("--seconds", type=float, default=8.0, help="длительность демо overlay")
    args = parser.parse_args(argv)

    if args.command == "daemon":
        from yo.app import run_daemon

        setup_logging()
        run_daemon()
        return 0
    if args.command == "demo":
        from yo.overlay import run_demo

        run_demo(args.seconds)
        return 0
    if args.command == "settings":
        from yo.settings import run_settings

        run_settings()
        return 0
    if args.command == "bind":
        return _cmd_bind(args.bind_spec)

    if not daemon_alive():
        if args.command in {"status", "quit"}:
            print("Ёхо не запущена")
            return 1 if args.command == "status" else 0
        if not _spawn_daemon():
            msg = "не удалось запустить Ёхо в фоне"
            print(msg, file=sys.stderr)
            if sys.platform == "win32" and getattr(sys, "frozen", False):
                _message_box(f"{msg}\n\nЖурнал: {_crash_log_path()}")
            return 1

    try:
        reply = send_command(args.command)
    except OSError as exc:
        print(f"нет связи с Ёхо: {exc}", file=sys.stderr)
        return 1
    print(reply)
    return 0


def _cli_out(text: str, *, error: bool = False) -> None:
    stream = sys.stderr if error else sys.stdout
    try:
        print(text, file=stream)
        stream.flush()
    except Exception:
        pass
    if sys.platform != "win32":
        return
    try:
        tty = stream is not None and stream.isatty()
    except Exception:
        tty = False
    if tty:
        return
    # Parent captured stdout (pipe) already has the text — do not block on OK.
    try:
        import msvcrt

        from yo.winapi import kernel32

        handle = msvcrt.get_osfhandle(stream.fileno())
        if int(kernel32.GetFileType(handle)) == 3:  # FILE_TYPE_PIPE
            return
    except Exception:
        pass
    if getattr(sys, "frozen", False) or stream is None:
        try:
            from yo.winapi import message_box

            message_box(text, title="Ёхо", error=error)
        except Exception:
            pass


def _cmd_bind(spec_parts: list[str]) -> int:
    from yo.bind import binds_conflict, format_bind, normalize_bind, optional_bind, parse_bind_spec
    from yo.config import load_config, save_config
    from yo.ipc import daemon_alive, send_command

    cfg = load_config()
    current = normalize_bind(cfg.hotkey_kind, cfg.hotkey_keycode)
    spec = " ".join(spec_parts).strip()
    if not spec:
        _cli_out(f"{current.kind} {current.code} ({format_bind(current)})")
        return 0
    if spec.lower() in {"capture", "grab", "listen"}:
        if not daemon_alive():
            _cli_out("Ёхо не запущена — сначала start/toggle, потом bind capture", error=True)
            return 1
        try:
            send_command("rebind")
        except OSError as exc:
            _cli_out(f"нет связи с Ёхо: {exc}", error=True)
            return 1
        _cli_out("нажмите кнопку — смотрите кота")
        return 0
    bind = parse_bind_spec(spec)
    if bind is None:
        _cli_out(f"не понял кнопку {spec!r} (пример: F8, 0x77, ё, mouse:8)", error=True)
        return 2
    other = optional_bind(cfg.translate_hotkey_kind, cfg.translate_hotkey_keycode)
    if binds_conflict(bind, other):
        _cli_out("кнопка уже занята переводом", error=True)
        return 2
    cfg.hotkey_kind = bind.kind
    cfg.hotkey_keycode = bind.code
    save_config(cfg)
    _cli_out(f"кнопка: {bind.kind} {bind.code} ({format_bind(bind)})")
    if daemon_alive():
        try:
            send_command("reload")
        except OSError as exc:
            _cli_out(f"конфиг записан, но демон не перечитал: {exc}", error=True)
            return 1
    return 0


def _venv_python(root: Path) -> Path:
    if sys.platform == "win32":
        cand = root / ".venv" / "Scripts" / "python.exe"
        if cand.exists():
            return cand
    else:
        cand = root / ".venv" / "bin" / "python"
        if cand.exists():
            return cand
    return Path(sys.executable)


def _spawn_daemon() -> bool:
    frozen = bool(getattr(sys, "frozen", False))
    from yo.paths import project_root, xdg_cache

    log = xdg_cache() / "daemon.log"
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("HF_HUB_DISABLE_XET", "1")
    env.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    env.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    env.setdefault("TQDM_DISABLE", "1")
    env.setdefault("HF_HOME", str(xdg_cache() / "hf"))
    if sys.platform != "win32":
        env.setdefault("DISPLAY", ":0")
    if frozen:
        exe = Path(sys.executable).resolve()
        argv = [str(exe), "daemon"]
        cwd = str(exe.parent)
        # Do not set YO_ROOT to this process's _MEIPASS (onefile extract dies with the parent).
    else:
        root = project_root()
        py = _venv_python(root)
        argv = [str(py), "-m", "yo", "daemon"]
        cwd = str(root)
        env["YO_ROOT"] = str(root)
    popen_kw = dict(cwd=cwd, env=env)
    if sys.platform == "win32":
        popen_kw["creationflags"] = subprocess.CREATE_NO_WINDOW | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    else:
        popen_kw["start_new_session"] = True
    with log.open("a", encoding="utf-8") as fh:
        popen_kw["stdout"] = fh
        popen_kw["stderr"] = fh
        subprocess.Popen(argv, **popen_kw)
    for _ in range(40):
        time.sleep(0.15)
        from yo.ipc import daemon_alive

        if daemon_alive():
            return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
