"""Куда считать речь: NVIDIA CUDA или процессор.

Radeon и другая встроенная графика не используются. CTranslate2 считает
либо на NVIDIA CUDA, либо на процессоре. У Radeon 780M около 3 ГБ общей
памяти — в неё модель Whisper не помещается, даже если бы был свой backend.
"""

from __future__ import annotations

import os
import sys

_DISPLAY_CLASS = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"


def choose_device(pref: str, cuda_devices: int) -> str:
    """auto/cuda → cuda only when a NVIDIA device is actually visible."""
    if (pref or "").strip().lower() == "cpu":
        return "cpu"
    if int(cuda_devices) > 0:
        return "cuda"
    return "cpu"


def cuda_device_count() -> int:
    try:
        import ctranslate2

        return int(ctranslate2.get_cuda_device_count())
    except Exception:
        return 0


def cpu_thread_count(logical: int | None = None) -> int:
    """Intra-op threads for CTranslate2 on CPU.

    A 16-thread Ryzen 7 (8 cores) gets 8. More threads do not make Whisper
    faster and steal time from the microphone callback.
    """
    if logical is None or logical <= 0:
        logical = os.cpu_count() or 4
    if logical >= 12:
        return min(8, logical // 2)
    if logical >= 4:
        return max(2, logical - 2)
    return max(1, logical - 1) if logical > 1 else 1


def cpu_model_kwargs(logical: int | None = None) -> dict[str, int]:
    """faster-whisper WhisperModel kwargs. One worker: 16 GB cannot hold two copies."""
    return {"cpu_threads": cpu_thread_count(logical), "num_workers": 1}


def has_nvidia_name(names: list[str]) -> bool:
    for name in names:
        upper = (name or "").upper()
        if "NVIDIA" in upper or "GEFORCE" in upper:
            return True
    return False


def windows_adapter_names() -> list[str]:
    if sys.platform != "win32":
        return []
    import winreg

    names: list[str] = []
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _DISPLAY_CLASS)
    except OSError:
        return []
    try:
        index = 0
        while True:
            try:
                sub = winreg.EnumKey(root, index)
            except OSError:
                break
            index += 1
            if not sub.isdigit():
                continue
            try:
                with winreg.OpenKey(root, sub) as child:
                    desc, _kind = winreg.QueryValueEx(child, "DriverDesc")
            except OSError:
                continue
            text = str(desc).strip()
            if not text:
                continue
            upper = text.upper()
            if "MICROSOFT" in upper and "BASIC" in upper:
                continue
            names.append(text)
    finally:
        root.Close()
    return names
