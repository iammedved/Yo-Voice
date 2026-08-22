"""Подключает pip-колёса CUDA/cuDNN к динамическому линкеру."""

from __future__ import annotations

import ctypes
import os


def setup_cuda_libs() -> None:
    extra: list[str] = []
    for pkg in (
        "nvidia.cublas.lib",
        "nvidia.cudnn.lib",
        "nvidia.cuda_nvrtc.lib",
        "nvidia.cuda_runtime.lib",
    ):
        try:
            mod = __import__(pkg, fromlist=["*"])
        except Exception:
            continue
        extra.extend(str(p) for p in getattr(mod, "__path__", []) or [])
        file = getattr(mod, "__file__", None)
        if file:
            extra.append(os.path.dirname(file))
    extra = list(dict.fromkeys(p for p in extra if p))
    if not extra:
        return
    current = os.environ.get("LD_LIBRARY_PATH", "")
    os.environ["LD_LIBRARY_PATH"] = os.pathsep.join(extra + ([current] if current else []))
    wanted = (
        "libcublas.so.12",
        "libcublasLt.so.12",
        "libcudnn.so.9",
        "libnvrtc.so.12",
    )
    for directory in extra:
        try:
            names = set(os.listdir(directory))
        except OSError:
            continue
        for name in wanted:
            if name not in names:
                continue
            try:
                ctypes.CDLL(os.path.join(directory, name), mode=ctypes.RTLD_GLOBAL)
            except OSError:
                pass
