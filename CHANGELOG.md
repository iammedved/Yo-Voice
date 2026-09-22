# Changelog

## Unreleased

- A settings file that cannot be read is left on disk. Ёхо uses the usual defaults only in memory until that file can be read again. A missing settings file is still created. A finished save writes a temporary file in the same folder and replaces the real file only after that write completes, so a crash in the middle does not leave a half-written settings file.
- Cleanup after recognition no longer rewrites four real phrases: «и слушая», «у тора», «у сорта», and «громко и тонко». «громко четко» still becomes «громко и чётко», «находятся сорта» still becomes «находится у рта», and «стоит монитора» still becomes «стоит у монитора».
- A pause inside one phrase is not sent back to recognition. The short margin stays only before the first speech and after the last.
- The Windows Setup wizard asks whether to download the ~0.8 GB Russian recognition model now (selected by default) or after the first launch. The progress window moves from real bytes received, then a check that the files on disk match the expected sizes. It is not a timer, and 100% is only that finished check. A successful new download starts the program again so the model loads cleanly. Weights that are already complete are not downloaded again and do not restart in a loop. The English translation model is still a separate download the first time you translate.
- A defect shows the date and time, what was being done, an error code, and a cause when the program can tell. Otherwise the report still has the code, the time, and which block it came from. One button, **Отправить разработчику**, opens a prefilled GitHub issue. There is no token in the program, and the issue is sent only when you submit it in the browser. The tray item is **Сообщить о сбое**.
- Windows 10/11 64-bit ships as `Yo-Voice-Setup.exe` (app version still 1.0.0). NVIDIA adapters use CUDA; when the adapter list is readable and has no NVIDIA, the installer does not unpack those libraries and recognition stays on the CPU (`int8`, at most 8 threads). An AMD or Intel graphics chip is not used. The suggested folder is `%LOCALAPPDATA%\Programs\Yo-Voice`. The logon checkbox starts unchecked, and leaving it unchecked removes an existing logon entry.
- Recognized lines in the local log are deleted 6 hours after that file's first line. While the program is running the check is about once a minute. If it is quit, the file stays until the next start, which deletes an already-expired journal before writing. The next line creates the new file. No WAV archive. Settings and downloaded models are not deleted with the log. Same rule on Linux and Windows.
- Listening is a toggle on Linux and Windows: one press starts, the next stops, and releasing the key does not paste. A pause while still listening inserts the phrase.
- Linux dictation still restores the previous clipboard. Windows leaves the pasted text on the clipboard. Translate on both leaves the English text on the clipboard.
- Capture accepts close-mic whisper: Silero sees a boosted copy, energy VAD no longer raises the gate into shout range, and overlay waves move on quiet speech
- After you stop the toggle, the mic keeps the last ~300 ms and one extra buffer so the final word is not cut
- Silero trims the clip for Whisper instead of a second energy gate; quiet endings stay
- Brand names (Ёхо, Grok, ChatGPT, …) are rewritten after recognition in `terms.py`; they are not fed to Whisper as hotwords
- Spoken ChatGPT (`чат джи пити`, CatGPT, …) and Sol 5.6 (`солл 5.6`, `соул пять точка шесть`, `лолл пять точка шесть`, …) rewrite to the English spelling. Bare «бол» / «толл» without a version stay as spoken.
- If you spoke and nothing could be pasted, the cat says **не разобрал**. Spoken «спасибо» / «пожалуйста» are kept
- Local recognizer is `coriollon/whisper-large-v3-turbo-russian` (legacy `large-v3-turbo` maps to it; the codeswitch repo id stays opt-in and is not the default). First launch may download those files; speech still never leaves this computer
- Whisper decode uses `without_timestamps` and temperature 0.0
- Microphone is stored and matched by PortAudio name (stable if the `hw:` index moves); analog jacks whose Pulse ports are not available stay off the menu
- Quiet live blocks are not pre-amplified in the capture callback; Whisper still gets one utterance-level boost
- Optional second hotkey: Russian speech → English text in the focused field, and the English stays on the clipboard. Assign it from the cat menu (**Назначить кнопку перевода**). The dictation key is unchanged. The overlay says **Перевод** in that mode instead of **Слушаю**. Recognition still uses the same Whisper model with no reload; English comes from a local NLLB pass over the Russian transcript, not from Whisper speech-translate and not from DeepL.
- Dictation mouse button still turns the cat off even when the pointer is over it; assigning the translate button no longer swallows the press.
- Overlay, desktop icon, and README hero: two standing grey hind paws with pink toe beans; the extra belly paw and reversed black-boot soles are gone
- README and changelog now say this program wherever they meant the program running in the background
- Right-click the cat to rebind the listen toggle to any keyboard key or mouse button; one control still starts and stops listening
- A missing microphone stays on `подключите микрофон` instead of flipping to `Слушаю`

## 1.0.0 — 2026-08-22

First public release of **Yo-Voice** (Ёхо).

- Local Russian dictation with `faster-whisper` `large-v3-turbo`
- Overlay cat mascot with status phrases Жду / Можно говорить / Слушаю
- Silero VAD so only speech is sent to Whisper
- Microphone picker: right-click the cat
- Hotkey: `ё` / `` ` `` (X11 keycode 49, the key left of `1`)
- Starts this program at login
- Paste into the focused field via Ctrl+V (Ctrl+Shift+V in terminals)
