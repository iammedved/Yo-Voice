import unittest

import numpy as np

from yo.asr import (
    DEFAULT_MODEL,
    TRANSCRIBE_OPTIONS,
    AsrEngine,
    prepare_pcm,
    resolve_asr_model,
    resolve_whisper_path,
    whisper_compute_type,
)


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

    def test_keeps_thanks_when_model_is_confident(self):
        from types import SimpleNamespace
        from yo.asr import keep_segment

        seg = SimpleNamespace(text="спасибо", no_speech_prob=0.1, avg_logprob=-0.2, compression_ratio=1.1)
        self.assertTrue(keep_segment(seg))


class TranscribeOptionsTests(unittest.TestCase):
    def test_does_not_feed_prompt_as_previous_context(self):
        self.assertFalse(TRANSCRIBE_OPTIONS["condition_on_previous_text"])
        self.assertIsNone(TRANSCRIBE_OPTIONS.get("initial_prompt"))
        self.assertTrue(TRANSCRIBE_OPTIONS["without_timestamps"])
        self.assertEqual(TRANSCRIBE_OPTIONS["temperature"], 0.0)
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
        self.assertFalse(kwargs.get("hotwords"))
        self.assertTrue(kwargs["without_timestamps"])
        self.assertEqual(kwargs["temperature"], 0.0)
        self.assertGreaterEqual(kwargs["beam_size"], 3)

    def test_silence_is_not_sent_to_model(self):
        engine = AsrEngine()
        engine.model = FakeModel()
        silence = (0.00008 * np.random.randn(16000)).astype(np.float32)
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

    def test_whisper_level_speech_is_kept_and_boosted(self):
        quiet = (0.0008 * np.sin(np.linspace(0, 80, 16000))).astype(np.float32)
        out = prepare_pcm(quiet, 16000)
        self.assertIsNotNone(out)
        self.assertGreater(float(np.sqrt(np.mean(out**2))), 0.02)

    def test_already_loud_speech_is_not_clipped_into_noise(self):
        loud = (0.3 * np.sin(np.linspace(0, 80, 16000))).astype(np.float32)
        out = prepare_pcm(loud, 16000)
        self.assertLess(float(np.max(np.abs(out))), 1.0)
        self.assertGreater(float(np.sqrt(np.mean(out**2))), 0.15)


class RussianTurboModelTests(unittest.TestCase):
    def test_default_and_legacy_turbo_resolve_to_russian_ct2(self):
        self.assertEqual(DEFAULT_MODEL, "coriollon/whisper-large-v3-turbo-russian")
        self.assertNotIn("codeswitch", DEFAULT_MODEL)
        self.assertEqual(resolve_asr_model("large-v3-turbo"), DEFAULT_MODEL)
        self.assertEqual(resolve_asr_model("coriollon/whisper-large-v3-turbo-russian"), DEFAULT_MODEL)
        self.assertEqual(resolve_asr_model(""), DEFAULT_MODEL)
        self.assertEqual(resolve_asr_model(DEFAULT_MODEL), DEFAULT_MODEL)
        self.assertNotIn("codeswitch", resolve_asr_model("coriollon/whisper-large-v3-turbo-russian"))
        self.assertEqual(
            resolve_asr_model("coriollon/whisper-large-v3-turbo-russian-codeswitch"),
            "coriollon/whisper-large-v3-turbo-russian-codeswitch",
        )
        self.assertEqual(
            resolve_asr_model("Systran/faster-whisper-large-v3-turbo"),
            "Systran/faster-whisper-large-v3-turbo",
        )

    def test_russian_weights_use_local_ct2_subdir(self):
        seen = {}

        def fake_download(*, repo_id, allow_patterns):
            seen["repo_id"] = repo_id
            seen["allow_patterns"] = allow_patterns
            return "/tmp/yo-ru-turbo"

        path = resolve_whisper_path("large-v3-turbo", download=fake_download)
        self.assertEqual(seen["repo_id"], DEFAULT_MODEL)
        self.assertTrue(any("ct2_int8_float16" in item for item in seen["allow_patterns"]))
        self.assertTrue(path.endswith("ct2_int8_float16"))

    def test_compute_type_matches_quantized_ct2(self):
        self.assertEqual(whisper_compute_type("cuda", "large-v3-turbo"), "int8_float16")
        self.assertEqual(whisper_compute_type("cpu", DEFAULT_MODEL), "int8")
        self.assertEqual(whisper_compute_type("cuda", "Systran/faster-whisper-large-v3-turbo"), "float16")

    def test_sources_stay_off_cloud_speech_apis(self):
        from yo.paths import project_root

        root = project_root()
        haystack = "\n".join(
            (root / "yo" / name).read_text(encoding="utf-8")
            for name in ("app.py", "asr.py", "config.py")
        ).lower()
        self.assertNotIn("gemini", haystack)
        self.assertNotIn("generativelanguage", haystack)
        self.assertNotIn("speech.googleapis", haystack)
