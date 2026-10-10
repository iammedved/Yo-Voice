# Yo-Voice Windows port status

## Installed audio hotfix — 2026-10-06

This section supersedes the historical snapshot below for the installed build.

- Rebuilt with PyInstaller from this working tree, preserving pre-existing local game/hotkey changes. Installed into `D:\ProgramFiles\Yo-Voice`; process restarted from that exact path and IPC ping returned `pong`.
- Installed EXE SHA256: `3a6b85040680cec69502ac501c5c40f1d2b9ecb55aee0afb565452d8e41d2122`. `audio-hotfix-build.json` beside the EXE records build/source hashes. `scripts/verify_frozen_sources.py` compares the bundled code for seven changed modules against current source; all match. This caught stale packaging cache before installation; final build used a clean work directory.
- Full previous installation and pre-update configuration: `D:\ProgramFiles\Yo-Voice-backup-20261006-audio`. Existing downloaded models, voiceprint, microphone and hotkeys retained. Enabled `speaker_filter=true` using the existing voiceprint, threshold 0.40.
- Removed VAD auto-gain (up to 20×), energy-based speech bypasses, and automatic energy fallback. Silero now needs probability 0.50 to start / 0.35 to continue plus RMS ≥ 0.0007. ASR gain capped at 4× instead of 40×; rejects no-speech probability > 0.60 and average log probability < -1.0, as well as non-finite samples/confidence.
- Speaker filtering no longer passes unverified clips under 0.5 seconds, missing samples/models or inference failures. Settings copy reflects blocked input. A selected missing microphone cannot fall back to a different microphone; silence does not trigger reopening. First callback uses the native capture sample rate.
- Idle audio retains only 0.4 seconds of pre-roll; uninterrupted speech is queued in approximately 30-second chunks, with a regression checking sample conservation.
- Final full test run: **401 tests, OK, 1 skipped** (CUDA wheel collection without `nvidia-cublas-cu12`). Actual installed WeSpeaker model test passed. A transient clipboard lock failed an earlier repeat; the isolated retry and final full run passed. Logs: `build/tests-audio-fix-final.log`.
- Actual Silero rejected 10-second zero, noise and hum fixtures. Russian Windows TTS phrase recognized correctly at original and 10× quieter amplitude, including the legitimate word «салюты». Existing saved voiceprint rejected that synthetic speaker. Logs: `build/speech-positive-regression.log`.
- Live fifine AM8 Pro diagnostic, without text injection: first 10.06-second capture produced zero speech starts / zero retained speech. A second identical-input comparison retained **0.822 seconds with the old code and 0 with the fix**. Audio was processed in memory, not archived. Logs: `build/microphone-audio-fix.log`, `build/microphone-before-after.log`.
- After installation the program opened the selected fifine, passed a live phrase through voice verification, recognition and paste. No claim of an exhaustive real-TV or simultaneous-speaker test: voice similarity is probabilistic, overlapping voices remain inseparable, faint or very short dictation may be rejected. Re-enroll in quiet surroundings if the saved voiceprint no longer matches the speaker/microphone. OS/driver gain controls were not changed.
- The installed app and `dist/Yo-Voice` are updated. The older standalone Setup installer has not been regenerated or published in this task.

QA snapshot of `D:\AI\whatneed\windows-migrate\04-yo-voice` against the **local Linux product** (`README.md`) and against **GitHub `iammedved/Yo-Voice`**. Version in this tree is still **1.0.0**. No git commit was made.

## GitHub `iammedved/Yo-Voice` vs this tree

