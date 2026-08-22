"""Оркестратор Ёхо: overlay, микрофон, ASR, вставка, горячая клавиша."""

from __future__ import annotations

import logging
import queue
import signal
import threading

import gi
import numpy as np

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk

from yo.asr import AsrEngine
from yo.audio import AudioCapture, stream_looks_dead
from yo.capture import has_microphone, listen_capture_plan, resolve_portaudio_device
from yo.config import Config, load_config, save_config
from yo.hotkey import HotkeyWatcher
from yo.inject import Injector
from yo.ipc import IpcServer
from yo.overlay import Overlay
from yo.session import DictationSession, accept_asr_commit
from yo.spectrum import SAMPLE_RATE
from yo.vad import SpeechGate, trim_to_speech

log = logging.getLogger("yo.app")
HOTKEY_BUSY_HINT = "клавиша ё занята"


class YoApp:
    def __init__(self, config: Config | None = None) -> None:
        self.config = config or load_config()
        saved = None
        if self.config.overlay_x is not None and self.config.overlay_y is not None:
            saved = (int(self.config.overlay_x), int(self.config.overlay_y))
        self.overlay = Overlay(
            saved_pos=saved,
            on_move=self._save_overlay_pos,
            on_settings=self._open_settings,
        )
        self.engine = AsrEngine(self.config.model, self.config.device)
        self.injector = Injector()
        self.session = DictationSession(self._inject_text)
        self.audio = AudioCapture(self._on_block, sample_rate=self.config.sample_rate)
        self.vad = SpeechGate()
        self._chunks: list[np.ndarray] = []
        self._chunks_lock = threading.Lock()
        self._token = 0
        self._utt = 0
        self._stopping = False
        self._hotkey: HotkeyWatcher | None = None
        self._ipc: IpcServer | None = None
        self._mic_poll_id: int | None = None
        self._saved_clip: str | None = None
        self._clip_owned = False
        self._pending_pastes = 0
        self._paste_q: list[str] = []
        self._paste_armed = False
        self._jobs: queue.Queue = queue.Queue()
        self._worker = threading.Thread(target=self._job_loop, daemon=True, name="yo-asr")
        self._worker.start()

    def _save_overlay_pos(self, x: int, y: int) -> None:
        self.config.overlay_x = int(x)
        self.config.overlay_y = int(y)
        save_config(self.config)

    def start_background(self) -> None:
        self._sync_mic()
        threading.Thread(target=self.engine.load, daemon=True).start()
        self._ipc = IpcServer(self._on_ipc)
        self._ipc.start()
        self._hotkey = HotkeyWatcher(self.config.hotkey_keycode, lambda: GLib.idle_add(self.toggle))
        self._hotkey.start()
        GLib.timeout_add(250, self._report_hotkey)
        signal.signal(signal.SIGINT, lambda *_: GLib.idle_add(self.quit))
        signal.signal(signal.SIGTERM, lambda *_: GLib.idle_add(self.quit))

    def toggle(self) -> bool:
        if self.session.listening:
            self.stop_listen()
        else:
            self.start_listen()
        return False

    def start_listen(self) -> bool:
        if self.session.listening or self._stopping:
            return False
        self._token += 1
        self.session.start()
        self.vad = SpeechGate()
        self._utt = 0
        self._stopping = False
        self._clip_owned = False
        self._saved_clip = None
        with self._chunks_lock:
            self._chunks = []
        has_mic = self._sync_mic()
        self.overlay.set_live(False)
        self.overlay.show_listening()
        self._arm_mic_poll()
        if not has_mic:
            return False
        if not self.engine.loaded():
            threading.Thread(target=self._load_then_mic, daemon=True).start()
        else:
            self._go_live()
        return False

    def stop_listen(self) -> bool:
        if not self.session.listening:
            self.overlay.hide()
            return False
        if self._stopping:
            return False
        self._stopping = True
        self._stop_mic_poll()
        self.audio.stop()
        self.overlay.set_live(False)
        audio = self._take_chunks()
        self._jobs.put((audio, True, self._token, None))
        return False

    def quit(self) -> bool:
        self._stop_mic_poll()
        self.audio.stop()
        self.session.stop()
        self.overlay.hide()
        if self._hotkey:
            self._hotkey.stop()
        if self._ipc:
            self._ipc.stop()
        self._jobs.put(None)
        Gtk.main_quit()
        return False

    def _load_then_mic(self) -> None:
        try:
            self.engine.load(lambda msg: GLib.idle_add(self.overlay.set_status, msg))
        except Exception as exc:
            GLib.idle_add(self._load_failed, str(exc))
            return
        if self.session.listening:
            GLib.idle_add(self._go_live)

    def _go_live(self) -> bool:
        if not self.session.listening:
            return False
        if not self._sync_mic():
            return False
        try:
            self._start_capture()
        except Exception:
            log.exception("не удалось открыть микрофон")
            self.overlay.set_live(False)
            self.overlay.set_mic_missing(True)
            return False
        self.overlay.set_live(True)
        GLib.timeout_add(1000, self._check_dead_stream)
        return False

    def _start_capture(self) -> None:
        device = resolve_portaudio_device(self.config.microphone)
        if device is None:
            raise RuntimeError("микрофон не найден")
        log.info("захват устройства %s (%s)", device, self.config.microphone or "auto")
        self.audio.start(device=device)

    def _sync_mic(self) -> bool:
        plan = listen_capture_plan(has_microphone())
        self.overlay.set_mic_missing(bool(plan["mic_missing"]))
        return bool(plan["start_capture"])

    def _arm_mic_poll(self) -> None:
        if self._mic_poll_id is not None:
            return
        self._mic_poll_id = GLib.timeout_add(1500, self._poll_mic)

    def _stop_mic_poll(self) -> None:
        sid = self._mic_poll_id
        self._mic_poll_id = None
        if sid is None:
            return
        try:
            GLib.source_remove(sid)
        except Exception:
            pass

    def _poll_mic(self) -> bool:
        if not self.session.listening or self._stopping:
            self._mic_poll_id = None
            return False
        was_missing = self.overlay.mic_missing
        ok = self._sync_mic()
        if ok and was_missing and self.engine.loaded():
            try:
                self._start_capture()
                self.overlay.set_live(True)
                GLib.timeout_add(1000, self._check_dead_stream)
            except Exception:
                log.exception("не удалось открыть микрофон")
                self.overlay.set_live(False)
                self.overlay.set_mic_missing(True)
        elif not ok:
            self.audio.stop()
            self.overlay.set_live(False)
        return True

    def _load_failed(self, message: str) -> bool:
        self.session.stop()
        self._stopping = False
        self.overlay.set_status(f"ошибка модели: {message}")
        GLib.timeout_add(2200, self._hide)
        return False

    def _on_block(self, pcm: np.ndarray, level: float, bands: list[float]) -> None:
        GLib.idle_add(self._push_levels, float(level), list(bands), np.copy(pcm))
        if not self.session.listening:
            return
        event = self.vad.process(pcm, self.config.sample_rate)
        if event == "start":
            self._utt += 1
            with self._chunks_lock:
                self._chunks = [pcm]
            return
        if event in {"speech", "end"} or self.vad.speaking:
            if event != "start":
                with self._chunks_lock:
                    self._chunks.append(pcm)
        if event == "end":
            audio = self._take_chunks()
            utt = self._utt
            if audio is not None:
                self._jobs.put((audio, False, self._token, utt))
            return

    def _push_levels(self, level: float, bands: list[float], pcm) -> bool:
        self.overlay.set_levels(level, bands, pcm)
        return False

    def _job_loop(self) -> None:
        while True:
            item = self._jobs.get()
            if item is None:
                return
            self._finalize(*item)

    def _check_dead_stream(self) -> bool:
        if not self.session.listening or self._stopping or self.overlay.mic_missing:
            return False
        if stream_looks_dead(self.audio.peak_level, 1000.0):
            log.warning("поток микрофона тихий, peak_rms=%s", self.audio.peak_level)
            self.audio.stop()
            self.overlay.set_live(False)
            self.overlay.set_mic_missing(True)
        return False

    def _report_hotkey(self) -> bool:
        hk = self._hotkey
        if hk is None or not hk.error:
            return False
        log.error("горячая клавиша: %s", hk.error)
        if not self.session.listening:
            self.overlay.set_hint(HOTKEY_BUSY_HINT)
            self.overlay.show_listening(HOTKEY_BUSY_HINT)
            GLib.timeout_add(3500, self._hide_hotkey_hint)
        return False

    def _hide_hotkey_hint(self) -> bool:
        if not self.session.listening:
            self.overlay.hide()
        return False

    def _finalize(
        self,
        audio: np.ndarray | None,
        hide_after: bool,
        token: int,
        utt: int | None = None,
    ) -> None:
        raw = ""
        try:
            speech = trim_to_speech(audio, self.config.sample_rate, backend="energy")
            if speech is not None and len(speech) > SAMPLE_RATE * 0.12:
                raw = self.engine.transcribe(speech, self.config.sample_rate)
        except Exception as exc:
            log.exception("ошибка распознавания")
            GLib.idle_add(self._finalize_failed, str(exc), hide_after, token)
            return
        if raw:
            log.info("распознано utt=%s hide=%s: %s", utt, hide_after, raw)
        GLib.idle_add(self._commit_raw, raw, hide_after, token, utt)

    def _finalize_failed(self, message: str, hide_after: bool, token: int) -> bool:
        self.overlay.set_status(f"ошибка: {message}")
        if hide_after and token == self._token:
            self.session.stop()
            self._stopping = False
            GLib.timeout_add(900, self._hide)
        return False

    def _commit_raw(
        self,
        raw: str,
        hide_after: bool,
        token: int,
        utt: int | None = None,
    ) -> bool:
        if not accept_asr_commit(
            token=token,
            current_token=self._token,
            listening=self.session.listening,
            stopping=self._stopping,
        ):
            return False
        text = self.session.commit_utterance(raw) if raw else ""
        if text:
            self.overlay.set_preview(text.strip())
        if hide_after:
            self.session.stop()
            self._stopping = False
            self.overlay.set_live(False)
            GLib.timeout_add(220, self._hide)
        return False

    def _inject_text(self, text: str) -> None:
        def _arm() -> bool:
            self._paste_q.append(text)
            if not self._paste_armed:
                self._paste_armed = True
                GLib.timeout_add(45, self._flush_paste)
            return False

        if threading.current_thread() is not threading.main_thread():
            GLib.idle_add(_arm)
            return
        _arm()

    def _flush_paste(self) -> bool:
        if not self._paste_q:
            self._paste_armed = False
            return False
        text = self._paste_q.pop(0)
        clip = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        if not self._clip_owned:
            self._saved_clip = clip.wait_for_text()
            self._clip_owned = True
        clip.set_text(text, -1)
        clip.store()
        self._pending_pastes += 1
        try:
            self.injector.paste()
        except Exception:
            log.exception("ошибка вставки")
        finally:
            self._pending_pastes = max(0, self._pending_pastes - 1)
        if self._paste_q:
            GLib.timeout_add(70, self._flush_paste)
        else:
            self._paste_armed = False
        return False

    def _restore_clipboard(self) -> bool:
        if self._pending_pastes > 0:
            GLib.timeout_add(80, self._restore_clipboard)
            return False
        if self._clip_owned and self._saved_clip is not None:
            clip = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            clip.set_text(self._saved_clip, -1)
        self._saved_clip = None
        self._clip_owned = False
        return False

    def _hide(self) -> bool:
        self.overlay.hide()
        GLib.timeout_add(80, self._restore_clipboard)
        return False

    def _take_chunks(self) -> np.ndarray | None:
        with self._chunks_lock:
            chunks = self._chunks
            self._chunks = []
        if not chunks:
            return None
        return np.concatenate(chunks)

    def _open_settings(self, event=None) -> bool:
        from yo.settings import popup_mic_menu

        popup_mic_menu(
            widget=self.overlay.window,
            event=event,
            on_pick=lambda _name: GLib.idle_add(self._reload_config),
        )
        return False

    def _reload_config(self) -> bool:
        self.config = load_config()
        if self.session.listening and not self._stopping and not self.overlay.mic_missing:
            try:
                self._start_capture()
                self.overlay.set_live(True)
            except Exception:
                log.exception("не удалось переключить микрофон")
                self.overlay.set_live(False)
                self.overlay.set_mic_missing(True)
        return False

    def _on_ipc(self, command: str) -> str:
        cmd = command.strip().lower()
        if cmd == "toggle":
            GLib.idle_add(self.toggle)
            return "ok"
        if cmd == "start":
            GLib.idle_add(self.start_listen)
            return "ok"
        if cmd == "stop":
            GLib.idle_add(self.stop_listen)
            return "ok"
        if cmd == "reload":
            GLib.idle_add(self._reload_config)
            return "ok"
        if cmd == "settings":
            GLib.idle_add(self._open_settings)
            return "ok"
        if cmd in {"status"}:
            return "listening" if self.session.listening else "idle"
        if cmd in {"quit", "exit"}:
            GLib.idle_add(self.quit)
            return "bye"
        return "unknown"


def run_daemon() -> None:
    Gtk.init([])
    app = YoApp()
    app.start_background()
    log.info("Ёхо запущена")
    Gtk.main()
