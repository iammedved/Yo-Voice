"""Пути проекта и пользовательских данных Ёхо (Windows)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_ID = "yo-voice"
DISPLAY_NAME = "Ёхо"


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    env = os.environ.get("YO_ROOT")
    if env:
        return Path(env)
    if frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def assets_dir() -> Path:
    cand = project_root() / "assets"
    if cand.is_dir():
        return cand
    if frozen():
        beside = Path(sys.executable).resolve().parent / "assets"
        if beside.is_dir():
            return beside
    return cand


def orb_path() -> Path:
    for name in ("logo.png", "mascot.png", "orb.png", "orb.jpg"):
        path = assets_dir() / name
        if path.exists():
            return path
    return assets_dir() / "logo.png"


def _appdata() -> Path:
    env = os.environ.get("APPDATA")
    if env:
        return Path(env)
    return Path.home() / "AppData" / "Roaming"


def _localappdata() -> Path:
    env = os.environ.get("LOCALAPPDATA")
    if env:
        return Path(env)
    return Path.home() / "AppData" / "Local"


def xdg_config() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else _appdata()
    path = base / APP_ID
    path.mkdir(parents=True, exist_ok=True)
    return path


def xdg_cache() -> Path:
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else _localappdata()
    path = base / APP_ID
    path.mkdir(parents=True, exist_ok=True)
    return path


def socket_path() -> Path:
    return xdg_cache() / "yo.port"


def pid_path() -> Path:
    return xdg_cache() / "yo.pid"


def config_path() -> Path:
    return xdg_config() / "config.json"


def replacements_path() -> Path:
    return xdg_config() / "replacements.json"