| | GitHub `main` | This tree |
|---|---|---|
| HEAD | `e0da531` (2026-08-22), Linux-only 1.0.0 | Same `e0da531` **plus uncommitted work** (dirty working tree; not pushed) |
| Origin | https://github.com/iammedved/Yo-Voice.git | Same remote; Windows files are local-only |
| Product claim | README: does **not** run on Windows / macOS | Linux `README.md` still says that (kept for `tests/test_release_docs.py`). Windows runbook is `README-WINDOWS.md` |
| ASR | `faster-whisper` `large-v3-turbo` (~1.6 GB first download) | `coriollon/whisper-large-v3-turbo-russian` (~0.8 GB). Legacy `large-v3-turbo` maps to it |
| Translate | Not in 1.0.0 GitHub README | Optional second bind: local NLLB rus→eng (`JustFrederik/nllb-200-distilled-600M-ct2-int8`) |
| Rebind | Right-click = mic **Авто** only | Right-click = mic **Авто**, rebind listen, optional translate bind |
| OS backends | X11 / GTK / Unix socket / `~/.config/autostart` | Linux backends kept; Windows selected at runtime (`sys.platform == "win32"`) |
| Install | `scripts/install.sh` | Linux script kept; Windows: `scripts/install.ps1`, `scripts/run.ps1`, `scripts/yo-voice.cmd` |
| Frozen binaries | None | None yet (`dist\` missing) |

Uncommitted Linux work in this snapshot (also not on GitHub `main`): `yo/bind.py`, `yo/mt.py`, `yo/terms.py`, overlay rebind, NLLB, Russian turbo model, brand polish. Windows facades split the old single-file backends:

- `yo/hotkey.py` → `hotkey_linux.py` / `hotkey_win.py`
- `yo/overlay.py` → `overlay_linux.py` / `overlay_win.py`
- `yo/inject.py` → `inject_linux.py` / `inject_win.py`
- `yo/ipc.py` → `ipc_linux.py` / `ipc_win.py`
- plus `yo/loop.py`, `yo/clip_win.py`, `yo/settings_win.py`, `yo/autostart_win.py`, `yo/winapi.py`

`yo/paths.py` inlines Windows `%APPDATA%` / `%LOCALAPPDATA%`. `yo/paths_win.py` exists but is unused.

## Feature parity (local Linux README vs Windows)

Status: **code+unit** = implemented and covered by tests on this machine. **code** = implemented, not live-exercised. **gap** = missing or unverified.

| Feature | Linux | Windows | Status |
|---|---|---|---|
| Local PTT Russian ASR, nothing uploaded | faster-whisper, audio stays on machine | Same `yo/asr.py` / `yo/app.py` | **code+unit** (no live Whisper run) |
| Model `coriollon/whisper-large-v3-turbo-russian` | First listen downloads ~0.8 GB | Same; cache `%LOCALAPPDATA%\yo-voice\hf` | **code+unit** resolve path; **first-run download not exercised** |
| Hotkey: key left of `1` (ё / grave, X11 49) | X11 grab keycode 49 | `VK_OEM_3` (`0xC0`); 49 maps to OEM_3 | **code+unit** |
| Shift+ё still types Ё | Unshifted grab only | Low-level keyboard hook; modifiers (`_mods_down`) pass through; `RegisterHotKey` not used (would swallow Shift+ё) | **code+unit** (source + hook logic; no live keystroke) |
| Overlay cat Жду → Можно говорить → Слушаю | GTK / cairo, no focus | tkinter chroma overlay, `WS_EX_NOACTIVATE` + `MA_NOACTIVATE` | **code+unit** phrases/layout; **live window not shown** |
| Waveform only while capturing | `wave_allowed` | Same gate in `overlay_win.py` | **code+unit** |
| Right-click: mic **Авто** | GTK menu | tk `Menu` in `settings_win.py` | **code+unit** |
| Rebind listen (key or mouse) | GTK + X11 capture | `capture_bind` + `WH_KEYBOARD_LL` / `WH_MOUSE_LL` | **code+unit** |
| Optional translate bind, local NLLB rus→eng | `yo/mt.py` | Same engine; Windows menu item **Назначить кнопку перевода** | **code+unit**; **NLLB download not exercised** |
| Overlay **Перевод** in translate mode | `task=overlay.task` | `task=self.task` → `display_label` | **code+unit** |
| Paste into focused field | XTest Ctrl+V | `SendInput` Ctrl+V | **code** |
| Ctrl+Shift+V in terminals | VTE / kitty / … | Windows Terminal, WT Preview, conhost, OpenConsole | **code+unit** (detection strings) |
| Dictation restores clipboard; translate leaves English | `restore_clipboard_after_paste` | Same + `clip_win.py` Unicode clipboard | **code+unit** |
| Autostart at login | `~/.config/autostart/yo-voice.desktop` | `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\Yo-Voice` → `pythonw -m yo daemon` | **code+unit**; **not live-registered in this QA pass** |
| User-level config, no cloud | `~/.config/yo-voice/` | `%APPDATA%\yo-voice\config.json` | **code+unit** |
| Logs / IPC | `~/.cache/yo-voice/yo.sock` | `%LOCALAPPDATA%\yo-voice\` + `yo.port` (TCP 127.0.0.1) | **code+unit** (IPC ping) |
| CLI: toggle / start / stop / status / settings / quit / demo + background process | `yo-voice` | `python -m yo`, `scripts\yo-voice.cmd` | **code+unit**; `--help` and `status` smoked |
| Silero VAD ONNX shipped | `yo/data/silero_vad.onnx` | Same file, 2 327 524 bytes; `package-data` in `pyproject.toml` | **code+unit** |
| Desktop / app-menu launcher | `.desktop` + `~/.local/bin/yo-voice` | `install.ps1` does **not** create Start Menu / Desktop shortcuts; HKCU Run + `yo-voice.cmd` only | **gap** vs Linux launcher UX (frozen Setup.exe may add this later) |
| Overlay transparency | GTK RGBA | tk `-transparentcolor` chroma `#00FF01` (not `UpdateLayeredWindow` per-pixel alpha) | **code**; visual risk if a pixel is that green |
| PulseAudio jack availability | `pactl` | Unused; PortAudio device list | expected platform split |
| Frozen `.exe` / Inno Setup | n/a | `dist\Yo-Voice\Yo-Voice.exe`, `dist\Yo-Voice-Setup.exe` | **gap** — not present at QA time |

Windows extras required by the port brief (Ctrl+V / Ctrl+Shift+V in WT/conhost) are implemented in `yo/inject_win.py`.

## How to install the `.exe` / `Setup.exe` once they exist

They were **not** in the tree during this pass (`dist\` missing). When packaging lands:

**Portable onedir (no installer):**

```powershell
dist\Yo-Voice\Yo-Voice.exe --help
dist\Yo-Voice\Yo-Voice.exe status
# same CLI as python -m yo: toggle | start | stop | settings | quit | demo
```

**Inno Setup (user-level, silent, no Program Files GUI):**

```powershell
dist\Yo-Voice-Setup.exe /VERYSILENT /CURRENTUSER
```

Do not run Setup with a GUI click into Program Files. `/CURRENTUSER` keeps it reversible from Apps & features / Add or Remove Programs. Uninstall after a silent user install: same uninstaller, or Apps & features → Yo-Voice.

**Source install (verified path today):**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install.ps1
.\.venv\Scripts\python.exe -m yo --help
```

## What was verified

Python: `.venv\Scripts\python.exe` → **3.12.10** 64-bit.

| Command | Result |
|---|---|
| `python -c "import yo.app"` | `IMPORT_OK` `yo\app.py`. `ctypes.wintypes.HCURSOR` / `HICON` / `HBRUSH` / `HHOOK` / `HINSTANCE` already aliased in `yo/winapi.py`; no QA edit to `yo/*.py` |
| `.venv\Scripts\python.exe -m unittest discover -s tests -t . -v` | **Ran 202 tests in 1.219s — OK** (0 failed, 0 skipped, 0 errors). First discovery attempt failed until `tests/__init__.py` existed (`Start directory is not importable`) |
| `python -m yo --help` | Exit 0. Commands: `toggle,start,stop,daemon,demo,status,quit,settings` |
| `python -m yo status` | Exit 1, `Ёхо не запущена` (no background process; expected) |
| Silero ONNX | `yo\data\silero_vad.onnx` present, 2 327 524 bytes |
| `dist\Yo-Voice\Yo-Voice.exe` | **Absent** — no `--help` / `status` smoke |
| `dist\Yo-Voice-Setup.exe` | **Absent** — live install skipped |

QA test edits (not product):

- `tests/__init__.py` — empty package so `discover -s tests -t .` works on Python 3.12
- `tests/test_terms.py` — patch `APPDATA` on win32 so user `replacements.json` is found (Linux still uses `XDG_CONFIG_HOME`)
- `tests/test_translate.py` — overlay task wiring inspected in `overlay_linux.py` (`task=overlay.task`) and `overlay_win.py` (`task=self.task`); facade `overlay.py` no longer contains the GTK draw path

`test_release_docs.py` was not gutted; Linux `README.md` still asserts GitHub 1.0.0 claims (including “What it cannot do”).

Whisper and NLLB were **not** downloaded.

## Gaps / remaining bugs

1. **No frozen artifacts.** Cannot smoke `Yo-Voice.exe` or measure Setup.exe size. No `.spec` / `.iss` in the tree at QA time.
2. **First-run model download not exercised** (Whisper ~0.8 GB, NLLB on first translate).
3. **No live PTT / overlay / paste session** (would pull models and grab the global hook).
4. **Autostart not live-checked** in HKCU; unit test only covers the `pythonw -m yo daemon` command string.
5. **No Start Menu / Desktop launcher** from `install.ps1` (Linux has `.desktop`). Frozen Setup may cover this; source install does not.
6. **Overlay is chroma-key tkinter**, not layered per-pixel alpha (`yo/winapi.py` has `UpdateLayeredWindow` unused by `overlay_win.py`). Possible fringe/green-fringe vs Linux cairo.
7. **`yo/paths_win.py` unused.** Live paths ignore `XDG_CONFIG_HOME` on Windows (correct for users; tests now patch `APPDATA`).
8. **GPU / `nvidia-cublas-cu12` path not verified.** `install.ps1` skips those wheels if they fail; CPU fallback is the tested import path.
9. **GitHub `main` is not this product.** Shipping Windows from GitHub clone of `e0da531` would miss the port and the later Linux NLLB/rebind/russian-turbo work.

No failing unit tests remain on this machine.
