"""Поиск реального микрофона / гарнитуры на Linux (PipeWire, затем PortAudio)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from typing import Any

NO_MIC_HINT = "подключите микрофон"
MIC_PERMISSION_HINT = "разрешите микрофон в параметрах Windows"
MIC_OPEN_HINT = "не удалось открыть микрофон"
MIC_SILENT_HINT = "микрофон молчит"

_PORT_AVAIL_RE = re.compile(
    r"availability(?: group: [^,]+,)? (not available|unknown|available)\s*\)?\s*$"
)
_HW_SUFFIX = re.compile(r"\s*\(hw:\d+,\d+\)\s*$", re.IGNORECASE)
_PA_SKIP = (
    "monitor",
    "loopback",
    "dummy",
    "null",
    "hdmi",
    "pipewire",
    "default",
)
# Windows Sound Mapper / stereo mix / analog line-in are not a headset mic.
_WIN_SKIP = _PA_SKIP + (
    "mapper",
    "переназначение",
    "первичный драйвер",
    "primary sound capture",
    "stereo mix",
    "стерео микшер",
    "line in",
    "line-in",
    "linein",
    "lin. input",
    "лин. вход",
    "what u hear",
    "wave out mix",
)
_MIC_NAME_HINTS = ("mic", "микрофон", "headset", "гарнитур")


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
    skip = _WIN_SKIP if sys.platform == "win32" else _PA_SKIP
    if any(token in name for token in skip):
        return False
    return True


def _hostapi_name(info: dict[str, Any]) -> str:
    explicit = info.get("hostapi_name")
    if explicit:
        return str(explicit).lower()
    idx = info.get("hostapi")
    if idx is None:
        return ""
    try:
        import sounddevice as sd

        host = sd.query_hostapis(int(idx))
        return str((host or {}).get("name") or "").lower()
    except Exception:
        return ""


def _windows_device_rank(info: dict[str, Any]) -> tuple[int, int]:
    host = _hostapi_name(info)
    if "wasapi" in host:
        host_rank = 0
    elif host in {"mme", "windows mme"} or host.endswith(" mme"):
        host_rank = 1
    elif "directsound" in host or host in {"windows ds", "ds"}:
        host_rank = 2
    elif "wdm-ks" in host:
        host_rank = 3
    else:
        host_rank = 5
    name = str(info.get("name") or "").lower()
    mic_rank = 0 if any(token in name for token in _MIC_NAME_HINTS) else 1
    return (host_rank, mic_rank)


def microphone_permission_denied() -> bool:
    """True when Windows Privacy has blocked microphone for desktop apps."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
    except ImportError:
        return False
    keys = (
        r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone",
        r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone\NonPackaged",
    )
    for path in keys:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                value, _typ = winreg.QueryValueEx(key, "Value")
        except OSError:
            continue
        if str(value).strip().lower() == "deny":
            return True
    return False


def mic_open_hint(exc: BaseException | None = None) -> str:
    if microphone_permission_denied():
        return MIC_PERMISSION_HINT
    text = str(exc or "").lower()
    if any(token in text for token in ("permission", "access denied", "denied", "not permitted")):
        return MIC_PERMISSION_HINT
    if any(token in text for token in ("не найден", "no device", "invalid device", "device unavailable")):
        return NO_MIC_HINT
    if any(token in text for token in ("молчит", "silent", "dead stream")):
        return MIC_SILENT_HINT
    if exc is not None:
        return MIC_OPEN_HINT
    return NO_MIC_HINT


def _read_pactl_sources() -> str | None:
    if sys.platform == "win32":
        return None
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


def dead_stream_plan(mic_present: bool) -> dict[str, object]:
    """Silence is not an unplug. Inventory decides whether the mic is gone."""
    if not mic_present:
        return {"mic_missing": True, "live": False, "stop_capture": True}
    return {"mic_missing": False, "live": None, "stop_capture": False}


def presence_poll_plan(mic_present: bool, *, was_missing: bool) -> dict[str, object]:
    if not mic_present:
        return {
            "mic_missing": True,
            "live": False,
            "start_capture": False,
            "stop_capture": True,
        }
    return {
        "mic_missing": False,
        "live": None,
        "start_capture": bool(was_missing),
        "stop_capture": False,
    }


def stable_device_name(name: str) -> str:
    return _HW_SUFFIX.sub("", (name or "").strip())


def names_match(saved: str, current: str) -> bool:
    left = (saved or "").strip().lower()
    right = (current or "").strip().lower()
    if not left or not right:
        return False
    if left == right:
        return True
    return stable_device_name(left).lower() == stable_device_name(right).lower()


def portaudio_name_at(index: int, *, devices: list | None = None) -> str:
    pa_devices = devices if devices is not None else _query_portaudio_devices()
    for i, device in enumerate(pa_devices):
        if _pa_index(device, i) == index:
            info = device if isinstance(device, dict) else {}
            return str(info.get("name") or "").strip()
    return ""


