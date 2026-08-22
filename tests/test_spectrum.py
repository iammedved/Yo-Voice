import math
import unittest

try:
    import numpy as np
except ImportError:
    np = None

from yo.spectrum import EnergyVad, resample, rms, spectrum_bands


@unittest.skipIf(np is None, "numpy не установлен")
class SpectrumTests(unittest.TestCase):
    def test_silence_rms_near_zero(self):
        silence = np.zeros(512, dtype=np.float32)
        self.assertLess(rms(silence), 1e-6)

    def test_loud_sine_has_energy(self):
        sr = 16000
        t = np.arange(1024) / sr
        wave = (0.4 * np.sin(2 * math.pi * 440 * t)).astype(np.float32)
        self.assertGreater(rms(wave), 0.2)

    def test_resample_length(self):
        src = np.linspace(-0.2, 0.2, 480, dtype=np.float32)
        dst = resample(src, 48000, 16000)
        self.assertAlmostEqual(len(dst) / len(src), 16000 / 48000, delta=0.02)

    def test_low_tone_heavier_in_low_bands(self):
        sr = 16000
        t = np.arange(2048) / sr
        wave = (0.5 * np.sin(2 * math.pi * 120 * t)).astype(np.float32)
        bands = spectrum_bands(wave, n_bands=12, sample_rate=sr)
        self.assertEqual(len(bands), 12)
        low = sum(bands[:4])
        high = sum(bands[8:])
        self.assertGreater(low, high)


class VadTests(unittest.TestCase):
    def test_start_and_end(self):
        vad = EnergyVad()
        events = [vad.process(0.08, 32) for _ in range(8)]
        self.assertIn("start", events)
        self.assertTrue(vad.speaking)
        events = [vad.process(0.0002, 32) for _ in range(45)]
        self.assertIn("end", events)
        self.assertFalse(vad.speaking)

    def test_quiet_headset_speech_is_detected(self):
        vad = EnergyVad()
        for _ in range(25):
            vad.process(0.0004, 32)
        events = [vad.process(0.006, 32) for _ in range(12)]
        self.assertIn("start", events)
        self.assertTrue(vad.speaking)

    def test_very_quiet_speech_is_detected(self):
        vad = EnergyVad()
        for _ in range(30):
            vad.process(0.00025, 32)
        events = [vad.process(0.0018, 32) for _ in range(16)]
        self.assertIn("start", events)
        self.assertTrue(vad.speaking)

    def test_distant_murmur_is_ignored(self):
        vad = EnergyVad()
        for _ in range(40):
            vad.process(0.00012, 32)
        events = [vad.process(0.00028, 32) for _ in range(16)]
        self.assertNotIn("start", events)
        self.assertFalse(vad.speaking)

    def test_quiet_continuation_after_loud_start(self):
        vad = EnergyVad()
        for _ in range(8):
            vad.process(0.02, 32)
        self.assertTrue(vad.speaking)
        events = [vad.process(0.0012, 32) for _ in range(12)]
        self.assertNotIn("end", events)
        self.assertTrue(vad.speaking)

    def test_close_talk_headset_is_detected(self):
        vad = EnergyVad()
        for _ in range(40):
            vad.process(0.00012, 32)
        events = [vad.process(0.004, 32) for _ in range(12)]
        self.assertIn("start", events)
        self.assertTrue(vad.speaking)

    def test_short_pause_does_not_split_phrase(self):
        vad = EnergyVad()
        for _ in range(8):
            vad.process(0.02, 32)
        self.assertTrue(vad.speaking)
        gap = [vad.process(0.0003, 32) for _ in range(10)]  # 320 ms
        self.assertNotIn("end", gap)
        self.assertTrue(vad.speaking)
