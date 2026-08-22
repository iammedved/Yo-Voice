"""Пути проекта и пользовательских данных Ёхо."""

from __future__ import annotations

import os
from pathlib import Path

APP_ID = "yo-voice"
DISPLAY_NAME = "Ёхо"


def project_root() -> Path:
    env = os.environ.get("YO_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent


def assets_dir() -> Path:
    return project_root() / "assets"


def orb_path() -> Path:
    for name in ("logo.png", "mascot.png", "orb.png", "orb.jpg"):
        path = assets_dir() / name
        if path.exists():
            return path
    return assets_dir() / "logo.png"


def xdg_config() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = base / APP_ID
    path.mkdir(parents=True, exist_ok=True)
    return path


def xdg_cache() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    path = base / APP_ID
    path.mkdir(parents=True, exist_ok=True)
    return path


def socket_path() -> Path:
    return xdg_cache() / "yo.sock"


def pid_path() -> Path:
    return xdg_cache() / "yo.pid"


def config_path() -> Path:
    return xdg_config() / "config.json"
