import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from yo import speaker as S
from yo.config import Config

SR = 16000


def _tone(seconds: float, freq: float, amp: float = 0.2) -> np.ndarray:
    t = np.arange(int(SR * seconds), dtype=np.float32) / SR
    return (amp * np.sin(2 * math.pi * freq * t)).astype(np.float32)


class FakeEncoder:
    """Low tone is "me", high tone is "someone else"; a mix is in between."""

    path = None

    def __init__(self) -> None:
        self.calls = 0

    def embed_many(self, clips):
        self.calls += 1
        out = []
        for clip in clips:
            spec = np.abs(np.fft.rfft(clip))
            freqs = np.fft.rfftfreq(len(clip), 1.0 / SR)
            low = float(np.sum(spec[freqs < 400] ** 2))
            high = float(np.sum(spec[freqs >= 400] ** 2))
            out.append(np.array([low, high, 0.0], dtype=np.float32))
        return np.stack(out)

    def embed(self, clip):
        return self.embed_many([clip])[0]


ME = np.array([1.0, 0.0, 0.0], dtype=np.float32)


class FbankTests(unittest.TestCase):
    def test_shape_and_mean_normalized(self):
        feats = S.fbank(_tone(1.0, 300))
        self.assertEqual(feats.shape, (98, 80))
        np.testing.assert_allclose(feats.mean(axis=0), 0.0, atol=1e-3)

    def test_too_short_is_empty(self):
        self.assertEqual(S.fbank(np.zeros(100, dtype=np.float32)).shape, (0, 80))

    def test_mic_gain_does_not_change_features(self):
        rng = np.random.default_rng(0)
        pcm = (0.05 * rng.standard_normal(SR)).astype(np.float32) + _tone(1.0, 300)
        np.testing.assert_allclose(S.fbank(pcm), S.fbank(pcm * 0.25), atol=1e-3)

    def test_mel_banks_cover_speech_band(self):
        self.assertEqual(S._BANKS.shape, (80, 257))
        self.assertTrue(np.all(S._BANKS.sum(axis=0)[3:255] > 0))


class CosineTests(unittest.TestCase):
    def test_values(self):
        self.assertAlmostEqual(S.cosine([1, 0], [2, 0]), 1.0)
        self.assertAlmostEqual(S.cosine([1, 0], [0, 3]), 0.0)
        self.assertEqual(S.cosine([0, 0], [1, 0]), 0.0)


class OwnVoiceOnlyTests(unittest.TestCase):
    def test_my_phrase_passes_whole(self):
        pcm = _tone(3.0, 150)
        kept, scores = S.own_voice_only(pcm, ME, FakeEncoder())
        self.assertIs(kept, pcm)
        self.assertTrue(scores and min(scores) > 0.9)

    def test_other_voice_is_dropped(self):
        kept, scores = S.own_voice_only(_tone(3.0, 1200), ME, FakeEncoder())
        self.assertIsNone(kept)
        self.assertTrue(max(scores) < 0.1)

    def test_short_phrase_is_scored_whole(self):
        enc = FakeEncoder()
        kept, scores = S.own_voice_only(_tone(1.2, 1200), ME, enc)
        self.assertIsNone(kept)
        self.assertEqual(len(scores), 1)

    def test_very_short_phrase_cannot_bypass_identity(self):
        pcm = _tone(0.3, 1200)
        kept, scores = S.own_voice_only(pcm, ME, FakeEncoder())
        self.assertIsNone(kept)
        self.assertEqual(scores, [])

    def test_other_voice_is_cut_out_of_a_mixed_phrase(self):
        mine, other = _tone(3.0, 150), _tone(3.0, 1200)
        pcm = np.concatenate([mine, other, mine])
        kept, _scores = S.own_voice_only(pcm, ME, FakeEncoder())
        self.assertIsNotNone(kept)
        # About 6 s of mine plus a short join; most of the 3 s of the other is gone.
        self.assertGreater(len(kept), 5.0 * SR)
        self.assertLess(len(kept), 7.0 * SR)
        spec = np.abs(np.fft.rfft(kept))
        freqs = np.fft.rfftfreq(len(kept), 1.0 / SR)
        self.assertGreater(spec[freqs < 400].sum(), 3 * spec[freqs >= 400].sum())

    def test_windows_cover_the_whole_clip(self):
        n = int(4.1 * SR)
        spans = S._windows(n, SR)
        self.assertEqual(spans[0][0], 0)
        self.assertEqual(spans[-1][1], n)
        self.assertTrue(all(b - a == int(S.WINDOW_S * SR) for a, b in spans))

    def test_none_stays_none(self):
        self.assertEqual(S.own_voice_only(None, ME, FakeEncoder()), (None, []))


class VoiceprintFileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / "voiceprint.json"

    def test_roundtrip_is_unit_length(self):
        S.save_voiceprint(np.array([3.0, 4.0]), quality=0.8, seconds=20, path=self.path)
        vec = S.load_voiceprint(self.path)
        np.testing.assert_allclose(vec, [0.6, 0.8], atol=1e-6)
        self.assertTrue(S.has_voiceprint(self.path))

    def test_missing_broken_or_other_model_is_none(self):
        self.assertIsNone(S.load_voiceprint(self.path))
        self.path.write_text("{oops", encoding="utf-8")
        self.assertIsNone(S.load_voiceprint(self.path))
        self.path.write_text('{"model": "other", "vector": [1, 0]}', encoding="utf-8")
        self.assertIsNone(S.load_voiceprint(self.path))

    def test_build_voiceprint_reports_a_noisy_sample(self):
        clean, q_clean = S.build_voiceprint(_tone(9.0, 150), FakeEncoder())
        self.assertGreater(q_clean, 0.99)
        _vec, q_mixed = S.build_voiceprint(np.concatenate([_tone(6.0, 150), _tone(3.0, 1200)]), FakeEncoder())
        self.assertLess(q_mixed, 0.6)
        np.testing.assert_allclose(np.linalg.norm(clean), 1.0, atol=1e-6)

    def test_enroll_refuses_too_little_speech(self):
        with mock.patch("yo.vad.trim_to_speech", return_value=_tone(3.0, 150)):
            with self.assertRaises(ValueError):
                S.enroll_from_pcm(np.zeros(SR), encoder=FakeEncoder(), path=self.path)
        self.assertFalse(self.path.exists())

    def test_enroll_saves(self):
        with mock.patch("yo.vad.trim_to_speech", return_value=_tone(12.0, 150)):
            quality, seconds = S.enroll_from_pcm(np.zeros(SR), encoder=FakeEncoder(), path=self.path)
        self.assertAlmostEqual(seconds, 12.0)
        self.assertGreater(quality, 0.99)
        self.assertTrue(S.has_voiceprint(self.path))


class SpeakerFilterTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / "voiceprint.json"
        p = mock.patch.object(S, "voiceprint_path", lambda: self.path)
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(S, "model_ready", lambda *_a: True)
        p.start()
        self.addCleanup(p.stop)

    def test_without_a_sample_no_one_passes(self):
        enc = FakeEncoder()
        pcm = _tone(3.0, 1200)
        flt = S.SpeakerFilter(enc)
        self.assertIsNone(flt.apply(pcm, threshold=0.4))
        self.assertEqual(enc.calls, 0)
        self.assertTrue(flt.missing_sample, "the cat must say a sample is missing")
        S.save_voiceprint(ME, quality=1.0, seconds=20, path=self.path)
        flt.apply(pcm, threshold=0.4)
        self.assertFalse(flt.missing_sample)

    def test_with_a_sample_other_voice_is_dropped(self):
        S.save_voiceprint(ME, quality=1.0, seconds=20, path=self.path)
        flt = S.SpeakerFilter(FakeEncoder())
        self.assertIsNone(flt.apply(_tone(3.0, 1200), threshold=0.4))
        mine = _tone(3.0, 150)
        self.assertIs(flt.apply(mine, threshold=0.4), mine)

    def test_new_sample_is_picked_up_without_restart(self):
        S.save_voiceprint(np.array([0.0, 1.0, 0.0]), quality=1.0, seconds=20, path=self.path)
        flt = S.SpeakerFilter(FakeEncoder())
        self.assertIsNone(flt.apply(_tone(3.0, 150), threshold=0.4))
        S.save_voiceprint(ME, quality=1.0, seconds=20, path=self.path)
        os.utime(self.path, (1, 2))  # mtime resolution on some file systems
        self.assertIsNotNone(flt.apply(_tone(3.0, 150), threshold=0.4))

    def test_model_failure_blocks_unverified_audio(self):
        S.save_voiceprint(ME, quality=1.0, seconds=20, path=self.path)
        enc = FakeEncoder()
        enc.embed_many = mock.Mock(side_effect=RuntimeError("onnx"))
        pcm = _tone(3.0, 1200)
        with self.assertRaisesRegex(RuntimeError, "фраза заблокирована"):
            S.SpeakerFilter(enc).apply(pcm, threshold=0.4)


