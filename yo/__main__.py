"""Точка входа: yo-voice toggle|daemon|demo|start|stop|status|settings."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from yo.cuda_env import setup_cuda_libs
from yo.ipc import daemon_alive, send_command
from yo.paths import project_root, xdg_cache


def main(argv: list[str] | None = None) -> int:
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    setup_cuda_libs()
    parser = argparse.ArgumentParser(
        prog="yo-voice",
        description="Ёхо — голосовой ввод в активное текстовое поле",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="toggle",
        choices=("toggle", "start", "stop", "daemon", "demo", "status", "quit", "settings"),
    )
    parser.add_argument("--seconds", type=float, default=8.0, help="длительность демо overlay")
    args = parser.parse_args(argv)

    if args.command == "daemon":
        from yo.app import run_daemon
        from yo.logutil import setup_logging

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

    if not daemon_alive():
        if args.command in {"status", "quit"}:
            print("Ёхо не запущена")
            return 1 if args.command == "status" else 0
        if not _spawn_daemon():
            print("не удалось запустить Ёхо в фоне", file=sys.stderr)
            return 1

    try:
        reply = send_command(args.command)
    except OSError as exc:
        print(f"нет связи с Ёхо: {exc}", file=sys.stderr)
        return 1
    print(reply)
    return 0


def _spawn_daemon() -> bool:
    root = project_root()
    py = root / ".venv" / "bin" / "python"
    if not py.exists():
        py = Path(sys.executable)
    log = xdg_cache() / "daemon.log"
    env = os.environ.copy()
    env["YO_ROOT"] = str(root)
    env.setdefault("DISPLAY", ":0")
    env.setdefault("PYTHONUNBUFFERED", "1")
    with log.open("a", encoding="utf-8") as fh:
        subprocess.Popen(
            [str(py), "-m", "yo", "daemon"],
            cwd=str(root),
            env=env,
            stdout=fh,
            stderr=fh,
            start_new_session=True,
        )
    for _ in range(40):
        time.sleep(0.15)
        if daemon_alive():
            return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
