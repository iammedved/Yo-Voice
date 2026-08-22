import unittest

import numpy as np

from yo.asr import TRANSCRIBE_OPTIONS, AsrEngine, prepare_pcm


class FakeSegments:
    def __init__(self, text: str):
        self.text = text


class FakeModel:
    def __init__(self):
        self.kwargs = None
        self.calls = 0

    def transcribe(self, pcm, **kwargs):
        self.calls += 1
        self.kwargs = kwargs
        self.pcm = pcm
        return iter([FakeSegments("проверка")]), None


class KeepSegmentTests(unittest.TestCase):
    def test_keeps_normal_text(self):
        from types import SimpleNamespace
        from yo.asr import keep_segment

        seg = SimpleNamespace(text="привет мир", no_speech_prob=0.1, avg_logprob=-0.2, compression_ratio=1.1)
        self.assertTrue(keep_segment(seg))

    def test_drops_no_speech_hallucination(self):
        from types import SimpleNamespace
        from yo.asr import keep_segment

        seg = SimpleNamespace(text="спасибо", no_speech_prob=0.92, avg_logprob=-1.4, compression_ratio=1.0)
        self.assertFalse(keep_segment(seg))

    def test_drops_repetitive_compression(self):
        from types import SimpleNamespace
        from yo.asr import keep_segment

        seg = SimpleNamespace(text="а а а а", no_speech_prob=0.2, avg_logprob=-0.3, compression_ratio=3.1)
        self.assertFalse(keep_segment(seg))


class TranscribeOptionsTests(unittest.TestCase):
    def test_does_not_feed_prompt_as_previous_context(self):
        self.assertFalse(TRANSCRIBE_OPTIONS["condition_on_previous_text"])
        self.assertIsNone(TRANSCRIBE_OPTIONS.get("initial_prompt"))
        self.assertGreaterEqual(TRANSCRIBE_OPTIONS["beam_size"], 3)
        self.assertGreaterEqual(TRANSCRIBE_OPTIONS["no_speech_threshold"], 0.5)

    def test_engine_passes_isolated_context(self):
        engine = AsrEngine()
        engine.model = FakeModel()
        engine.device = "cpu"
        audio = (0.04 * np.sin(np.linspace(0, 40, 16000))).astype(np.float32)
        engine.transcribe(audio, 16000)
        kwargs = engine.model.kwargs
        self.assertFalse(kwargs["condition_on_previous_text"])
        self.assertFalse(kwargs.get("initial_prompt"))
        self.assertGreaterEqual(kwargs["beam_size"], 3)

    def test_silence_is_not_sent_to_model(self):
        engine = AsrEngine()
        engine.model = FakeModel()
        silence = (0.0002 * np.random.randn(16000)).astype(np.float32)
        self.assertEqual(engine.transcribe(silence, 16000), "")
        self.assertEqual(engine.model.calls, 0)


class PreparePcmTests(unittest.TestCase):
    def test_true_silence_is_dropped(self):
        silence = (0.0003 * np.ones(16000, dtype=np.float32))
        self.assertIsNone(prepare_pcm(silence, 16000))

    def test_quiet_speech_is_boosted_not_left_inaudible(self):
        quiet = (0.008 * np.sin(np.linspace(0, 80, 16000))).astype(np.float32)
        out = prepare_pcm(quiet, 16000)
        self.assertIsNotNone(out)
        self.assertGreater(float(np.sqrt(np.mean(out**2))), 0.02)

    def test_very_quiet_speech_is_boosted_for_whisper(self):
        quiet = (0.0025 * np.sin(np.linspace(0, 80, 16000))).astype(np.float32)
        out = prepare_pcm(quiet, 16000)
        self.assertIsNotNone(out)
        self.assertGreater(float(np.sqrt(np.mean(out**2))), 0.03)

    def test_already_loud_speech_is_not_clipped_into_noise(self):
        loud = (0.3 * np.sin(np.linspace(0, 80, 16000))).astype(np.float32)
        out = prepare_pcm(loud, 16000)
        self.assertLess(float(np.max(np.abs(out))), 1.0)
        self.assertGreater(float(np.sqrt(np.mean(out**2))), 0.15)
