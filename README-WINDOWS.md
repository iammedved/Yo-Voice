# Yo-Voice (Ёхо) on Windows

Local Russian dictation for 64-bit Windows 10 or 11. Press the hotkey **once**, speak, pause — the transcript is pasted into the focused text field. Press the same control again to stop. Releasing the key does not stop or paste. Audio never leaves this machine.

The same program on Linux is in [README.md](README.md). Linux needs X11. Windows does not use that path.

Most people should install **[Yo-Voice-Setup.exe](https://github.com/iammedved/Yo-Voice/releases/download/v1.0.0-windows/Yo-Voice-Setup.exe)** and skip the source steps.

## Installer

`Yo-Voice-Setup.exe` is the Windows analog of Linux `scripts/install.sh`: Start Menu and Desktop shortcuts **Ёхо**, an optional logon task, and uninstall without an administrator account unless the folder you pick requires one.

1. Double-click the Setup file.
2. Suggested folder: `%LOCALAPPDATA%\Programs\Yo-Voice`. If Ёхо is already installed in another folder, choose that same folder. Accepting the suggestion otherwise creates a second copy. The wizard does not always remember a custom folder.
3. **Запускать Ёхо при входе в Windows (рекомендуется)** starts **unchecked**. Tick it to start at sign-in. Leaving it unchecked removes an existing logon entry for Ёхо.
4. The speech-model page offers two choices. **Download now** starts selected and downloads `coriollon/whisper-large-v3-turbo-russian` (~0.8 GB) before the wizard finishes. **After the first launch** skips that step. The progress window counts real bytes, then checks file sizes on disk. It is not a timer. **100%** means that check passed. A new download starts the program again so the model loads cleanly. Weights that are already complete are left in place and do not restart in a loop. The same window is used if you chose later and the weights are still missing at the first start.
5. On the Ready page, read the mode. NVIDIA adapters use CUDA and the NVIDIA libraries are unpacked. If the adapters were read and none is NVIDIA, those libraries are not unpacked and recognition stays on the CPU (`int8`, at most 8 threads). An AMD or Intel graphics chip is not used. If the adapter list could not be read, the libraries are unpacked and recognition still falls back to the CPU when there is no NVIDIA GPU. The page does not write settings and does not force CPU on an NVIDIA PC.
6. Finish. You can start Ёхо from the last page. Shortcuts leave it in the tray.

The Setup file is large because it can carry NVIDIA libraries. Whisper (~0.8 GB) and NLLB are **not** inside it. Whisper is the choice above. NLLB still downloads on the first translate, into `%LOCALAPPDATA%\yo-voice\`.

A failure dialog has the date and time, what was being done, an error code, and a cause when the program can tell. Otherwise it still names the code, the time, and the block. **Отправить разработчику** opens a prefilled issue at `https://github.com/iammedved/Yo-Voice/issues/new`. The program does not contain a token, and you still submit the issue in the browser. A link that would be too long is also copied to the clipboard. The tray item **Сообщить о сбое** opens the same report. The developer sees it when the issue exists.

Running Setup again stops a running copy, then updates the folder you selected.

**Uninstall:** Settings → Apps → **Ёхо (Yo-Voice)**, or `Uninstall.exe` in the install folder. That removes the program files, shortcuts, and the logon entry. It does **not** delete settings (`%APPDATA%\yo-voice`) or models and the journal (`%LOCALAPPDATA%\yo-voice`).

## What a session stores

| Item | Where |
|---|---|
| Settings | `%APPDATA%\yo-voice\config.json` |
| Models, cache, journal | `%LOCALAPPDATA%\yo-voice\` |
| Program | the folder you chose, by default `%LOCALAPPDATA%\Programs\Yo-Voice\Yo-Voice.exe` |

If `config.json` cannot be read, Ёхо does not replace it with defaults. Defaults are used only in memory. A missing settings file is still created. A finished save writes a temporary file in the same folder and replaces `config.json` only after that write completes.

The journal holds recognized lines and is deleted **6 hours** after its first line. While Ёхо is open the check runs about once a minute. After you quit, the file stays until the next start, and a start that finds it already six hours old deletes it before writing. The next line creates the new file. Settings, models, and the port file are not deleted with it. There is no WAV archive.

On Windows the pasted text **stays on the clipboard**. Linux dictation puts the previous clipboard back; Windows does not. Translate on both leaves the English text on the clipboard.

Paste is Ctrl+V, or Ctrl+Shift+V in Windows Terminal. An elevated window or some exclusive fullscreen apps may ignore the keystroke; the text is still on the clipboard.

## Hotkey

Default listen key is **immediately left of `1`**: **ё** on ЙЦУКЕН, **\`** (grave / tilde) on a US layout. **Shift+ё** still types **Ё**.

Right-click the cat → **Назначить кнопку** to rebind the toggle (keyboard or mouse). **Назначить кнопку перевода** assigns a different control for local Russian → English (NLLB). Nothing is assigned for translation until you pick one.

## First use

1. Start Ёхо from the shortcut, or tick logon start and sign in again.
2. Press **ё**. The cat shows **Жду**, then **Можно говорить**, then **Слушаю**.
3. If the speech model was not downloaded during Setup and is not already on disk, the first start shows the same 1–100% window, then starts the program again after a new download.
4. Speak and pause. Text is pasted into the focused field.

## Recognition

NVIDIA CUDA when a NVIDIA GPU is present (`int8_float16` for the Russian model). Otherwise CPU `int8`. No ROCm, DirectML, or Vulkan path. A machine without NVIDIA does not need an NVIDIA driver and will feel slower after each phrase.

A pause inside one phrase is not sent back to recognition. The short margin stays only before the first speech and after the last. Cleanup still fixes known mishearings, but «и слушая», «у тора», «у сорта», and «громко и тонко» stay as spoken. «громко четко» still becomes «громко и чётко».

## Install from source

Python **3.12** (not 3.13):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install.ps1
```

That creates `.venv`, installs `requirements.txt`, and registers logon start. Pass `-NoAutostart` to skip the logon entry, or `-Launch` to start immediately. This default is the opposite of the Setup wizard, whose logon box starts unchecked.

```powershell
powershell -File scripts\run.ps1
scripts\yo-voice.cmd
.\.venv\Scripts\python.exe -m yo
```

Useful commands, same words as Linux:

```text
python -m yo              # toggle listening (starts this program if needed)
python -m yo status       # idle | listening
python -m yo start
python -m yo stop
python -m yo settings
python -m yo quit
python -m yo demo         # overlay demo without dictation
```

Rebuild `Yo-Voice-Setup.exe` only after `dist\Yo-Voice\Yo-Voice.exe` exists:

```powershell
powershell -ExecutionPolicy Bypass -File installer\build-setup.ps1
```

The script uses [Inno Setup](https://jrsoftware.org/isinfo.php) (`ISCC.exe`) and writes `E:\yo-voice\Yo-Voice-Setup.exe` plus a copy at `dist\Yo-Voice-Setup.exe`. Compiling the installer does not run the wizard and does not replace an already installed copy.

## Git

Repository: <https://github.com/iammedved/Yo-Voice.git>

The Windows app version is **1.0.0**, shipped as `Yo-Voice-Setup.exe` on the [`v1.0.0-windows`](https://github.com/iammedved/Yo-Voice/releases/tag/v1.0.0-windows) release. Linux install remains `scripts/install.sh` from this tree. Tag `v1.0.0` is the older source tag and is not a substitute for that installer.
