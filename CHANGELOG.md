# Changelog

## Unreleased

- Overlay and desktop icon: the cat mascot now includes complete hind paws instead of a cropped canvas

## 1.0.0 — 2026-08-22

First public release of **Yo-Voice** (Ёхо).

- Local Russian dictation with `faster-whisper` `large-v3-turbo`
- Overlay cat mascot with status phrases Жду / Можно говорить / Слушаю
- Silero VAD so only speech is sent to Whisper
- Microphone picker: right-click the cat
- Hotkey: `ё` / `` ` `` (X11 keycode 49, the key left of `1`)
- Autostart background daemon on login
- Paste into the focused field via Ctrl+V (Ctrl+Shift+V in terminals)
