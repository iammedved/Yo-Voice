import math
import unittest

import numpy as np

from yo.vad import END_MS, FRAME, SILERO_START, SpeechGate, boost_for_vad, trim_to_speech


def _sine(seconds: float, freq: float = 180.0, amp: float = 0.2, sr: int = 16000) -> np.ndarray:
    t = np.arange(int(sr * seconds), dtype=np.float32) / sr
    return (amp * np.sin(2 * math.pi * freq * t)).astype(np.float32)


class SpeechGateTests(unittest.TestCase):
    def test_silence_never_starts(self):
        gate = SpeechGate(backend="energy")
        silence = np.zeros(512, dtype=np.float32)
        events = [gate.process(silence, 16000) for _ in range(40)]
        self.assertNotIn("start", events)
        self.assertFalse(gate.speaking)

    def test_voiced_sine_starts_and_ends(self):
        gate = SpeechGate(backend="energy")
        voiced = _sine(0.032)
        events = [gate.process(voiced, 16000) for _ in range(8)]
        self.assertIn("start", events)
        self.assertTrue(gate.speaking)
        silence = np.zeros(512, dtype=np.float32)
        events = [gate.process(silence, 16000) for _ in range(45)]
        self.assertIn("end", events)
        self.assertFalse(gate.speaking)


class AutoBackendTests(unittest.TestCase):
    def test_auto_backend_still_drops_silence(self):
        gate = SpeechGate()
        silence = np.zeros(512, dtype=np.float32)
        events = [gate.process(silence, 16000) for _ in range(40)]
        self.assertNotIn("start", events)
        self.assertIsNone(trim_to_speech(np.zeros(16000, dtype=np.float32), 16000))

    def test_quiet_voiced_speech_starts(self):
        self.assertLessEqual(SILERO_START, 0.30)
        gate = SpeechGate()
        quiet = _sine(0.032, amp=0.002)
        events = [gate.process(quiet, 16000) for _ in range(16)]
        self.assertIn("start", events)
        self.assertTrue(gate.speaking)


class SileroGateTests(unittest.TestCase):
    def _gate(self) -> SpeechGate:
        gate = SpeechGate()
        if gate._backend != "silero":
            self.skipTest("silero onnx недоступен")
        return gate

    def test_click_does_not_hold_the_endpoint(self):
        gate = self._gate()
        gate._silero.prob = lambda frame: 0.9
        gate.process(_sine(0.032, amp=0.2), 16000)
        gate.process(_sine(0.032, amp=0.2), 16000)
        self.assertTrue(gate.speaking)
        gate._silero.prob = lambda frame: 0.0
        spike = np.full(FRAME, 0.002, dtype=np.float32)
        quiet = np.full(FRAME, 1.5e-5, dtype=np.float32)
        hop = int(0.8 / (FRAME / 16000))
        ends = []
        for i in range(int(3.0 / (FRAME / 16000))):
            event = gate.process(spike if i % hop == 0 else quiet, 16000)
            if event == "end":
                ends.append(i)
        self.assertTrue(ends)
        self.assertFalse(gate.speaking)
        self.assertLess(ends[0] * FRAME / 16000, END_MS / 1000.0 + 0.5)

    def test_sustained_energy_still_starts_without_silero(self):
        gate = self._gate()
        gate._silero.prob = lambda frame: 0.0
        whisper = np.full(FRAME, 0.002, dtype=np.float32)
        events = [gate.process(whisper, 16000) for _ in range(12)]
        self.assertIn("start", events)
        self.assertTrue(gate.speaking)

    def test_one_energy_spike_does_not_start(self):
        gate = self._gate()
        gate._silero.prob = lambda frame: 0.0
        spike = np.full(FRAME, 0.002, dtype=np.float32)
        self.assertNotEqual(gate.process(spike, 16000), "start")
        self.assertFalse(gate.speaking)

    def test_end_inside_block_is_not_dropped(self):
        gate = self._gate()
        gate.speaking = True
        gate._silence_ms = END_MS - 10
        gate._silero.prob = lambda frame: 0.0
        event = gate.process(np.zeros(FRAME * 3, dtype=np.float32), 16000)
        self.assertEqual(event, "end")
        self.assertFalse(gate.speaking)

    def test_end_then_speech_in_one_block_still_returns_end(self):
        gate = self._gate()
        gate.speaking = True
        gate._silence_ms = END_MS - 10
        calls = {"n": 0}

        def prob(frame):
            calls["n"] += 1
            return 0.0 if calls["n"] == 1 else 0.95

        gate._silero.prob = prob
        event = gate.process(np.zeros(FRAME * 3, dtype=np.float32), 16000)
        self.assertEqual(event, "end")


