import unittest

from yo.audio import STOP_TAIL_MS, drain_timeout_s, stream_looks_dead
from yo.paths import project_root


class DeadStreamTests(unittest.TestCase):
    def test_true_silence_after_a_second_is_dead(self):
        self.assertTrue(stream_looks_dead(peak_rms=0.0, elapsed_ms=1000))

    def test_quiet_speech_is_not_dead(self):
        self.assertFalse(stream_looks_dead(peak_rms=0.002, elapsed_ms=1000))

    def test_barracuda_idle_floor_is_not_dead(self):
        self.assertFalse(stream_looks_dead(peak_rms=1.51e-05, elapsed_ms=1000))
        self.assertTrue(stream_looks_dead(peak_rms=0.0, elapsed_ms=1000))

    def test_does_not_flag_before_window(self):
        self.assertFalse(stream_looks_dead(peak_rms=0.0, elapsed_ms=200))


class StopTailTests(unittest.TestCase):
    def test_tail_is_short_hang_not_another_vad_second(self):
        self.assertGreaterEqual(STOP_TAIL_MS, 200)
        self.assertLessEqual(STOP_TAIL_MS, 400)

    def test_drain_waits_about_one_block(self):
        wait = drain_timeout_s(100.0)
        self.assertGreaterEqual(wait, 0.12)
        self.assertLessEqual(wait, 0.25)

    def test_live_blocks_are_not_preamplified(self):
        src = (project_root() / "yo" / "audio.py").read_text(encoding="utf-8")
        callback = src[src.index("def _callback") :]
        self.assertNotIn("0.0008 < level < 0.04", callback)
        self.assertNotIn("0.04 / level", callback)

    def test_stop_listen_keeps_a_tail_then_drains(self):
        src = (project_root() / "yo" / "app.py").read_text(encoding="utf-8")
        stop = src[src.index("def stop_listen") : src.index("def quit")]
        self.assertIn("STOP_TAIL_MS", stop)
        self.assertIn("timeout_add", stop)
        self.assertNotIn("self.audio.stop()", stop)
        finish = src[src.index("def _finish_stop") : src.index("def _load_then_mic")]
        self.assertIn("drain", finish)
        self.assertIn("self.audio.stop", finish)
        on_block = src[src.index("def _on_block") : src.index("def _push_levels")]
        self.assertIn("_stopping", on_block)


class WasapiCapturePlanTests(unittest.TestCase):
    def test_skips_communications_16khz(self):
        from yo.audio import _wasapi_capture_rates

        self.assertEqual(_wasapi_capture_rates(16000), [48000, 44100])
        self.assertEqual(_wasapi_capture_rates(48000), [48000, 44100])
        self.assertEqual(_wasapi_capture_rates(44100), [44100, 48000])
        self.assertNotIn(16000, _wasapi_capture_rates(16000))

    def test_does_not_enable_autoconvertpcm(self):
        src = (project_root() / "yo" / "audio.py").read_text(encoding="utf-8")
        self.assertNotIn("auto_convert=True", src)
        self.assertIn("exclusive=True", src)
        self.assertIn("exclusive: bool = False", src)
        self.assertIn("_wasapi_capture_rates", src)
        self.assertIn("_probe_stream_silent", src)

    def test_wasapi_exclusive_is_last_after_shared_hosts(self):
        src = (project_root() / "yo" / "app.py").read_text(encoding="utf-8")
        body = src[src.index("def _start_capture") : src.index("def _sync_mic")]
        self.assertIn("exclusive_modes", body)
        self.assertIn("exclusive=exclusive", body)
        self.assertLess(body.index("exclusive_modes = [False]"), body.index("exclusive_modes.append(True)"))
