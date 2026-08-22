"""Конфиг Ёхо."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from yo.paths import config_path

log = logging.getLogger("yo.config")


@dataclass
class Config:
    model: str = "large-v3-turbo"
    language: str = "ru"
    device: str = "auto"  # auto | cuda | cpu
    hotkey_keycode: int = 49  # grave / ё
    sample_rate: int = 16000
    inject_leading_space: bool = True
    overlay_x: int | None = None
    overlay_y: int | None = None
    microphone: str = ""  # PortAudio name; empty = auto


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
    return Config(**base)


def save_config(cfg: Config, path: Path | None = None) -> None:
    file = path or config_path()
    file.write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