class ModelDownloadTests(unittest.TestCase):
    def test_bad_hash_is_not_kept(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "src.onnx"
            src.write_bytes(b"x" * 2_000_000)
            dst = Path(d) / "model.onnx"
            with self.assertRaises(RuntimeError):
                S.ensure_model(path=dst, url=src.as_uri())
            self.assertFalse(dst.exists())
            self.assertFalse(dst.with_name(dst.name + ".part").exists())

    def test_good_hash_is_kept(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "src.onnx"
            src.write_bytes(b"y" * 2_000_000)
            dst = Path(d) / "model.onnx"
            import hashlib

            with mock.patch.object(S, "MODEL_SHA256", hashlib.sha256(src.read_bytes()).hexdigest()):
                self.assertEqual(S.ensure_model(path=dst, url=src.as_uri()), dst)
            self.assertTrue(S.model_ready(dst))


class FakeCapture:
    """First device refuses like WDM-KS did; the next one streams speech."""

    refuse = {7}

    def __init__(self, on_block, sample_rate=SR) -> None:
        self.on_block = on_block
        self.tried: list = []
        self.stopped = False

    def start(self, device=None, *, exclusive=False):
        self.tried.append((device, exclusive))
        if device in self.refuse:
            raise RuntimeError("Unanticipated host error [Windows WDM-KS error 0]")
        for _ in range(5):
            self.on_block(_tone(0.1, 150), 0.1, [])

    def stop(self, *, drain=True):
        self.stopped = True


class RecordTests(unittest.TestCase):
    def test_falls_back_to_the_next_copy_of_the_mic(self):
        made = []

        def factory(on_block, sample_rate):
            made.append(FakeCapture(on_block, sample_rate))
            return made[-1]

        with mock.patch("yo.capture.capture_candidate_indices", return_value=[7, 3]):
            pcm = S.record_pcm(0.05, "Headset", capture_factory=factory)
        self.assertEqual([d for d, _ex in made[0].tried], [7, 3])
        self.assertTrue(made[0].stopped)
        self.assertEqual(len(pcm), 5 * int(0.1 * SR))

    def test_every_device_refusing_is_a_clear_error(self):
        cap = FakeCapture(lambda *_a: None)
        cap.refuse = {7, None}
        with mock.patch("yo.capture.capture_candidate_indices", return_value=[7]):
            with self.assertRaises(RuntimeError) as ctx:
                S.open_capture(cap, "Headset")
        self.assertIn("не удалось открыть микрофон", str(ctx.exception))
        self.assertNotIn(None, [d for d, _ex in cap.tried])


class ConfigTests(unittest.TestCase):
    def test_filter_is_off_by_default(self):
        cfg = Config()
        self.assertFalse(cfg.speaker_filter)
        self.assertAlmostEqual(cfg.speaker_threshold, S.DEFAULT_THRESHOLD)


@unittest.skipUnless(os.environ.get("YO_SPEAKER_MODEL"), "set YO_SPEAKER_MODEL=path to the ONNX model")
class RealModelTests(unittest.TestCase):
    def test_embedding_shape_and_self_similarity(self):
        enc = S.SpeakerEncoder(Path(os.environ["YO_SPEAKER_MODEL"]))
        rng = np.random.default_rng(0)
        pcm = (0.05 * rng.standard_normal(2 * SR)).astype(np.float32) + _tone(2.0, 180)
        a, b = enc.embed_many([pcm, pcm])
        self.assertEqual(a.shape, (256,))
        self.assertAlmostEqual(S.cosine(a, b), 1.0, places=4)


if __name__ == "__main__":
    unittest.main()
