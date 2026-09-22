# Yo-Voice

[![Version 1.0.0](https://img.shields.io/badge/version-1.0.0-C41E6A)](CHANGELOG.md)

<img src="assets/readme-hero.png" alt="Yo-Voice cat speaking into a microphone. Overlay status Слушаю and transcript: Нажал ё — текст уже в поле." width="100%">

**Yo-Voice** (Ёхо) is local Russian dictation for **Linux** and **Windows**. Press the hotkey once, speak, pause — the transcript is pasted into whatever text field has focus. Press the same control again to stop. Releasing the key does nothing: this is a toggle, not hold-to-talk.

It is not a cloud product. Microphone audio and transcripts stay on the computer that runs it.

## What it does

- Types what you say into the **currently focused** text field (browser, editor, chat, terminal).
- Runs **on your machine**. Speech is recognized locally with `faster-whisper` (`coriollon/whisper-large-v3-turbo-russian`). Nothing is uploaded to a speech API.
- Speaks **Russian**. Punctuation and capitalization are cleaned up after recognition. A second hotkey (unset until you assign it) recognizes that Russian speech locally, then translates the Russian transcript to **English** with a local **NLLB** model and pastes the English into the focused field.
- Shows a small **cat overlay** while listening: **Жду** (waiting / loading), **Можно говорить** (about one second after the mic is live), then **Слушаю** (listening). The waveform moves only while the microphone is actually capturing.
- Lets you pick the microphone by **right-clicking the cat**, and rebind the listen toggle to any keyboard key or mouse button from that same menu. One button starts and stops listening.
- Can start at login. On Linux, `scripts/install.sh` turns that on. On Windows, the Setup wizard leaves the box **unchecked** until you tick it.

## What it cannot do

Yo-Voice 1.0.0 does **not**:

- Run on **macOS**
- Run on a **Wayland-only** Linux session (Linux needs **X11** for the global hotkey and paste)
- Send audio or text to the cloud, or offer an account / sync
- Stream words into the cursor **while you are still talking** (it pastes after a pause, or when you press the hotkey again)
- Keep a history of recordings or WAV files
- Translate into languages other than English (the optional second hotkey is Russian speech → English text only)
- Use an AMD, Intel, or other non-NVIDIA graphics chip for recognition (that path is the CPU)
- Paste into an elevated window, or into some exclusive fullscreen apps, on Windows
- Replace a full accessibility on-screen keyboard or a system-wide IME

Linux reference: **Linux Mint 22.3, Cinnamon, X11**. Windows reference: **Windows 11**, 64-bit. The installer also accepts Windows 10, 64-bit.

## Privacy

- **Your speech never leaves this computer.** Recognition runs locally.
- **Transcripts are not uploaded.** Dictation and translate both stay on this computer: there is no DeepL (or other translation API) call.
- **Clipboard.** On Linux, dictation pastes through the clipboard and then restores what was there before. Translate pastes the English and **leaves that English on the clipboard**. On Windows, the pasted text **stays** on the clipboard (dictation and translate), so a manual paste still works if the keystroke could not be delivered.
- **Journal.** Recognized phrases are written to a log on this computer. That file is removed **6 hours** after its first line. While Ёхо is running, the check is about once a minute, so the file can outlive the six hours by about a minute. If Ёхо is quit, the file stays until the next start; a start that finds a journal already six hours old deletes it before writing again. The new file appears on the next line, not as an empty placeholder at the moment of deletion. Settings and downloaded models are not part of this cleanup. There is still no WAV or recording archive.
- **Linux paths:** config in `~/.config/yo-voice/`, log and cache in `~/.cache/yo-voice/`.
- **Windows paths:** config in `%APPDATA%\yo-voice\`, log, cache, and models in `%LOCALAPPDATA%\yo-voice\`.
- The only expected network use is **install time** (Python packages, or downloading the Windows installer), the **first listen**, which downloads Whisper model weights (~0.8 GB) into a local cache, and the **first use of the translate hotkey**, which downloads local NLLB weights. Those downloads are model files, not your microphone or transcripts. The speech models are not inside the Windows installer.

## Hotkey

Dictation starts on the key **immediately left of `1`**:

| Keyboard layout | Key |
|---|---|
| Russian (ЙЦУКЕН) | **ё** |
| US / UK | **\`** (grave / tilde key, unshifted) |

On Linux that is X11 keycode **49**. On Windows it is the same physical key. Holding **Shift+ё** still types **Ё** — only the unshifted key is the toggle.

To use another keyboard key or mouse button: right-click the cat → **Назначить кнопку** → press that key or button. The same control still both starts and stops listening. Mouse-wheel ticks are not used as the toggle.

A second control is optional: right-click the cat → **Назначить кнопку перевода** → press a different key or mouse button. That toggle listens to Russian and pastes English. While the cat is already listening, the other key switches the current phrase to the other mode. The two controls cannot be the same button. Nothing is assigned for translation until you pick one.

If another app already owns that key, the overlay says `клавиша ё занята`.

## Recognition

- **NVIDIA** present: recognition uses that GPU (CUDA). The Russian model runs as `int8_float16`.
- **No NVIDIA** (including a Ryzen PC whose only graphics chip is a Radeon): recognition and translation run on the **CPU** as `int8`, with at most 8 threads. The installer does not unpack the NVIDIA libraries in that case. No NVIDIA driver is required. The pause after a phrase is longer than on a discrete NVIDIA GPU. The graphics chip is not used, because the recognizer speaks CUDA or CPU only.
- If Windows cannot read the display-adapter list, the installer still unpacks the NVIDIA libraries, and recognition falls back to the CPU when no NVIDIA GPU is actually available.
- The Ready page of `Yo-Voice-Setup.exe` states which of these it picked. It does not write a settings file and does not force CPU mode on an NVIDIA PC.

## Install on Linux

### 1. System packages

```bash
sudo apt update
sudo apt install -y \
  git curl \
  python3 python3-venv python3-pip \
  python3-gi python3-gi-cairo python3-cairo python3-xlib \
  gir1.2-gtk-3.0 libportaudio2
```

Install your NVIDIA driver from Driver Manager if you want GPU recognition. Without NVIDIA, CPU mode still runs.

### 2. Download

```bash
git clone https://github.com/iammedved/Yo-Voice.git
cd Yo-Voice
```

### 3. Install

```bash
chmod +x scripts/install.sh
./scripts/install.sh
```

The installer:

1. Creates `.venv` (with system GTK / X11 bindings)
2. Installs Python dependencies, including CUDA libraries when available
3. Puts a **Ёхо** launcher on the Desktop and in the application menu
4. Enables **autostart** of this program (`~/.config/autostart/yo-voice.desktop`, 3 second delay)
5. Symlinks `yo-voice` into `~/.local/bin/`

### 4. First launch

1. If the Desktop icon asks for permission, choose **Allow Launching**.
2. Click **Ёхо**, or run `yo-voice` (add `~/.local/bin` to `PATH` if needed).
3. Press **ё** / **\`**. The cat appears. The **first** time, it downloads the model and the overlay may show a loading status for a minute.
4. Speak Russian. When you pause, text is pasted at the caret. Press the hotkey again to stop.

Right-click the cat to choose the microphone (**Авто** = automatic) or to rebind the toggle key / mouse button.

### Later launches (every day after that)

You do **not** need to open the app by hand.

- After you log into Cinnamon, **this program starts by itself**.
- Press **ё** / **\`** to start or stop listening.
- The Desktop / menu icon toggles listening the same way.
- First-run model download happens only once; later starts are local and fast on an NVIDIA GPU.

Useful commands:

```bash
yo-voice              # toggle listening (starts this program if needed)
yo-voice status       # idle | listening
yo-voice start        # start listening
yo-voice stop         # stop and paste
yo-voice settings     # microphone window
yo-voice quit         # quit this program
yo-voice demo         # overlay demo without dictation
```

Re-run `./scripts/install.sh` after a `git pull` to refresh the venv and launchers.

Requirements: Linux with an **X11** session, Python **3.10+**, a microphone. An NVIDIA GPU is faster; CPU mode works and is slower. Disk: a few hundred MB for the app, plus **~0.8 GB** for the Whisper model on first listen.

## Install on Windows

Windows users do not need Python or a clone. Download **[Yo-Voice-Setup.exe](https://github.com/iammedved/Yo-Voice/releases/download/v1.0.0-windows/Yo-Voice-Setup.exe)** (64-bit, Windows 10 or 11). The file is large because the app can carry NVIDIA libraries. The ~0.8 GB speech model is a separate download the first time you listen.

1. Double-click `Yo-Voice-Setup.exe`. A normal install does not ask for an administrator account. Picking a protected folder can.
2. The suggested folder is `%LOCALAPPDATA%\Programs\Yo-Voice`. If Ёхо is already installed somewhere else, choose **that same folder**. The wizard does not always remember a custom folder, and accepting the suggestion creates a second copy.
3. The task **Запускать Ёхо при входе в Windows (рекомендуется)** starts **unchecked**. Tick it if Ёхо should start when you sign in. Leaving it unchecked **removes** an existing logon entry for Ёхо.
4. The Ready page names the mode: NVIDIA CUDA, or CPU when no NVIDIA adapter was found. Unknown adapters still get the NVIDIA libraries, with CPU fallback if there is no NVIDIA GPU.
5. Finish. The last page can start Ёхо. Desktop and Start Menu shortcuts are named **Ёхо** and leave it in the tray.

Then press **ё** / **\`**, speak, and pause. The first listen downloads the model into `%LOCALAPPDATA%\yo-voice\`. Paste is Ctrl+V, or Ctrl+Shift+V in Windows Terminal. The pasted text stays on the clipboard.

Uninstall from Settings → Apps → **Ёхо (Yo-Voice)**, or run `Uninstall.exe` in the install folder. That removes the program, the shortcuts, and the logon entry. It does **not** delete `%APPDATA%\yo-voice` (settings) or `%LOCALAPPDATA%\yo-voice` (models and the journal).

Running Setup again stops a running copy, then copies files over the folder you chose.

From a source checkout, Python **3.12** and `scripts/install.ps1` are the other path. Unlike the wizard, that script **does** register logon start unless you pass `-NoAutostart`. Details: [README-WINDOWS.md](README-WINDOWS.md).

## How a dictation pass works

1. Hotkey (or the launcher) tells this program to listen.
2. Overlay appears without stealing keyboard focus, so the caret stays in your app.
3. Silero VAD keeps silence out of Whisper; only speech is transcribed.
4. On a pause, the utterance is recognized locally and pasted (Ctrl+V; Ctrl+Shift+V in a terminal).
5. Press the hotkey again to flush the last bit and hide the cat.

## Troubleshooting

| Symptom | What to try |
|---|---|
| Waves do not move | Unmute the headset mic. Right-click the cat and pick the real device, not a monitor/loopback. |
| `подключите микрофон` | No usable capture device. Plug in a mic and pick it in the menu. |
| `клавиша ё занята` | Another program grabbed the key. Close it, or right-click the cat and pick another. |
| Linux icon does nothing | Desktop files on Mint often need **Allow Launching**. Or run `yo-voice` in a terminal. |
| First start is slow | Model download, or CPU mode on a PC without NVIDIA. Later starts should not download again. |
| GPU unused | NVIDIA: driver, and on Linux the CUDA wheels from `install.sh`. Any other GPU stays on the CPU. |
| Nothing pastes | Click the target field first. The overlay never takes focus on purpose. On Windows, an elevated or exclusive-fullscreen window may ignore the paste; the text is still on the clipboard. |

## Versioning

This tree is **1.0.0**. See [CHANGELOG.md](CHANGELOG.md). Git tags follow semver (`v1.0.0`). The Windows installer of this same version is the `Yo-Voice-Setup.exe` asset on the [`v1.0.0-windows`](https://github.com/iammedved/Yo-Voice/releases/tag/v1.0.0-windows) release. That asset is the built app, not something `git checkout v1.0.0` produces by itself.

## License

[MIT](LICENSE). Third-party models (`faster-whisper` / Whisper weights, Silero VAD, NLLB) keep their own licenses.
