"""Пути проекта и пользовательских данных Ёхо."""

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
    # PyInstaller: _MEIPASS is the extract dir (onefile) or _internal (onedir).
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


def xdg_config() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = base / APP_ID
    path.mkdir(parents=True, exist_ok=True)
    return path


def xdg_cache() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    path = base / APP_ID
    path.mkdir(parents=True, exist_ok=True)
    return path


def socket_path() -> Path:
    if sys.platform == "win32":
        return xdg_cache() / "yo.port"
    return xdg_cache() / "yo.sock"


def pid_path() -> Path:
    return xdg_cache() / "yo.pid"


def config_path() -> Path:
    return xdg_config() / "config.json"


def replacements_path() -> Path:
    return xdg_config() / "replacements.json"
