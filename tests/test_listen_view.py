import unittest
from pathlib import Path

from yo.capture import NO_MIC_HINT, dead_stream_plan, presence_poll_plan
from yo.phrases import LISTEN, UNRECOGNIZED, display_label, phrase_for, wave_allowed


class MissingMicLabelTests(unittest.TestCase):
    def test_missing_mic_is_only_plug_hint_even_if_live(self):
        label = display_label(
            live=True,
            now=20.0,
            live_since=1.0,
            mic_missing=True,
        )
        self.assertEqual(label, NO_MIC_HINT)
        self.assertEqual(label, "подключите микрофон")
        self.assertNotEqual(label, LISTEN)
        self.assertFalse(wave_allowed(live=True, hint="", mic_missing=True))

    def test_captured_mic_can_say_listening(self):
        label = display_label(
            live=True,
            now=12.0,
            live_since=10.0,
            mic_missing=False,
        )
        self.assertEqual(label, LISTEN)
        self.assertTrue(wave_allowed(live=True, hint="", mic_missing=False))

    def test_unrecognized_speech_is_shown(self):
        label = display_label(
            live=True,
            now=12.0,
            live_since=10.0,
            mic_missing=False,
            status=UNRECOGNIZED,
        )
        self.assertEqual(label, "не разобрал")


class PresenceStabilityTests(unittest.TestCase):
    def test_quiet_stream_does_not_pretend_unplug_when_device_exists(self):
        plan = dead_stream_plan(True)
        self.assertFalse(plan["mic_missing"])
        self.assertIsNone(plan["live"])
        self.assertFalse(plan["stop_capture"])

    def test_unplugged_inventory_stays_on_missing_mic(self):
        plan = dead_stream_plan(False)
        self.assertTrue(plan["mic_missing"])
        self.assertFalse(plan["live"])
        self.assertTrue(plan["stop_capture"])
        poll = presence_poll_plan(False, was_missing=False)
        self.assertTrue(poll["mic_missing"])
        self.assertFalse(poll["live"])
        self.assertFalse(poll["start_capture"])
        self.assertTrue(poll["stop_capture"])
        label = display_label(live=bool(poll["live"]), now=1.0, live_since=None, mic_missing=True)
        self.assertEqual(label, NO_MIC_HINT)
        self.assertNotEqual(label, LISTEN)
        self.assertNotEqual(phrase_for(live=False, now=1.0, live_since=None), LISTEN)

    def test_replug_may_restart_capture_but_silence_does_not_flip(self):
        recovered = presence_poll_plan(True, was_missing=True)
        self.assertFalse(recovered["mic_missing"])
        self.assertTrue(recovered["start_capture"])
        self.assertFalse(recovered["stop_capture"])
        still_there = presence_poll_plan(True, was_missing=False)
        self.assertFalse(still_there["start_capture"])
        quiet = dead_stream_plan(True)
        self.assertFalse(quiet["mic_missing"])
        self.assertNotEqual(quiet.get("live"), False)

    def test_app_dead_stream_uses_inventory_plan(self):
        src = Path(__file__).resolve().parents[1].joinpath("yo", "app.py").read_text(encoding="utf-8")
        start = src.index("def _check_dead_stream")
        body = src[start : src.index("def _report_hotkey")]
        self.assertIn("dead_stream_plan", body)
        self.assertIn("stream_looks_dead", body)
        self.assertLess(body.index("dead_stream_plan"), body.index("set_mic_missing"))
        silent_branch = body[body.index('if plan["mic_missing"]') :]
        self.assertNotIn("_surface_mic_error", silent_branch)
        self.assertNotIn("MIC_SILENT_HINT", silent_branch)

    def test_go_live_clears_hint_and_does_not_block_ui(self):
        src = Path(__file__).resolve().parents[1].joinpath("yo", "app.py").read_text(encoding="utf-8")
        go = src[src.index("def _go_live") : src.index("def _start_capture")]
        self.assertIn("_start_capture", go)
        self.assertNotIn("Thread", go)
        self.assertNotIn("_capture_then_live", go)
        self.assertIn('set_hint("")', go)
        self.assertIn("set_live(True)", go)
        start = src[src.index("def start_listen") : src.index("def stop_listen")]
        self.assertLess(start.index("set_task"), start.index("show_listening"))
        self.assertLess(start.index("show_listening"), start.index("_go_live"))
        self.assertIn("set_live(True)", start)
        self.assertIn("timeout_add(0, self._go_live)", start)

    def test_reload_opens_the_selected_microphone(self):
        src = Path(__file__).resolve().parents[1].joinpath("yo", "app.py").read_text(encoding="utf-8")
        body = src[src.index("def _reload_config") : src.index("def _on_ipc")]
        self.assertIn("_start_capture", body)
        self.assertIn("mic_open_hint", body)
        self.assertNotIn("not self.overlay.mic_missing", body)
        self.assertIn("microphone", body)
        open_settings = src[src.index("def _open_settings") : src.index("def _overlay_xid")]
        self.assertIn("idle_add(self._reload_config", open_settings)
