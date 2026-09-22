# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir spec for Yo-Voice (Windows). Whisper/NLLB weights stay out."""

import importlib.util
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)

SPECDIR = Path(SPECPATH).resolve()
ROOT = SPECDIR.parent
ICON = ROOT / "assets" / "yo-voice.ico"

def _nvidia_cuda_binaries():
    path = ROOT / "yo" / "cuda_env.py"
    spec = importlib.util.spec_from_file_location("yo_cuda_env_spec", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return list(mod.nvidia_cuda_binaries())


datas = [
    (str(ROOT / "assets"), "assets"),
    (str(ROOT / "yo" / "data" / "silero_vad.onnx"), "yo/data"),
]
datas += collect_data_files("faster_whisper")
datas += collect_data_files("_sounddevice_data")
datas += collect_data_files("certifi")
for _meta in (
    "faster_whisper",
    "huggingface_hub",
    "transformers",
    "ctranslate2",
    "onnxruntime",
    "tokenizers",
    "sounddevice",
    "onnxruntime-gpu",
):
    try:
        datas += copy_metadata(_meta)
    except Exception:
        pass

binaries = []
binaries += collect_dynamic_libs("ctranslate2")
binaries += collect_dynamic_libs("onnxruntime")
binaries += collect_dynamic_libs("av")
binaries += _nvidia_cuda_binaries()


hiddenimports = [
    "yo",
    "yo.app",
    "yo.overlay_win",
    "yo.hotkey_win",
    "yo.inject_win",
    "yo.ipc_win",
    "yo.settings_win",
    "yo.tray_win",
    "yo.loop_win",
    "yo.clip_win",
    "yo.autostart_win",
    "yo.winapi",
    "yo.asr",
    "yo.fetchprog",
    "yo.prefetch_ui",
    "yo.report",
    "yo.report_ui",
    "yo.mt",
    "yo.vad",
    "yo.audio",
    "yo.bind",
    "yo.capture",
    "yo.config",
    "yo.cuda_env",
    "yo.logutil",
    "yo.overlay",
    "yo.hotkey",
    "yo.inject",
    "yo.ipc",
    "yo.loop",
    "yo.paths",
    "yo.phrases",
    "yo.polish",
    "yo.session",
    "yo.settings",
    "yo.spectrum",
    "yo.terms",
    "faster_whisper",
    "ctranslate2",
    "onnxruntime",
    "onnxruntime.capi",
    "onnxruntime.capi.onnxruntime_pybind11_state",
    "sounddevice",
    "_sounddevice_data",
    "numpy",
    "PIL",
    "PIL.Image",
    "PIL.ImageTk",
    "transformers",
    "transformers.models.auto",
    "transformers.models.auto.tokenization_auto",
    "transformers.models.nllb",
    "transformers.models.nllb.tokenization_nllb",
    "transformers.models.nllb.tokenization_nllb_fast",
    "sentencepiece",
    "huggingface_hub",
    "tokenizers",
    "certifi",
    "cffi",
    "charset_normalizer",
    "filelock",
    "packaging",
    "requests",
    "tqdm",
    "yaml",
    "av",
    "httpx",
    "httpcore",
    "anyio",
    "h11",
    "fsspec",
]
hiddenimports += collect_submodules("transformers.models.nllb")
hiddenimports += collect_submodules("ctranslate2")
hiddenimports += collect_submodules("faster_whisper")

excludes = [
    "yo.overlay_linux",
    "yo.hotkey_linux",
    "yo.loop_linux",
    "yo.inject_linux",
    "yo.ipc_linux",
    "gi",
    "gi.repository",
    "Xlib",
    "cairo",
    "torch",
    "torchvision",
    "torchaudio",
    "tensorflow",
    "matplotlib",
    "IPython",
    "pytest",
]

a = Analysis(
    [str(ROOT / "yo" / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(SPECDIR / "rthook_console.py")],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Yo-Voice",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON) if ICON.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Yo-Voice",
)