class TrimToSpeechTests(unittest.TestCase):
    def test_pure_silence_is_not_sent(self):
        silence = np.zeros(16000, dtype=np.float32)
        self.assertIsNone(trim_to_speech(silence, 16000, backend="energy"))

    def test_speech_surrounded_by_silence_is_kept(self):
        clip = np.concatenate(
            [
                np.zeros(8000, dtype=np.float32),
                _sine(0.6),
                np.zeros(8000, dtype=np.float32),
            ]
        )
        kept = trim_to_speech(clip, 16000, backend="energy")
        self.assertIsNotNone(kept)
        self.assertGreater(len(kept), 16000 * 0.3)
        self.assertLess(len(kept), len(clip))

    def test_quiet_tail_is_kept_with_pad(self):
        clip = np.concatenate(
            [
                _sine(0.5, amp=0.2),
                _sine(0.3, amp=0.0004),
            ]
        )
        tight = trim_to_speech(clip, 16000, backend="energy", pad_ms=0)
        padded = trim_to_speech(clip, 16000, backend="energy", pad_ms=400)
        self.assertIsNotNone(tight)
        self.assertIsNotNone(padded)
        self.assertGreater(len(padded), len(tight))
        defaulted = trim_to_speech(clip, 16000, backend="energy")
        self.assertGreaterEqual(len(defaulted), len(padded) - 512)

    def test_whisper_level_speech_is_kept(self):
        clip = _sine(0.8, amp=0.0012)
        kept = trim_to_speech(clip, 16000, backend="energy")
        self.assertIsNotNone(kept)
        self.assertGreater(len(kept), 16000 * 0.4)

    def test_boost_raises_quiet_speech_without_touching_loud(self):
        quiet = _sine(0.032, amp=0.002)
        loud = _sine(0.032, amp=0.08)
        boosted = boost_for_vad(quiet)
        self.assertGreater(float(np.sqrt(np.mean(boosted**2))), float(np.sqrt(np.mean(quiet**2))) * 5)
        same = boost_for_vad(loud)
        self.assertLess(abs(float(np.max(np.abs(same))) - float(np.max(np.abs(loud)))), 0.02)

    def test_click_islands_do_not_keep_the_hole(self):
        click = np.full(FRAME, 0.05, dtype=np.float32)
        silence = np.zeros(40 * FRAME, dtype=np.float32)
        speech = _sine(8 * FRAME / 16000, amp=0.2)
        clip = np.concatenate([click, silence, speech, silence, click])
        kept = trim_to_speech(clip, 16000, backend="energy", pad_ms=0)
        self.assertIsNotNone(kept)
        self.assertEqual(len(kept), len(speech))

    def test_short_gap_stays_one_phrase(self):
        speech = _sine(8 * FRAME / 16000, amp=0.2)
        gap = np.zeros(3 * FRAME, dtype=np.float32)
        clip = np.concatenate([speech, gap, speech])
        kept = trim_to_speech(clip, 16000, backend="energy", pad_ms=0)
        self.assertIsNotNone(kept)
        self.assertEqual(len(kept), len(clip))

    def test_long_gap_is_not_spanned(self):
        speech = _sine(8 * FRAME / 16000, amp=0.2)
        hole = np.zeros(40 * FRAME, dtype=np.float32)
        clip = np.concatenate([speech, hole, speech])
        kept = trim_to_speech(clip, 16000, backend="energy", pad_ms=0)
        self.assertIsNotNone(kept)
        self.assertGreater(len(kept), len(speech) * 2)
        self.assertLess(len(kept), len(speech) * 2 + 16000)

    def test_minute_between_clicks_is_not_sent(self):
        click = np.full(FRAME, 0.05, dtype=np.float32)
        minute = np.zeros((16000 * 30 // FRAME) * FRAME, dtype=np.float32)
        speech = _sine(8 * FRAME / 16000, amp=0.2)
        clip = np.concatenate([click, minute, speech, minute, click])
        kept = trim_to_speech(clip, 16000, backend="energy")
        self.assertIsNotNone(kept)
        self.assertLess(len(kept), 16000 * 2)

    def test_finalize_does_not_energy_trim(self):
        from yo.paths import project_root

        src = (project_root() / "yo" / "app.py").read_text(encoding="utf-8")
        body = src[src.index("def _finalize") : src.index("def _finalize_failed")]
        self.assertNotIn('backend="energy"', body)
        self.assertIn("trim_to_speech", body)
