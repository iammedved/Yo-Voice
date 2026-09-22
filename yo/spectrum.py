"""Громкость и тембр для живых волн overlay."""

from __future__ import annotations

import math

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore


N_BANDS = 12
SAMPLE_RATE = 16000
# Headset idle is ~1.5e-5; close whisper ~8e-4..4e-3; shout is >0.15.
WAVE_RMS_FLOOR = 0.00012
WAVE_RMS_FULL = 0.006
ENERGY_START_FLOOR = 0.00035
ENERGY_START_CAP = 0.0007
ENERGY_START_NOISE_MULT = 2.6
ENERGY_CONTINUE_FLOOR = 0.00028
ENERGY_CONTINUE_NOISE_MULT = 1.8
ENERGY_NOISE_LEARN = 0.0005


def resample(block, src_rate: int, dst_rate: int):
    if np is None:
        return block
    arr = np.asarray(block, dtype=np.float32)
    if src_rate == dst_rate or len(arr) < 2:
        return arr
    n_dst = max(1, int(round(len(arr) * dst_rate / src_rate)))
    old_x = np.linspace(0.0, 1.0, num=len(arr), endpoint=False)
    new_x = np.linspace(0.0, 1.0, num=n_dst, endpoint=False)
    return np.interp(new_x, old_x, arr).astype(np.float32)


def rms(block) -> float:
    if np is None:
        if not block:
            return 0.0
        return math.sqrt(sum(x * x for x in block) / len(block))
    if block is None or len(block) == 0:
        return 0.0
    arr = np.asarray(block, dtype=np.float32)
    return float(np.sqrt(np.mean(np.square(arr))))


def wave_amplitude(rms_value: float) -> float:
    """Overlay bar height: idle stays flat, whisper already moves, shout saturates."""
    level = float(rms_value)
    if level < WAVE_RMS_FLOOR:
        return 0.12
    return 0.16 + min(0.84, (level - WAVE_RMS_FLOOR) / WAVE_RMS_FULL * 0.84)


def voice_loudness(rms_value: float) -> float:
    return min(1.0, max(0.0, (float(rms_value) - WAVE_RMS_FLOOR) / WAVE_RMS_FULL))


def spectrum_bands(block, n_bands: int = N_BANDS, sample_rate: int = SAMPLE_RATE) -> list[float]:
    """Логарифмические полосы 80–4000 Гц, 0..1. Это тембр, не только громкость."""
    if np is None or block is None or len(block) < 32:
        return [0.0] * n_bands
    arr = np.asarray(block, dtype=np.float32)
    windowed = arr * np.hanning(len(arr)).astype(np.float32)
    spec = np.abs(np.fft.rfft(windowed))
    freqs = np.fft.rfftfreq(len(arr), d=1.0 / sample_rate)
    lo, hi = 80.0, min(4000.0, sample_rate / 2.0)
    edges = np.geomspace(lo, hi, n_bands + 1)
    bands: list[float] = []
    peak = float(np.max(spec)) or 1.0
    for a, b in zip(edges[:-1], edges[1:]):
        mask = (freqs >= a) & (freqs < b)
        value = float(np.mean(spec[mask])) if np.any(mask) else 0.0
        bands.append(max(0.0, min(1.0, value / peak)))
    return bands


class EnergyVad:
    def __init__(self) -> None:
        self.noise = 0.00018
        self.speaking = False
        self._speech_ms = 0.0
        self._silence_ms = 0.0
        self._speech_peak = 0.0

    def process(self, level: float, dt_ms: float) -> str:
        # Learn the idle floor only. Quiet speech must not raise the gate.
        if not self.speaking and level < ENERGY_NOISE_LEARN:
            self.noise = 0.97 * self.noise + 0.03 * level
        start_thresh = min(ENERGY_START_CAP, max(ENERGY_START_FLOOR, self.noise * ENERGY_START_NOISE_MULT))
        if self.speaking:
            if level > start_thresh:
                self._speech_peak = 0.85 * self._speech_peak + 0.15 * level
            continue_thresh = max(self.noise * ENERGY_CONTINUE_NOISE_MULT, ENERGY_CONTINUE_FLOOR)
            is_speech = level > continue_thresh
        else:
            is_speech = level > start_thresh
        if is_speech:
            self._speech_ms += dt_ms
            self._silence_ms = 0.0
            if not self.speaking:
                self._speech_peak = max(self._speech_peak, level)
            if not self.speaking and self._speech_ms > 40:
                self.speaking = True
                return "start"
            return "speech" if self.speaking else "silence"
        self._speech_ms = 0.0
        if self.speaking:
            self._silence_ms += dt_ms
            if self._silence_ms > 1100:
                self.speaking = False
                self._silence_ms = 0.0
                self._speech_peak = 0.0
                return "end"
            return "speech"
        return "silence"
