import unittest
from pathlib import Path

from yo.paths import project_root
from yo.phrases import LISTEN, SPEAK_NOW, WAIT, phrase_for, wave_allowed


class PhraseTests(unittest.TestCase):
    def test_before_capture_is_wait(self):
        self.assertEqual(phrase_for(live=False, now=1.0, live_since=None), WAIT)
        self.assertEqual(WAIT, "Жду")

    def test_capture_start_flashes_speak_now(self):
        self.assertEqual(phrase_for(live=True, now=10.0, live_since=10.0), SPEAK_NOW)
        self.assertEqual(phrase_for(live=True, now=10.9, live_since=10.0), SPEAK_NOW)
        self.assertEqual(SPEAK_NOW, "Можно говорить")

    def test_after_one_second_is_listening(self):
        self.assertEqual(phrase_for(live=True, now=11.0, live_since=10.0), LISTEN)
        self.assertEqual(LISTEN, "Слушаю")

    def test_stop_returns_to_wait(self):
        self.assertEqual(phrase_for(live=False, now=20.0, live_since=10.0), WAIT)

    def test_govoryu_is_not_a_phrase(self):
        from yo.phrases import TRANSLATE

        self.assertNotIn("Говорю", {WAIT, SPEAK_NOW, LISTEN, TRANSLATE})


class WaveGateTests(unittest.TestCase):
    def test_wave_only_when_live_and_clear(self):
        self.assertFalse(wave_allowed(live=False, hint="", mic_missing=False))
        self.assertFalse(wave_allowed(live=True, hint="подключите микрофон", mic_missing=False))
        self.assertFalse(wave_allowed(live=True, hint="", mic_missing=True))
        self.assertTrue(wave_allowed(live=True, hint="", mic_missing=False))

    def test_wait_never_shares_a_moving_wave(self):
        label = phrase_for(live=False, now=0.0, live_since=None)
        self.assertEqual(label, WAIT)
        self.assertFalse(wave_allowed(live=False, hint="", mic_missing=False))


class AppWiringTests(unittest.TestCase):
    def test_app_does_not_publish_govoryu(self):
        src = (project_root() / "yo" / "app.py").read_text(encoding="utf-8")
        self.assertNotIn('"говорю"', src)
        self.assertNotIn("'говорю'", src)
        self.assertIn("set_live(True)", src)
        self.assertIn("SpeechGate", src)
