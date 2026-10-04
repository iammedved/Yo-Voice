"""YoApp start/stop flow on a virtual clock: no microphone, model or display."""

import heapq
import itertools
import unittest
from unittest import mock

import numpy as np

try:
    from yo import app as app_mod
except Exception as exc:  # pragma: no cover - GTK / Xlib / Tk missing
    app_mod = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


class FakeLoop:
    def __init__(self) -> None:
        self.now = 0
        self._heap: list = []
        self._seq = itertools.count()
        self._dead: set[int] = set()

    def timeout_add(self, ms, fn, *args):
        sid = next(self._seq)
        heapq.heappush(self._heap, (self.now + int(ms), sid, int(ms), fn, args))
        return sid

    def idle_add(self, fn, *args):
        return self.timeout_add(0, fn, *args)

    def source_remove(self, sid):
        if sid is not None:
            self._dead.add(sid)

    def advance(self, ms: int) -> None:
        end = self.now + int(ms)
        while self._heap and self._heap[0][0] <= end:
            when, sid, ms, fn, args = heapq.heappop(self._heap)
            self.now = when
            if sid in self._dead:
                continue
            if fn(*args):  # GLib: a true return repeats the timer
                heapq.heappush(self._heap, (when + max(1, ms), sid, ms, fn, args))
        self.now = end


class FakeOverlay:
    def __init__(self, **_kw) -> None:
        self.visible = False
        self.live = False
        self.live_since = None
        self.status = ""
        self.hint = ""
        self.mic_missing = False
        self.preview = ""
        self.task = "transcribe"
        self.window = None

    def native_id(self):
        return None

    def show_listening(self, status=""):
        self.status = status
        self.visible = True

    def hide(self):
        self.visible = False
        self.live = False
        self.status = ""

    def set_task(self, task):
        self.task = task

    def set_status(self, status):
        self.status = status

    def set_live(self, live):
        self.live = bool(live)

    def set_preview(self, text):
        self.preview = text

    def set_mic_missing(self, missing):
        self.mic_missing = bool(missing)

    def set_hint(self, text):
        self.hint = text

    def set_levels(self, *_a):
        pass


class FakeEngine:
    def __init__(self, *_a, **_kw) -> None:
        self.text = "привет мир"

    def loaded(self):
        return True

    def load(self, *_a):
        pass

    def transcribe(self, *_a, **_kw):
        return self.text


class FakeAudio:
    def __init__(self, on_block, sample_rate=16000) -> None:
        self.on_block = on_block
        self.peak_level = 0.1
        self.running = False

    def start(self, device=None, *, exclusive=False):
        self.running = True

    def stop(self, *, drain=True):
        self.running = False


class FakeInjector:
    def __init__(self) -> None:
        self.pastes: list[str] = []
        self.clip = None

    def paste(self, hwnd=None, overlay_hwnd=None):
        self.pastes.append(self.clip())


def _speech() -> np.ndarray:
    t = np.arange(16000) / 16000.0
    return (0.05 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


@unittest.skipIf(app_mod is None, f"yo.app needs the desktop stack: {_IMPORT_ERROR}")
class AppFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.loop = FakeLoop()
        self.clipboard = {"text": "ORIGINAL"}
        self.injector = FakeInjector()
        self.injector.clip = lambda: self.clipboard["text"]
        patches = {
            "Overlay": FakeOverlay,
            "AsrEngine": FakeEngine,
            "LocalTranslator": lambda *_a, **_kw: mock.Mock(),
            "Injector": lambda: self.injector,
            "AudioCapture": FakeAudio,
            "SpeechGate": lambda *_a, **_kw: mock.Mock(process=lambda *_x: "silence"),
            "timeout_add": self.loop.timeout_add,
            "idle_add": self.loop.idle_add,
            "source_remove": self.loop.source_remove,
            "clipboard_get": lambda: self.clipboard["text"],
            "clipboard_set": lambda text: self.clipboard.__setitem__("text", text),
            "has_microphone": lambda: True,
            "microphone_permission_denied": lambda: False,
            "capture_candidate_indices": lambda *_a, **_kw: [0],
            "portaudio_name_at": lambda *_a, **_kw: "mic",
            "patch_config": lambda **_kw: self.app.config,
            "trim_to_speech": lambda audio, *_a, **_kw: audio,
            "load_config": lambda: app_mod.Config(),
        }
        for name, value in patches.items():
            p = mock.patch.object(app_mod, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(app_mod.sys, "platform", "linux")
        p.start()
        self.addCleanup(p.stop)
        self.app = app_mod.YoApp(config=app_mod.Config())
        # Run recognition jobs inline so the test owns the order of events.
        self.app._jobs.put(None)
        self.app._worker.join(timeout=2)

    def press(self) -> None:
        self.app.toggle()

    def speak(self) -> None:
        with self.app._chunks_lock:
            self.app._chunks.append(_speech())

    def run_jobs(self) -> None:
        while not self.app._jobs.empty():
            item = self.app._jobs.get_nowait()
            if item is not None:
                self.app._finalize(*item)

    def stop_and_recognize(self) -> None:
        self.press()
        self.loop.advance(app_mod.STOP_TAIL_MS)
        self.run_jobs()

    def test_press_while_last_phrase_is_recognized_starts_next_session(self):
        self.press()
        self.loop.advance(10)
        self.speak()
        self.press()  # stop
        token = self.app._token
        self.loop.advance(100)
        self.press()  # pressed again before the last phrase is pasted
        self.loop.advance(app_mod.STOP_TAIL_MS)
        self.run_jobs()
        self.loop.advance(2000)
        self.assertEqual(self.injector.pastes, ["Привет мир."])
        self.assertTrue(self.app.session.listening, "second press was dropped")
        self.assertEqual(self.app._token, token + 1)
        self.assertTrue(self.app.overlay.visible)

    def test_old_hide_timer_does_not_hide_a_new_session(self):
        self.app.engine.text = ""
        self.press()
        self.loop.advance(10)
        self.speak()
        self.stop_and_recognize()  # nothing recognized: hide in 900 ms
        self.loop.advance(300)
        self.press()  # start again
        self.loop.advance(2000)
        self.assertTrue(self.app.session.listening)
        self.assertTrue(self.app.overlay.visible, "stale hide timer hid the cat")

    def test_failed_text_cleanup_does_not_leave_session_stuck(self):
        self.press()
        self.loop.advance(10)
        self.speak()
        with mock.patch.object(self.app.session, "commit_utterance", side_effect=ValueError("boom")):
            with mock.patch.object(self.app, "_show_defect"):
                self.stop_and_recognize()
                self.loop.advance(2000)
        self.assertFalse(self.app.session.listening)
        self.assertFalse(self.app._stopping)
        self.press()
        self.assertTrue(self.app.session.listening, "hotkey ignored after a failed commit")

    def test_quick_restart_keeps_the_users_clipboard(self):
        self.press()
        self.loop.advance(10)
        self.speak()
        self.stop_and_recognize()
        self.loop.advance(250)  # cat hidden, clipboard restore still pending
        self.press()
        self.loop.advance(10)
        self.speak()
        self.stop_and_recognize()
        self.loop.advance(2000)
        self.assertEqual(self.injector.pastes, ["Привет мир.", "Привет мир."])
        self.assertEqual(self.clipboard["text"], "ORIGINAL")


if __name__ == "__main__":
    unittest.main()
