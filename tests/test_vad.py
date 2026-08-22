import math
import unittest

import numpy as np

from yo.vad import SpeechGate, trim_to_speech


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