def capture_microphone_update(saved: str, resolved_name: str) -> str | None:
    name = (resolved_name or "").strip()
    if not name:
        return None
    if (saved or "").strip() == name:
        return None
    return name


def _pulse_allows_pa_device(ident: str, sources: list[dict[str, Any]]) -> bool:
    needle = (ident or "").lower()
    matched = False
    for source in sources:
        token = _hw_token(source)
        if not token or token.lower() not in needle:
            continue
        matched = True
        if _usable_pulse_source(source):
            return True
    return not matched


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
        pulse_all = parse_pactl_sources(pactl_text)
    else:
        text = _read_pactl_sources()
        pulse_all = parse_pactl_sources(text) if text else []
    pulse = [src for src in pulse_all if _usable_pulse_source(src)]
    pa_devices = devices if devices is not None else _query_portaudio_devices()
    listed: list[dict[str, str]] = []
    seen: dict[str, tuple[int, int]] = {}
    for device in pa_devices:
        if not _usable_pa_device(device):
            continue
        info = device if isinstance(device, dict) else {}
        ident = str(info.get("name") or "").strip()
        if not ident:
            continue
        if pulse_all and not _pulse_allows_pa_device(ident, pulse_all):
            continue
        rank = _windows_device_rank(info) if sys.platform == "win32" else (0, 0)
        if ident in seen and seen[ident] <= rank:
            continue
        label = ident
        for src in pulse:
            token = _hw_token(src)
            if token and token.lower() in ident.lower():
                label = str(src.get("description") or ident)
                break
        if ident in seen:
            for item in listed:
                if item["id"] == ident:
                    item["label"] = label
                    break
        else:
            listed.append({"id": ident, "label": label})
        seen[ident] = rank
    return listed


def _best_index_for_name(pa_devices: list, preferred: str) -> int | None:
    lowered = preferred.lower()
    exact: tuple[tuple[int, int], int] | None = None
    stable: tuple[tuple[int, int], int] | None = None
    partial: tuple[tuple[int, int], int] | None = None
    for i, device in enumerate(pa_devices):
        if not _usable_pa_device(device):
            continue
        info = device if isinstance(device, dict) else {}
        ident = str(info.get("name") or "").strip()
        ident_l = ident.lower()
        rank = _windows_device_rank(info) if sys.platform == "win32" else (0, i)
        index = _pa_index(device, i)
        if ident_l == lowered:
            if exact is None or rank < exact[0]:
                exact = (rank, index)
            continue
        if names_match(preferred, ident):
            if stable is None or rank < stable[0]:
                stable = (rank, index)
        if lowered in ident_l:
            if partial is None or rank < partial[0]:
                partial = (rank, index)
    if exact is not None:
        return exact[1]
    if stable is not None:
        return stable[1]
    if partial is not None:
        return partial[1]
    return None


def resolve_portaudio_device(
    name: str = "",
    *,
    pactl_text: str | None = None,
    devices: list | None = None,
) -> int | None:
    pa_devices = devices if devices is not None else _query_portaudio_devices()
    preferred = (name or "").strip()
    if preferred:
        found = _best_index_for_name(pa_devices, preferred)
        if found is not None:
            return found
    return preferred_portaudio_device(pactl_text=pactl_text, devices=devices)


def capture_candidate_indices(name: str = "", *, devices: list | None = None) -> list[int]:
    """WASAPI first, then MME/DirectSound/WDM-KS copies of the selected mic.

    The settings combo stores a device name. Every PortAudio alias of that
    name is tried so a headset like Barracuda X (and any other listed mic)
    actually opens, not just the first host API.
    """
    pa_devices = devices if devices is not None else _query_portaudio_devices()
    wanted = (name or "").strip()
    first = resolve_portaudio_device(wanted, devices=pa_devices)
    out: list[int] = []
    seen: set[int] = set()

    def add(idx: int | None) -> None:
        if idx is None or idx in seen:
            return
        seen.add(idx)
        out.append(idx)

    add(first)
    ranked: list[tuple[tuple[int, int], int]] = []
    for i, device in enumerate(pa_devices):
        if not _usable_pa_device(device):
            continue
        info = device if isinstance(device, dict) else {}
        ident = str(info.get("name") or "").strip()
        idx = _pa_index(device, i)
        if wanted and not names_match(wanted, ident) and wanted.lower() not in ident.lower():
            continue
        rank = _windows_device_rank(info) if sys.platform == "win32" else (0, i)
        ranked.append((rank, idx))
    ranked.sort()
    for _rank, idx in ranked:
        add(idx)
    return out


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
    best: tuple[tuple[int, int], int] | None = None
    for i, device in enumerate(pa_devices):
        if not _usable_pa_device(device):
            continue
        info = device if isinstance(device, dict) else {}
        rank = _windows_device_rank(info) if sys.platform == "win32" else (0, i)
        index = _pa_index(device, i)
        if best is None or rank < best[0]:
            best = (rank, index)
    if best is not None:
        return best[1]
    return None
