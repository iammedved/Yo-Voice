"""Подключает pip-колёса CUDA/cuDNN к динамическому линкеру."""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

NVIDIA_PKGS = (
    "nvidia.cublas.lib",
    "nvidia.cudnn.lib",
    "nvidia.cuda_nvrtc.lib",
    "nvidia.cuda_runtime.lib",
    "nvidia.cublas",
    "nvidia.cudnn",
    "nvidia.cuda_nvrtc",
    "nvidia.cuda_runtime",
)

FROZEN_RELS = (
    "nvidia/cublas/bin",
    "nvidia/cudnn/bin",
    "nvidia/cuda_runtime/bin",
    "nvidia/cuda_nvrtc/bin",
    "ctranslate2",
)

# Windows pip wheels: nvidia/<pkg>/bin/<dll>. ctranslate2 грузит cublas по имени
# в encode — процесс должен уже видеть эти каталоги в PATH / add_dll_directory.
NVIDIA_CUDA_DLLS = (
    ("cuda_runtime", "cudart64_12.dll"),
    ("cublas", "cublasLt64_12.dll"),
    ("cublas", "cublas64_12.dll"),
    ("cudnn", "cudnn64_9.dll"),
    ("cuda_nvrtc", "nvrtc64_120_0.dll"),
    ("cuda_nvrtc", "nvrtc-builtins64_129.dll"),
)

WANTED_DLLS = tuple(name for _pkg, name in NVIDIA_CUDA_DLLS)


def _unique(paths: list[str]) -> list[str]:
    return list(dict.fromkeys(p for p in paths if p))


def _with_bin_lib(directories: list[str]) -> list[str]:
    """NVIDIA Windows wheels кладут DLL в <pkg>/bin, не в корень пакета."""
    extra: list[str] = []
    for directory in directories:
        extra.append(directory)
        for child in ("bin", "lib"):
            nested = os.path.join(directory, child)
            extra.append(nested)
    return extra


def cuda_search_dirs() -> list[str]:
    extra: list[str] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            extra.append(meipass)
            for rel in FROZEN_RELS:
                extra.append(os.path.join(meipass, *rel.split("/")))
    for pkg in NVIDIA_PKGS:
        try:
            mod = __import__(pkg, fromlist=["*"])
        except Exception:
            continue
        extra.extend(str(p) for p in getattr(mod, "__path__", []) or [])
        file = getattr(mod, "__file__", None)
        if file:
            extra.append(os.path.dirname(file))
    return _unique(_with_bin_lib(extra))


def nvidia_cuda_binaries() -> list[tuple[str, str]]:
    """Пары (src, dest_dir) для PyInstaller, если колёса NVIDIA стоят в venv."""
    roots: list[Path] = []
    try:
        import nvidia

        roots.extend(Path(p) for p in (getattr(nvidia, "__path__", None) or []))
    except Exception:
        pass
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for root in roots:
        for pkg, name in NVIDIA_CUDA_DLLS:
            src = root / pkg / "bin" / name
            if not src.is_file():
                continue
            key = str(src.resolve())
            if key in seen:
                continue
            seen.add(key)
            out.append((str(src), f"nvidia/{pkg}/bin"))
    return out


def setup_cuda_libs() -> None:
    extra = cuda_search_dirs()
    if not extra:
        return
    if sys.platform == "win32":
        current = os.environ.get("PATH", "")
        existing = [p for p in extra if os.path.isdir(p)]
        if existing:
            os.environ["PATH"] = os.pathsep.join(existing + ([current] if current else []))
            if hasattr(os, "add_dll_directory"):
                for directory in existing:
                    try:
                        os.add_dll_directory(directory)
                    except (OSError, FileNotFoundError):
                        pass
        loaded: set[str] = set()
        for directory in existing:
            try:
                names = set(os.listdir(directory))
            except OSError:
                continue
            for name in WANTED_DLLS:
                if name not in names or name in loaded:
                    continue
                try:
                    ctypes.WinDLL(os.path.join(directory, name))
                    loaded.add(name)
                except OSError:
                    pass
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
