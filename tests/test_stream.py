import unittest

from yo.audio import stream_looks_dead


class DeadStreamTests(unittest.TestCase):
    def test_true_silence_after_a_second_is_dead(self):
        self.assertTrue(stream_looks_dead(peak_rms=0.0, elapsed_ms=1000))

    def test_quiet_speech_is_not_dead(self):
        self.assertFalse(stream_looks_dead(peak_rms=0.002, elapsed_ms=1000))

    def test_does_not_flag_before_window(self):
        self.assertFalse(stream_looks_dead(peak_rms=0.0, elapsed_ms=200))
