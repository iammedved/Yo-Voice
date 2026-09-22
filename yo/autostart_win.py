"""User-level autostart via HKCU Run (no admin)."""

from __future__ import annotations

import sys
import winreg
from pathlib import Path

from yo.paths import project_root

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Yo-Voice"


def _pythonw(root: Path | None = None) -> Path:
    root = root or project_root()
    pyw = root / ".venv" / "Scripts" / "pythonw.exe"
    if pyw.exists():
        return pyw
    return Path(sys.executable)


def command(root: Path | None = None) -> str:
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        return f'"{exe}" daemon'
    root = root or project_root()
    py = _pythonw(root)
    return f'"{py}" -m yo daemon'


def enable(root: Path | None = None) -> str:
    cmd = command(root)
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY)
    try:
        try:
            winreg.DeleteValue(key, "yo-voice")
        except FileNotFoundError:
            pass
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, cmd)
    finally:
        winreg.CloseKey(key)
    return cmd


def disable() -> None:
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
    except FileNotFoundError:
        return
    try:
        winreg.DeleteValue(key, VALUE_NAME)
    except FileNotFoundError:
        pass
    finally:
        winreg.CloseKey(key)


def enabled() -> bool:
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ)
    except FileNotFoundError:
        return False
    try:
        winreg.QueryValueEx(key, VALUE_NAME)
        return True
    except FileNotFoundError:
        return False
    finally:
        winreg.CloseKey(key)
