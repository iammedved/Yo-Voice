"""Конфиг Ёхо."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from yo.asr import DEFAULT_MODEL
from yo.bind import normalize_bind
from yo.paths import config_path

log = logging.getLogger("yo.config")


@dataclass
class Config:
    model: str = DEFAULT_MODEL
    language: str = "ru"
    device: str = "auto"  # auto | cuda | cpu
    hotkey_kind: str = "key"  # key | button
    hotkey_keycode: int = 49  # X11 keycode or mouse button
    translate_hotkey_kind: str = ""  # key | button | empty = unset
    translate_hotkey_keycode: int = 0
    sample_rate: int = 16000
    inject_leading_space: bool = True
    overlay_x: int | None = None
    overlay_y: int | None = None
    microphone: str = ""  # PortAudio name; empty = auto
    tray_intro_shown: bool = False


def load_config(path: Path | None = None) -> Config:
    file = path or config_path()
    if not file.exists():
        cfg = Config()
        save_config(cfg, file)
        return cfg
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("config is not an object")
    except Exception:
        log.warning("битый конфиг %s, беру значения по умолчанию", file)
        cfg = Config()
        save_config(cfg, file)
        return cfg
    base = asdict(Config())
    base.update({k: v for k, v in data.items() if k in base})
    cfg = Config(**base)
    bind = normalize_bind(cfg.hotkey_kind, cfg.hotkey_keycode)
    cfg.hotkey_kind = bind.kind
    cfg.hotkey_keycode = bind.code
    return cfg


def save_config(cfg: Config, path: Path | None = None) -> None:
    file = path or config_path()
    file.write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def patch_config(path: Path | None = None, **fields) -> Config:
    """Merge selected fields onto the on-disk config so a stale in-memory
    object cannot overwrite a concurrent CLI bind or other keys."""
    allowed = asdict(Config())
    cfg = load_config(path)
    for key, value in fields.items():
        if key not in allowed:
            raise TypeError(f"unknown config field {key}")
        setattr(cfg, key, value)
    save_config(cfg, path)
    return cfg
