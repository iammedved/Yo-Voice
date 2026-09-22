"""Оркестратор Ёхо: overlay, микрофон, ASR, вставка, горячая клавиша."""

from __future__ import annotations

import logging
import os
import queue
import signal
import sys
import threading
import time

import numpy as np

from yo.asr import AsrEngine
from yo.audio import STOP_TAIL_MS, AudioCapture, stream_looks_dead
from yo.bind import (
    ToggleBind,
    binds_conflict,
    capture_bind,
    listen_press_action,
    normalize_bind,
    optional_bind,
    restore_clipboard_after_paste,
)
from yo.capture import (
    MIC_PERMISSION_HINT,
    NO_MIC_HINT,
    capture_candidate_indices,
    capture_microphone_update,
    dead_stream_plan,
    has_microphone,
    listen_capture_plan,
    mic_open_hint,
    microphone_permission_denied,
    portaudio_name_at,
    presence_poll_plan,
)
from yo.config import Config, load_config, patch_config
from yo.hotkey import HotkeyWatcher
from yo.inject import Injector
from yo.ipc import IpcServer
from yo.loop import clipboard_get, clipboard_set, idle_add, loop_init, loop_main, loop_quit, source_remove, timeout_add
from yo.mt import LocalTranslator, english_from_russian_asr
from yo.overlay import Overlay
from yo.phrases import UNRECOGNIZED
from yo.session import (
    DictationSession,
    accept_asr_commit,
    empty_speech_feedback,
    too_sparse_for_duration,
)
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
        self.translator = LocalTranslator(self.config.device)
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
        self._rebinding = False
        self._rebind_target = "transcribe"
        self._rebind_gen = 0
        self._rebind_overlay_only = False
        self._ipc: IpcServer | None = None
        self._mic_poll_id: int | None = None
        self._saved_clip: str | None = None
        self._clip_owned = False
        self._pending_pastes = 0
        self._paste_q: list[str] = []
        self._paste_armed = False
        self._paste_fail = 0
        self._paste_hwnd = 0
        self._overlay_hwnd = 0
        self._last_good_paste = 0
        self._jobs: queue.Queue = queue.Queue()
        self._tray = None
        self._worker = threading.Thread(target=self._job_loop, daemon=True, name="yo-asr")
        self._worker.start()

    def _save_overlay_pos(self, x: int, y: int) -> None:
        self.config = patch_config(overlay_x=int(x), overlay_y=int(y))

    def start_background(self) -> None:
        self._sync_mic()
        threading.Thread(target=self._preload_models, daemon=True, name="yo-asr-load").start()
        self._ipc = IpcServer(self._on_ipc)
        self._ipc.start()
        self._restart_hotkey()
        if sys.platform == "win32":
            self._start_tray()
            timeout_add(400, self._track_paste_target)
        from yo.logutil import DICTATION_LOG_CHECK_MS

        timeout_add(DICTATION_LOG_CHECK_MS, self._expire_dictation_log)
        signal.signal(signal.SIGINT, lambda *_: idle_add(self.quit))
        signal.signal(signal.SIGTERM, lambda *_: idle_add(self.quit))

    def _expire_dictation_log(self) -> bool:
        from yo.logutil import DICTATION_LOG_CHECK_MS, expire_dictation_log

        try:
            expire_dictation_log()
        except Exception:
            log.debug("не удалось проверить срок журнала", exc_info=True)
        timeout_add(DICTATION_LOG_CHECK_MS, self._expire_dictation_log)
        return False

    def _preload_models(self) -> None:
        try:
            self.engine.load()
        except Exception:
            log.warning("модель ASR не загрузилась (будет повтор при записи)", exc_info=True)

    def toggle(self) -> bool:
        return self._press("transcribe")

    def toggle_translate(self) -> bool:
        return self._press("translate")

    def _press(self, task: str) -> bool:
        if self._rebinding:
            return False
        action = listen_press_action(
            listening=self.session.listening,
            current_task=self.session.task,
            pressed_task=task,
        )
        if action == "start":
            self.start_listen(task=task)
        elif action == "stop":
            self.stop_listen()
        else:
            self._switch_task(task)
        return False

    def _switch_task(self, task: str) -> None:
        self.session.set_task(task)
        self.overlay.set_task(task)

    def _cancel_rebind(self) -> None:
        if not self._rebinding:
            return
        self._rebind_gen += 1
        self._rebinding = False
        self._rebind_overlay_only = False
        self._restart_hotkey()
        self._restore_status_hint()

    def start_listen(self, task: str = "transcribe") -> bool:
        self._cancel_rebind()
        if self.session.listening or self._stopping:
            return False
        self._token += 1
        self.session.start(task=task)
        self.overlay.set_task(task)
        self.vad = SpeechGate()
        self._utt = 0
        self._stopping = False
        self._clip_owned = False
        self._saved_clip = None
        with self._chunks_lock:
            self._chunks = []
        has_mic = self._sync_mic()
        if has_mic and not (self.overlay.hint or "").strip():
            self.overlay.set_hint("")
            self.overlay.set_live(True)
        elif not has_mic:
            self.overlay.set_live(False)
        # Snapshot the focused app before the overlay maps — paste must not
        # target the cat if show/hide briefly activates it.
        self._snapshot_paste_target()
        set_anchor = getattr(self.overlay, "set_anchor", None)
        if callable(set_anchor):
            set_anchor(self._paste_hwnd)
        self.overlay.show_listening()
        if sys.platform == "win32":
            try:
                native = getattr(self.overlay, "native_id", None)
                hwnd = native() if callable(native) else None
                if hwnd:
                    self._overlay_hwnd = int(hwnd)
            except Exception:
                pass
        self._arm_mic_poll()
        if not has_mic:
            return False
        # Paint the cat first; PortAudio probe must not freeze the overlay.
        timeout_add(0, self._go_live)
        if not self.engine.loaded():
            threading.Thread(target=self._load_then_mic, daemon=True, name="yo-asr-load-listen").start()
        return False

    def stop_listen(self) -> bool:
        self._cancel_rebind()
        if not self.session.listening:
            self.overlay.hide()
            return False
        if self._stopping:
            return False
        self._stopping = True
        self._stop_mic_poll()
        timeout_add(STOP_TAIL_MS, self._finish_stop, self._token)
        return False

    def quit(self) -> bool:
        self._stop_mic_poll()
        self.audio.stop(drain=False)
        self.session.stop()
        self.overlay.hide()
        if self._hotkey:
            self._hotkey.stop()
        if self._ipc:
            self._ipc.stop()
        tray = self._tray
        self._tray = None
        if tray is not None:
            try:
                tray.stop()
            except Exception:
                log.exception("не удалось убрать иконку из трея")
        self._jobs.put(None)
        loop_quit()
        return False

    def _finish_stop(self, token: int) -> bool:
        if token != self._token or not self._stopping:
            return False
        self.overlay.set_live(False)
        self.audio.stop(drain=True)
        audio = self._take_chunks()
        self._jobs.put((audio, True, token, None, self.session.task))
        return False

    def _load_then_mic(self) -> None:
        try:
            self.engine.load(lambda msg: idle_add(self.overlay.set_status, msg))
        except Exception as exc:
            idle_add(self._load_failed, str(exc))
            return
        if self.session.listening and not self.overlay.live:
            idle_add(self._go_live)

    def _surface_mic_error(self, hint: str, *, missing: bool = False) -> None:
        log.error("микрофон: %s", hint)
        self.overlay.set_live(False)
        if missing:
            self.overlay.set_mic_missing(True)
            if hint and hint != NO_MIC_HINT:
                self.overlay.set_hint(hint)
        else:
            self.overlay.set_mic_missing(False)
            self.overlay.set_hint(hint)
        tray = getattr(self, "_tray", None)
        if tray is not None and missing:
            try:
                tray.show_message(hint)
            except Exception:
                log.exception("не удалось показать уведомление")

    def _go_live(self) -> bool:
        if not self.session.listening:
            return False
        if not self._sync_mic():
            return False
        # Open on the Tk/UI thread: WASAPI/DirectSound need this apartment.
        # timeout_add(0) already painted the cat; do not spawn a worker.
        try:
            self._start_capture()
        except Exception as exc:
            log.exception("не удалось открыть микрофон")
            hint = mic_open_hint(exc)
            self._surface_mic_error(hint, missing=hint == NO_MIC_HINT)
            return False
        self._mark_live()
        return False

    def _mark_live(self) -> bool:
        if not self.session.listening or self._stopping:
            return False
        self.overlay.set_mic_missing(False)
        self.overlay.set_hint("")
        self.overlay.set_live(True)
        timeout_add(1000, self._check_dead_stream)
        return False

    def _start_capture(self) -> None:
        last_error: Exception | None = None
        opened: int | None = None
        wanted = (self.config.microphone or "").strip()
        candidates = capture_candidate_indices(wanted)
        exclusive_modes = [False]
        if sys.platform == "win32":
            exclusive_modes.append(True)
        log.info("микрофон из настроек %s кандидаты %s", wanted or "auto", candidates)
        for exclusive in exclusive_modes:
            for device in candidates:
                try:
                    log.info("захват устройства %s exclusive=%s", device, exclusive)
                    self.audio.start(device=device, exclusive=exclusive)
                    opened = device
                    break
                except Exception as exc:
                    log.warning("захват device=%s exclusive=%s: %s", device, exclusive, exc)
                    if not exclusive or last_error is None:
                        last_error = exc
            if opened is not None:
                break
        if opened is None:
            if last_error is not None:
                raise last_error
            raise RuntimeError("микрофон не найден")
        name = portaudio_name_at(opened)
        log.info("микрофон %s (%s)", opened, name or wanted or "auto")
        if wanted:
            return
        update = capture_microphone_update(wanted, name)
        if update is not None:
            self.config = patch_config(microphone=update)

    def _sync_mic(self) -> bool:
        plan = listen_capture_plan(has_microphone())
        if microphone_permission_denied():
            self.overlay.set_mic_missing(False)
            self.overlay.set_hint(MIC_PERMISSION_HINT)
            return bool(plan["start_capture"])
        self.overlay.set_mic_missing(bool(plan["mic_missing"]))
        return bool(plan["start_capture"])

    def _arm_mic_poll(self) -> None:
        if self._mic_poll_id is not None:
            return
        self._mic_poll_id = timeout_add(1500, self._poll_mic)

    def _stop_mic_poll(self) -> None:
        sid = self._mic_poll_id
        self._mic_poll_id = None
        if sid is None:
            return
        source_remove(sid)

    def _poll_mic(self) -> bool:
        if not self.session.listening or self._stopping:
            self._mic_poll_id = None
            return False
        was_missing = self.overlay.mic_missing
        ok = self._sync_mic()
        plan = presence_poll_plan(ok, was_missing=was_missing)
        if plan["stop_capture"]:
            self.audio.stop(drain=False)
            self.overlay.set_live(False)
            return True
        if plan["start_capture"] and self.engine.loaded():
            if not self.overlay.live:
                self._go_live()
        return True

    def _load_failed(self, message: str) -> bool:
        self.audio.stop(drain=False)
        self.session.stop()
        self._stopping = False
        self.overlay.set_status(f"ошибка модели: {message}")
        timeout_add(2200, self._hide)
        return False

    def _on_block(self, pcm: np.ndarray, level: float, bands: list[float]) -> None:
        idle_add(self._push_levels, float(level), list(bands), np.copy(pcm))
        if not self.session.listening and not self._stopping:
            return
        with self._chunks_lock:
            self._chunks.append(pcm)
        if self._stopping or not self.session.listening:
            return
        event = self.vad.process(pcm, self.config.sample_rate)
        if event == "start":
            self._utt += 1
        if event == "end":
            audio = self._take_chunks()
            utt = self._utt
            if audio is not None:
                self._jobs.put((audio, False, self._token, utt, self.session.task))
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
        if not stream_looks_dead(self.audio.peak_level, 1000.0):
            return False
        log.warning("поток микрофона тихий, peak_rms=%s", self.audio.peak_level)
        if microphone_permission_denied():
            self._surface_mic_error(MIC_PERMISSION_HINT)
            return False
        plan = dead_stream_plan(has_microphone())
        if plan["stop_capture"]:
            self.audio.stop(drain=False)
        if plan["live"] is False:
            self.overlay.set_live(False)
        if plan["mic_missing"]:
            self.overlay.set_mic_missing(True)
        # Quiet but present: keep Слушаю/Перевод. Barracuda idle is not a mute.
        return False

    def _report_hotkey(self) -> bool:
        hk = self._hotkey
        if hk is None or not hk.error:
            return False
        log.error("горячая клавиша: %s", hk.error)
        if not self.session.listening:
            self.overlay.set_hint(HOTKEY_BUSY_HINT)
            self.overlay.show_listening(HOTKEY_BUSY_HINT)
            timeout_add(3500, self._hide_hotkey_hint)
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
        task: str = "transcribe",
    ) -> None:
        raw = ""
        speech_seconds = 0.0
        try:
            speech = trim_to_speech(audio, self.config.sample_rate, backend="auto")
            if speech is not None and len(speech) > SAMPLE_RATE * 0.12:
                speech_seconds = len(speech) / float(SAMPLE_RATE)
                raw = self.engine.transcribe(speech, self.config.sample_rate)
                if raw:
                    log.info("распознано utt=%s hide=%s task=%s: %s", utt, hide_after, task, raw)
                if task == "translate" and raw:
                    status = "загрузка перевода" if not self.translator.loaded() else "перевод"
                    idle_add(self.overlay.set_status, status)
                    raw = english_from_russian_asr(raw, self.translator.translate_ru_en)
                    if raw:
                        log.info("перевод utt=%s: %s", utt, raw)
        except Exception as exc:
            log.exception("ошибка распознавания")
            idle_add(self._finalize_failed, str(exc), hide_after, token)
            return
        idle_add(self._commit_raw, raw, hide_after, token, utt, task, speech_seconds)

    def _finalize_failed(self, message: str, hide_after: bool, token: int) -> bool:
        self.overlay.set_status(f"ошибка: {message}")
        if hide_after and token == self._token:
            self.session.stop()
            self._stopping = False
            timeout_add(900, self._hide)
        return False

    def _commit_raw(
        self,
        raw: str,
        hide_after: bool,
        token: int,
        utt: int | None = None,
        task: str = "transcribe",
        speech_seconds: float = 0.0,
    ) -> bool:
        if not accept_asr_commit(
            token=token,
            current_token=self._token,
            listening=self.session.listening,
            stopping=self._stopping,
        ):
            return False
        if raw and too_sparse_for_duration(raw, speech_seconds):
            log.info(
                "длинный клип %.1f с и короткий текст (%s) — не вставляю",
                speech_seconds,
                raw,
            )
            raw = ""
        text = self.session.commit_utterance(raw, task=task) if raw else ""
        if text:
            self.overlay.set_preview(text.strip())
        else:
            feedback = empty_speech_feedback(
                speech_seconds=speech_seconds,
                raw=raw,
                polished=text,
            )
            if feedback:
                self.overlay.set_status(feedback)
                if not hide_after:
                    timeout_add(1400, self._clear_unrecognized)
        if hide_after:
            self.session.stop()
            self._stopping = False
            self.overlay.set_live(False)
            timeout_add(900 if not text else 220, self._hide)
        return False

    def _clear_unrecognized(self) -> bool:
        if self.overlay.status == UNRECOGNIZED:
            self.overlay.set_status("")
        return False

    def _snapshot_paste_target(self) -> None:
        self._paste_hwnd = 0
        self._overlay_hwnd = 0
        if sys.platform != "win32":
            return
        try:
            from yo.inject_win import usable_paste_target
            from yo.winapi import (
                cursor_pos,
                focused_hwnd,
                hwnd_int,
                user32,
                window_from_point,
                window_label,
            )

            overlay = 0
            native = getattr(self.overlay, "native_id", None)
            if callable(native):
                overlay = hwnd_int(native())
            self._overlay_hwnd = overlay

            raw = focused_hwnd()
            target = usable_paste_target(raw, overlay)
            if not target:
                fg = hwnd_int(user32.GetForegroundWindow())
                target = usable_paste_target(fg, overlay)
                if target:
                    raw = fg
            if not target:
                try:
                    cx, cy = cursor_pos()
                    under = window_from_point(cx, cy)
                    target = usable_paste_target(under, overlay)
                    if target:
                        raw = under
                        log.info(
                            "цель вставки под курсором hwnd=%s %s",
                            target,
                            window_label(target),
                        )
                except Exception:
                    pass
            if not target:
                target = usable_paste_target(self._last_good_paste, overlay)
                if target:
                    fg = hwnd_int(user32.GetForegroundWindow())
                    log.info(
                        "цель вставки последняя рабочая hwnd=%s %s (fg=%s %s)",
                        target,
                        window_label(target),
                        fg,
                        window_label(fg),
                    )
            self._paste_hwnd = target
            if target:
                self._last_good_paste = target
                log.info("цель вставки hwnd=%s %s", target, window_label(target))
            elif raw:
                log.info(
                    "цель вставки оболочка hwnd=%s %s — вставлю в активное поле",
                    raw,
                    window_label(raw),
                )
            else:
                log.info("цель вставки не запомнена overlay=%s", overlay)
        except Exception:
            log.debug("не удалось запомнить окно для вставки", exc_info=True)
            self._paste_hwnd = 0
            self._overlay_hwnd = 0

    def _track_paste_target(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            from yo.inject_win import usable_paste_target
            from yo.winapi import focused_hwnd, hwnd_int, user32

            overlay = self._overlay_hwnd
            if not overlay:
                native = getattr(self.overlay, "native_id", None)
                if callable(native):
                    overlay = hwnd_int(native()) or 0
            got = usable_paste_target(focused_hwnd(), overlay)
            if not got:
                got = usable_paste_target(hwnd_int(user32.GetForegroundWindow()), overlay)
            if got:
                self._last_good_paste = got
        except Exception:
            pass
        timeout_add(400, self._track_paste_target)
        return False

    def _inject_text(self, text: str) -> None:
        def _arm() -> bool:
            self._paste_q.append(text)
            if not self._paste_armed:
                self._paste_armed = True
                # Win32: hide overlay at +220ms; paste after that so Ctrl+V
                # cannot land on the cat if deiconify briefly stole focus.
                delay = 280 if sys.platform == "win32" else 45
                timeout_add(delay, self._flush_paste)
            return False

        if threading.current_thread() is not threading.main_thread():
            idle_add(_arm)
            return
        _arm()

    def _flush_paste(self) -> bool:
        if not self._paste_q:
            self._paste_armed = False
            return False
        text = self._paste_q.pop(0)
        if not self._clip_owned:
            self._saved_clip = clipboard_get()
            self._clip_owned = True
        try:
            clipboard_set(text)
            self._paste_fail = 0
        except Exception:
            log.exception("не удалось записать текст в буфер обмена")
            self._paste_fail += 1
            if self._paste_fail < 3:
                self._paste_q.insert(0, text)
                timeout_add(120, self._flush_paste)
            elif self._paste_q:
                timeout_add(70, self._flush_paste)
            else:
                self._paste_armed = False
                self._paste_fail = 0
            return False
        log.info("в буфер %s символов", len(text))
        self._pending_pastes += 1
        parked = False
        if sys.platform == "win32":
            try:
                native = getattr(self.overlay, "native_id", None)
                hwnd = native() if callable(native) else None
                if hwnd:
                    self._overlay_hwnd = int(hwnd)
            except Exception:
                pass
            try:
                mapped = False
                ov = self._overlay_hwnd
                if ov:
                    try:
                        from yo.winapi import user32 as _u32

                        mapped = bool(_u32.IsWindowVisible(ov))
                    except Exception:
                        mapped = False
                if (getattr(self.overlay, "visible", False) or mapped) and hasattr(
                    self.overlay, "park"
                ):
                    self.overlay.park()
                    parked = True
                    log.info("оверлей спрятан перед вставкой")
            except Exception:
                parked = False
            try:
                from yo.inject_win import choose_paste_hwnd, usable_paste_target
                from yo.winapi import (
                    allow_set_foreground,
                    focused_hwnd,
                    hwnd_int,
                    user32,
                    window_root,
                )

                allow_set_foreground()
                overlay = self._overlay_hwnd
                live = usable_paste_target(focused_hwnd(), overlay)
                if not live:
                    live = usable_paste_target(
                        hwnd_int(user32.GetForegroundWindow()), overlay
                    )
                chosen, reason = choose_paste_hwnd(self._paste_hwnd, live, overlay)
                if reason == "live-fallback":
                    log.info(
                        "перед вставкой снимок непригоден — беру активное окно hwnd=%s",
                        chosen,
                    )
                elif reason == "keep-snapshot":
                    log.info(
                        "перед вставкой оставляю снимок hwnd=%s, активное окно hwnd=%s другое",
                        chosen,
                        live,
                    )
                elif reason == "same-root":
                    log.info(
                        "перед вставкой беру фокус того же окна hwnd=%s вместо снимка hwnd=%s",
                        chosen,
                        self._paste_hwnd,
                    )
                if chosen:
                    self._paste_hwnd = chosen
                    root = window_root(chosen)
                    if root and user32.IsWindow(root):
                        ok = bool(user32.SetForegroundWindow(root))
                        log.info(
                            "перед вставкой SetForegroundWindow hwnd=%s ok=%s",
                            root,
                            ok,
                        )
            except Exception:
                log.debug("не удалось вернуть поле перед вставкой", exc_info=True)
        try:
            self.injector.paste(
                hwnd=self._paste_hwnd or None,
                overlay_hwnd=self._overlay_hwnd or None,
            )
        except TypeError:
            self.injector.paste()
        except Exception:
            log.exception("ошибка вставки")
        finally:
            self._pending_pastes = max(0, self._pending_pastes - 1)
            if parked and self.session.listening:
                timeout_add(160, self._unpark_overlay)
        if self._paste_q:
            timeout_add(70, self._flush_paste)
        else:
            self._paste_armed = False
        return False

    def _unpark_overlay(self) -> bool:
        if not self.session.listening:
            return False
        try:
            if hasattr(self.overlay, "unpark"):
                self.overlay.unpark()
        except Exception:
            log.debug("не удалось вернуть оверлей после вставки", exc_info=True)
        return False

    def _restore_clipboard(self) -> bool:
        if self._pending_pastes > 0:
            timeout_add(80, self._restore_clipboard)
            return False
        if restore_clipboard_after_paste(task=self.session.task):
            if self._clip_owned and self._saved_clip is not None:
                clipboard_set(self._saved_clip)
        self._saved_clip = None
        self._clip_owned = False
        return False

    def _hide(self) -> bool:
        self.overlay.hide()
        if sys.platform == "win32":
            try:
                from yo.inject_win import usable_paste_target
                from yo.winapi import (
                    allow_set_foreground,
                    focused_hwnd,
                    hwnd_int,
                    user32,
                    window_root,
                )

                allow_set_foreground()
                overlay = self._overlay_hwnd
                live = usable_paste_target(focused_hwnd(), overlay)
                if not live:
                    live = usable_paste_target(
                        hwnd_int(user32.GetForegroundWindow()), overlay
                    )
                saved = usable_paste_target(self._paste_hwnd, overlay)
                target = live or saved
                if target:
                    root = window_root(target)
                    if user32.IsWindow(root):
                        user32.SetForegroundWindow(root)
            except Exception:
                log.debug("не удалось вернуть фокус после overlay", exc_info=True)
        timeout_add(80, self._restore_clipboard)
        return False

    def _take_chunks(self) -> np.ndarray | None:
        with self._chunks_lock:
            chunks = self._chunks
            self._chunks = []
        if not chunks:
            return None
        return np.concatenate(chunks)

    def _start_tray(self) -> None:
        if sys.platform != "win32":
            return
        try:
            from yo.tray_win import TrayIcon

            self._tray = TrayIcon(
                on_settings=lambda: idle_add(self._open_settings),
                on_open_log=lambda: idle_add(self._open_log),
                on_quit=lambda: idle_add(self.quit),
                on_toggle=lambda: idle_add(self.toggle),
            )
            show_intro = not bool(getattr(self.config, "tray_intro_shown", False))
            self._tray.start(balloon=show_intro)
            if show_intro:
                self.config = patch_config(tray_intro_shown=True)
        except Exception:
            log.exception("не удалось создать иконку в трее")

    def _open_log(self) -> bool:
        from yo.paths import xdg_cache

        path = xdg_cache() / "daemon.log"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(exist_ok=True)
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception:
            log.exception("не удалось открыть журнал")
        return False

    def _open_settings(self, event=None) -> bool:
        from yo.settings import popup_mic_menu

        try:
            popup_mic_menu(
                widget=self.overlay.window,
                event=event,
                on_pick=lambda name: idle_add(self._reload_config, name),
                on_rebind=lambda: idle_add(self._begin_rebind),
                on_rebind_translate=lambda: idle_add(self._begin_translate_rebind),
                listening=self.session.listening,
            )
        except Exception:
            log.exception("окно настроек не открылось")
        return False

    def _overlay_xid(self) -> int | None:
        native = getattr(self.overlay, "native_id", None)
        if native is not None:
            try:
                return native()
            except Exception:
                return None
        return None

    def _current_bind(self) -> ToggleBind:
        return normalize_bind(self.config.hotkey_kind, self.config.hotkey_keycode)

    def _translate_bind(self) -> ToggleBind | None:
        return optional_bind(self.config.translate_hotkey_kind, self.config.translate_hotkey_keycode)

    def _pause_hotkeys(self) -> None:
        if self._hotkey is not None:
            self._hotkey.stop()
            self._hotkey = None

    def _hotkey_pairs(self) -> list[tuple[ToggleBind, object]]:
        pairs: list[tuple[ToggleBind, object]] = [
            (self._current_bind(), lambda: idle_add(self.toggle)),
        ]
        trans = self._translate_bind()
        if trans is not None and not binds_conflict(trans, self._current_bind()):
            pairs.append((trans, lambda: idle_add(self.toggle_translate)))
        return pairs

    def _restart_hotkey(self) -> None:
        pairs = self._hotkey_pairs()
        hk = self._hotkey
        if hk is not None and getattr(hk, "can_replace", None) and hk.can_replace(pairs):
            hk.replace_binds(pairs)
            return
        self._pause_hotkeys()
        self._hotkey = HotkeyWatcher(
            binds=pairs,
            overlay_xid_fn=self._overlay_xid,
        )
        self._hotkey.start()
        timeout_add(250, self._report_hotkey)

    def _begin_rebind(self) -> bool:
        return self._begin_rebind_target("transcribe")

    def _begin_translate_rebind(self) -> bool:
        return self._begin_rebind_target("translate")

    def _begin_rebind_target(self, target: str) -> bool:
        self._rebind_gen += 1
        gen = self._rebind_gen
        self._rebinding = True
        self._rebind_target = target
        self._rebind_overlay_only = not self.overlay.visible
        self.overlay.set_hint("нажмите кнопку")
        if not self.overlay.visible:
            self.overlay.show_listening("нажмите кнопку")
        self._pause_hotkeys()
        timeout_add(250, lambda g=gen: self._arm_rebind_capture(g))
        return False

    def _arm_rebind_capture(self, gen: int) -> bool:
        if not self._rebinding or gen != self._rebind_gen:
            return False
        capture_bind(
            lambda bind, g=gen: idle_add(self._finish_rebind, bind, g),
            overlay_xid=self._overlay_xid(),
        )
        return False

    def _finish_rebind(self, bind: ToggleBind | None, gen: int | None = None) -> bool:
        if gen is not None and gen != self._rebind_gen:
            return False
        self._rebinding = False
        overlay_only = self._rebind_overlay_only
        self._rebind_overlay_only = False
        if bind is None:
            self._restart_hotkey()
            self._restore_status_hint()
            if overlay_only and not self.session.listening:
                self.overlay.hide()
            return False
        other = self._translate_bind() if self._rebind_target == "transcribe" else self._current_bind()
        if binds_conflict(bind, other):
            self._restart_hotkey()
            self.overlay.set_hint("кнопка уже занята")
            timeout_add(1800, self._clear_busy_bind_hint)
            return False
        if self._rebind_target == "translate":
            self.config = patch_config(
                translate_hotkey_kind=bind.kind,
                translate_hotkey_keycode=bind.code,
            )
        else:
            self.config = patch_config(
                hotkey_kind=bind.kind,
                hotkey_keycode=bind.code,
            )
        log.info("кнопка %s: %s %s", self._rebind_target, bind.kind, bind.code)
        self._restart_hotkey()
        self._restore_status_hint()
        if overlay_only and not self.session.listening:
            timeout_add(700, self._hide_rebind_overlay)
        return False

    def _hide_rebind_overlay(self) -> bool:
        if not self.session.listening and not self._rebinding:
            self.overlay.hide()
        return False

    def _clear_busy_bind_hint(self) -> bool:
        self._restore_status_hint()
        return False

    def _restore_status_hint(self) -> None:
        if self.overlay.mic_missing:
            self.overlay.set_hint(NO_MIC_HINT)
            return
        self.overlay.set_hint("")

    def _reload_config(self, microphone: str | None = None) -> bool:
        previous = self._current_bind()
        previous_tr = self._translate_bind()
        self.config = load_config()
        if microphone is not None:
            wanted = str(microphone)
            if (self.config.microphone or "") != wanted:
                self.config = patch_config(microphone=wanted)
        nxt = self._current_bind()
        nxt_tr = self._translate_bind()
        if nxt != previous or nxt_tr != previous_tr:
            self._restart_hotkey()
        if self.session.listening and not self._stopping:
            try:
                self._start_capture()
                self._mark_live()
            except Exception as exc:
                log.exception("не удалось переключить микрофон")
                hint = mic_open_hint(exc)
                self._surface_mic_error(hint, missing=hint == NO_MIC_HINT)
        return False

    def _on_ipc(self, command: str) -> str:
        cmd = command.strip().lower()
        if cmd == "toggle":
            idle_add(self.toggle)
            return "ok"
        if cmd == "start":
            idle_add(self.start_listen)
            return "ok"
        if cmd == "stop":
            idle_add(self.stop_listen)
            return "ok"
        if cmd == "reload":
            idle_add(self._reload_config)
            return "ok"
        if cmd == "rebind":
            idle_add(self._begin_rebind)
            return "ok"
        if cmd in {"rebind-translate", "rebind_translate"}:
            idle_add(self._begin_translate_rebind)
            return "ok"
        if cmd == "settings":
            idle_add(self._open_settings)
            return "ok"
        if cmd in {"status"}:
            return "listening" if self.session.listening else "idle"
        if cmd in {"quit", "exit"}:
            idle_add(self.quit)
            return "bye"
        return "unknown"


def run_daemon() -> None:
    try:
        from yo.logutil import setup_logging

        setup_logging()
        if sys.platform == "win32":
            from yo.ipc_win import claim_singleton, daemon_alive
            from yo.winapi import is_high_integrity, relaunch_medium_integrity, token_integrity_rid

            try:
                dropped = relaunch_medium_integrity(["daemon"])
            except Exception:
                log.exception("не удалось снять права администратора — продолжаю")
                dropped = False
            if dropped:
                log.info("Ёхо перезапущена без прав администратора — так вставка в другие окна работает")
                return
            log.info("целостность rid=%s high=%s", token_integrity_rid(), is_high_integrity())
            if daemon_alive():
                log.info("Ёхо уже запущена")
                print("Ёхо уже запущена")
                return
            if not claim_singleton():
                log.info("Ёхо уже запускается")
                for _ in range(20):
                    time.sleep(0.15)
                    if daemon_alive():
                        print("Ёхо уже запущена")
                        return
                print("Ёхо уже запущена")
                return
        loop_init()
        app = YoApp()
        app.start_background()
        log.info("Ёхо запущена")
        loop_main()
    except Exception:
        log.exception("демон Ёхо упал")
        raise
