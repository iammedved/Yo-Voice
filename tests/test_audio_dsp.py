import unittest

import numpy as np

from yo.spectrum import DcBlocker, StreamResampler, rms


def _tone(freq: float, rate: int, seconds: float = 1.0, amp: float = 0.1) -> np.ndarray:
    t = np.arange(int(rate * seconds)) / float(rate)
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _blocks(x: np.ndarray, size: int):
    return [x[i : i + size] for i in range(0, len(x), size)]


class StreamResamplerTests(unittest.TestCase):
    def _run(self, x, src, dst, size):
        rs = StreamResampler(src, dst)
        return np.concatenate([rs.process(b) for b in _blocks(x, size)])

    def test_speech_band_passes(self):
        out = self._run(_tone(1000, 48000), 48000, 16000, 480)
        self.assertAlmostEqual(rms(out[400:]), rms(_tone(1000, 16000)), delta=0.003)

    def test_hiss_above_nyquist_does_not_fold_into_speech(self):
        for freq in (9000, 10000, 12000, 20000):
            out = self._run(_tone(freq, 48000), 48000, 16000, 480)
            # Plain decimation keeps the full 0.07 RMS as a 4-7 kHz alias.
            self.assertLess(rms(out[400:]), 0.0015, freq)

    def test_block_size_does_not_change_the_result(self):
        rng = np.random.default_rng(1)
        x = (0.05 * rng.standard_normal(44100)).astype(np.float32)
        whole = self._run(x, 44100, 16000, len(x))
        for size in (441, 512, 1000, 37):
            parts = self._run(x, 44100, 16000, size)
            self.assertEqual(len(parts), len(whole), size)
            np.testing.assert_allclose(parts, whole, atol=1e-5)

    def test_length_does_not_drift(self):
        out = self._run(np.zeros(44100 * 10, dtype=np.float32), 44100, 16000, 441)
        self.assertLessEqual(abs(len(out) - 160000), 1)

    def test_same_rate_is_untouched(self):
        x = _tone(300, 16000)
        np.testing.assert_array_equal(StreamResampler(16000, 16000).process(x), x)


class DcBlockerTests(unittest.TestCase):
    def test_removes_offset(self):
        dc = DcBlocker(48000)
        x = _tone(200, 48000, seconds=2.0) + np.float32(0.2)
        out = np.concatenate([dc.process(b) for b in _blocks(x, 480)])
        self.assertLess(abs(float(np.mean(out[-48000:]))), 0.002)

    def test_low_voice_has_no_block_rate_buzz(self):
        x = _tone(120, 48000)
        dc = DcBlocker(48000)
        out = np.concatenate([dc.process(b) for b in _blocks(x, 480)])
        err = rms(out[24000:] - x[24000:])
        # Per-block mean removal left ~0.011 RMS of 100 Hz steps here.
        self.assertLess(err, 0.002)


if __name__ == "__main__":
    unittest.main()
