"""Regressions for room noise, silent input and speaker-filter bypasses."""
import queue
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from yo.asr import keep_segment, prepare_pcm
from yo.audio import AudioCapture
from yo.capture import capture_candidate_indices
from yo.vad import FRAME, SpeechGate, trim_to_speech


class NoiseTests(unittest.TestCase):
    def test_real_silero_rejects_noise_and_hum(self):
        rng = np.random.default_rng(5)
        for audio in (rng.normal(0, .003, 16000 * 3).astype('float32'),
                      (.02 * np.sin(np.arange(16000 * 3) * 2 * np.pi * 180 / 16000)).astype('float32')):
            gate = SpeechGate()
            events = [gate.process(audio[i:i+FRAME]) for i in range(0, len(audio), FRAME)]
            self.assertNotIn('start', events)
            self.assertIsNone(trim_to_speech(audio))

    def test_loud_non_speech_cannot_bypass_final_filter(self):
        backend = Mock()
        backend.prob.return_value = 0.0
        with patch('yo.vad._try_silero', return_value=backend):
            self.assertIsNone(trim_to_speech(np.full(32000, .1, dtype='float32')))

    def test_failed_vad_never_switches_to_energy(self):
        with patch('yo.vad._try_silero', return_value=None):
            with self.assertRaises(RuntimeError):
                SpeechGate()
            with self.assertRaises(RuntimeError):
                trim_to_speech(np.ones(16000, dtype='float32'))

    def test_high_speech_probability_still_needs_audible_input(self):
        backend = Mock()
        backend.prob.return_value = .99
        with patch('yo.vad._try_silero', return_value=backend):
            gate = SpeechGate()
            faint = np.full(FRAME, .0001, dtype='float32')
            self.assertNotIn('start', [gate.process(faint) for _ in range(20)])
            self.assertIsNone(trim_to_speech(np.tile(faint, 30)))

    def test_nonfinite_audio_and_confidence_are_rejected(self):
        for value in (float('nan'), float('inf')):
            self.assertIsNone(prepare_pcm(np.full(16000, value)))
            self.assertIsNone(trim_to_speech(np.full(16000, value)))
            self.assertFalse(keep_segment(SimpleNamespace(text='Салюты', avg_logprob=value)))

    def test_no_speech_confidence_cannot_be_overridden_by_fluent_text(self):
        self.assertFalse(keep_segment(SimpleNamespace(text='Салюты', no_speech_prob=.8, avg_logprob=-.1)))
        self.assertTrue(keep_segment(SimpleNamespace(text='Салюты', no_speech_prob=.1, avg_logprob=-.1)))


class MicrophoneTests(unittest.TestCase):
    def test_missing_selected_mic_has_no_candidates(self):
        self.assertEqual(capture_candidate_indices('USB headset', devices=[
            {'name': 'Laptop mic', 'max_input_channels': 1, 'hostapi_name': 'Windows WASAPI'}]), [])

    def test_silent_open_stream_is_kept_and_first_callback_uses_native_rate(self):
        cap = AudioCapture(Mock())
        stream = Mock()
        observed = []
        stream.start.side_effect = lambda: observed.append(cap.capture_rate)
        with patch('yo.audio._input_stream_plans', return_value=[{'samplerate': 48000}]), \
             patch('yo.audio.sd.InputStream', return_value=stream), \
             patch('yo.audio._probe_stream_silent', return_value=True):
            cap.start(device=1)
        self.assertEqual(observed, [48000])
        self.assertIs(cap._stream, stream)
        stream.close.assert_not_called()
        cap.stop(drain=False)


class BufferTests(unittest.TestCase):
    def app(self, event):
        from yo.app import YoApp
        app = YoApp.__new__(YoApp)
        app.config = SimpleNamespace(sample_rate=16000)
        app.session = SimpleNamespace(listening=True, task='transcribe')
        app._stopping = False
        app._chunks = []
        app._chunks_lock = threading.Lock()
        app._jobs = queue.Queue()
        app._token = app._utt = 1
        app.vad = SimpleNamespace(speaking=event != 'silence', process=lambda *args: event)
        return app

    def test_minutes_of_silence_keep_only_preroll(self):
        app = self.app('silence')
        with patch('yo.app.idle_add'):
            for _ in range(1200):
                app._on_block(np.zeros(1600, dtype='float32'), 0., [])
        self.assertLessEqual(sum(map(len, app._chunks)), 6400)
        self.assertTrue(app._jobs.empty())

    def test_continuous_speech_is_bounded_and_samples_preserved(self):
        app = self.app('speech')
        with patch('yo.app.idle_add'):
            for _ in range(650):
                app._on_block(np.ones(1600, dtype='float32'), .1, [])
        self.assertEqual(app._jobs.qsize(), 2)
        total = sum(len(app._jobs.get()[0]) for _ in range(2)) + sum(map(len, app._chunks))
        self.assertEqual(total, 650 * 1600)
