Yo-Voice Windows onedir (PyInstaller)
=====================================

Build (from repo root, venv already created):

  powershell -ExecutionPolicy Bypass -File packaging\build-exe.ps1

Output:

  dist\Yo-Voice\                 redistributable folder (copy this)
  dist\Yo-Voice\Yo-Voice.exe     windowed entry (yo.__main__:main)

Commands (same as `python -m yo`):

  Yo-Voice.exe                  start daemon in this process (tray + overlay)
  Yo-Voice.exe status|start|stop|quit|settings|demo|daemon|toggle
  Yo-Voice.exe --help

Not bundled (downloaded on first listen/translate into %LOCALAPPDATA%\yo-voice\hf):

  Whisper weights (~0.8 GB, coriollon/whisper-large-v3-turbo-russian)
  NLLB CTranslate2 + tokenizer snapshots

Bundled:

  Python runtime, yo package, assets\, yo\data\silero_vad.onnx
  faster-whisper, ctranslate2 (+ its DLLs), onnxruntime, sounddevice/PortAudio
  transformers tokenizer stack (no model weights)

Config: %APPDATA%\yo-voice\
Cache / logs / models: %LOCALAPPDATA%\yo-voice\
