"""Поиск реального микрофона / гарнитуры на Linux (PipeWire, затем PortAudio)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import Any

NO_MIC_HINT = "подключите микрофон"

_PORT_AVAIL_RE = re.compile(
    r"availability(?: group: [^,]+,)? (not available|unknown|available)\s*\)?\s*$"
)
_PA_SKIP = (
    "monitor",
    "loopback",
    "dummy",
    "null",
    "hdmi",
    "pipewire",
    "default",
)


def parse_pactl_sources(text: str) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    in_ports = False
    for raw in (text or "").splitlines():
        line = raw.strip()
        if line.startswith("Source #"):
            if current is not None:
                sources.append(current)
            current = {
                "name": "",
                "description": "",
                "device_class": "",
                "monitor_of": "",
                "ports": [],
            }
            in_ports = False
            continue
        if current is None:
            continue
        if line.startswith("Name:"):
            current["name"] = line.split(":", 1)[1].strip()
            in_ports = False
        elif line.startswith("Description:"):
            current["description"] = line.split(":", 1)[1].strip()
        elif line.startswith("Monitor of Sink:"):
            current["monitor_of"] = line.split(":", 1)[1].strip()
        elif line.startswith("device.class"):
            current["device_class"] = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("alsa.card ="):
            current["alsa_card"] = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("alsa.device ="):
            current["alsa_device"] = line.split("=", 1)[1].strip().strip('"')
        elif line == "Ports:":
            in_ports = True
        elif in_ports and (line.startswith("Active Port:") or line.startswith("Formats:")):
            in_ports = False
        elif in_ports and line and ":" in line:
            name = line.split(":", 1)[0].strip()
            match = _PORT_AVAIL_RE.search(line)
            availability = match.group(1) if match else "unknown"
            current["ports"].append((name, availability))
    if current is not None:
        sources.append(current)
    return sources


def _usable_pulse_source(source: dict[str, Any]) -> bool:
    name = str(source.get("name") or "")
    description = str(source.get("description") or "")
    device_class = str(source.get("device_class") or "")
    monitor_of = str(source.get("monitor_of") or "").strip()
    if device_class == "monitor":
        return False
    if name.endswith(".monitor"):
        return False
    if description.lower().startswith("monitor of"):
        return False
    if monitor_of and monitor_of.lower() not in {"n/a", "н/д"}:
        return False
    ports = list(source.get("ports") or [])
    if not ports:
        return device_class == "sound"
    if any(availability == "available" for _name, availability in ports):
        return True
    if all(availability == "not available" for _name, availability in ports):
        return False
    return True


def _usable_pa_device(device: Any) -> bool:
    info = device if isinstance(device, dict) else {}
    try:
        channels = int(info.get("max_input_channels") or 0)
    except (TypeError, ValueError):
        channels = 0
    if channels <= 0:
        return False
    name = str(info.get("name") or "").lower()
    return not any(token in name for token in _PA_SKIP)


def _read_pactl_sources() -> str | None:
    pactl = shutil.which("pactl")
    if not pactl:
        return None
    env = os.environ.copy()
    env["LANG"] = "C"
    env["LC_ALL"] = "C"
    try:
        result = subprocess.run(
            [pactl, "list", "sources"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2.0,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout or ""


def has_microphone(*, pactl_text: str | None = None, devices: list | None = None) -> bool:
    if pactl_text is not None:
        return any(_usable_pulse_source(src) for src in parse_pactl_sources(pactl_text))
    if devices is not None:
        return any(_usable_pa_device(dev) for dev in devices)
    text = _read_pactl_sources()
    if text is not None:
        return any(_usable_pulse_source(src) for src in parse_pactl_sources(text))
    try:
        import sounddevice as sd

        return any(_usable_pa_device(dev) for dev in sd.query_devices())
    except Exception:
        return False


def listen_capture_plan(mic_present: bool) -> dict[str, object]:
    if mic_present:
        return {"start_capture": True, "mic_missing": False, "hint": None}
    return {"start_capture": False, "mic_missing": True, "hint": NO_MIC_HINT}


def _hw_token(source: dict[str, Any]) -> str | None:
    card = str(source.get("alsa_card") or "").strip()
    device = str(source.get("alsa_device") or "").strip()
    if not card or not device:
        return None
    return f"hw:{card},{device}"


def _pa_index(device: Any, fallback: int) -> int:
    info = device if isinstance(device, dict) else {}
    try:
        return int(info.get("index", fallback))
    except (TypeError, ValueError):
        return fallback


def _query_portaudio_devices() -> list:
    try:
        import sounddevice as sd

        return list(sd.query_devices())
    except Exception:
        return []


def list_capture_devices(*, pactl_text: str | None = None, devices: list | None = None) -> list[dict[str, str]]:
    if pactl_text is not None:
        pulse = [src for src in parse_pactl_sources(pactl_text) if _usable_pulse_source(src)]
    else:
        text = _read_pactl_sources()
        pulse = [src for src in parse_pactl_sources(text) if _usable_pulse_source(src)] if text else []
    pa_devices = devices if devices is not None else _query_portaudio_devices()
    listed: list[dict[str, str]] = []
    seen: set[str] = set()
    for device in pa_devices:
        if not _usable_pa_device(device):
            continue
        info = device if isinstance(device, dict) else {}
        ident = str(info.get("name") or "").strip()
        if not ident or ident in seen:
            continue
        label = ident
        for src in pulse:
            token = _hw_token(src)
            if token and token.lower() in ident.lower():
                label = str(src.get("description") or ident)
                break
        seen.add(ident)
        listed.append({"id": ident, "label": label})
    return listed


def resolve_portaudio_device(
    name: str = "",
    *,
    pactl_text: str | None = None,
    devices: list | None = None,
) -> int | None:
    pa_devices = devices if devices is not None else _query_portaudio_devices()
    preferred = (name or "").strip().lower()
    if preferred:
        exact: int | None = None
        partial: int | None = None
        for i, device in enumerate(pa_devices):
            if not _usable_pa_device(device):
                continue
            info = device if isinstance(device, dict) else {}
            ident = str(info.get("name") or "").strip()
            lowered = ident.lower()
            if lowered == preferred:
                exact = _pa_index(device, i)
                break
            if preferred in lowered and partial is None:
                partial = _pa_index(device, i)
        if exact is not None:
            return exact
        if partial is not None:
            return partial
    return preferred_portaudio_device(pactl_text=pactl_text, devices=devices)


def preferred_portaudio_device(*, pactl_text: str | None = None, devices: list | None = None) -> int | None:
    if pactl_text is not None:
        usable = [src for src in parse_pactl_sources(pactl_text) if _usable_pulse_source(src)]
    elif devices is None:
        text = _read_pactl_sources()
        usable = [src for src in parse_pactl_sources(text) if _usable_pulse_source(src)] if text is not None else []
    else:
        usable = []
    pa_devices = devices if devices is not None else _query_portaudio_devices()
    for src in usable:
        token = _hw_token(src)
        if not token:
            continue
        needle = token.lower()
        for i, device in enumerate(pa_devices):
            info = device if isinstance(device, dict) else {}
            name = str(info.get("name") or "").lower()
            if needle in name and _usable_pa_device(device):
                return _pa_index(device, i)
    for i, device in enumerate(pa_devices):
        if _usable_pa_device(device):
            return _pa_index(device, i)
    return None
