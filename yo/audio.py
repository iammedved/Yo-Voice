"""Захват микрофона: PCM, RMS, спектр тембра."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

import numpy as np
import sounddevice as sd

from yo.spectrum import SAMPLE_RATE, resample, rms, spectrum_bands

log = logging.getLogger("yo.audio")

BlockHandler = Callable[[np.ndarray, float, list[float]], None]

DEAD_STREAM_MS = 900.0
DEAD_STREAM_RMS = 0.00025


def stream_looks_dead(peak_rms: float, elapsed_ms: float, *, min_ms: float = DEAD_STREAM_MS, max_rms: float = DEAD_STREAM_RMS) -> bool:
    return elapsed_ms >= min_ms and peak_rms < max_rms


class AudioCapture:
    def __init__(self, on_block: BlockHandler, sample_rate: int = SAMPLE_RATE) -> None:
        self.on_block = on_block
        self.sample_rate = sample_rate
        self.capture_rate = sample_rate
        self.peak_level = 0.0
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()

    def start(self, device: int | None = None) -> None:
        self.stop()
        self.peak_level = 0.0
        info = sd.query_devices(device) if device is not None else sd.query_devices(kind="input")
        self.capture_rate = int(info.get("default_samplerate") or 48000)
        blocksize = max(256, int(round(self.capture_rate * 512 / self.sample_rate)))
        kwargs: dict = {
            "samplerate": self.capture_rate,
            "channels": 1,
            "dtype": "float32",
            "blocksize": blocksize,
            "callback": self._callback,
        }
        if device is not None:
            kwargs["device"] = device
        stream = sd.InputStream(**kwargs)
        stream.start()
        self._stream = stream

    def stop(self) -> None:
        stream = self._stream
        self._stream = None
        if stream is None:
            return
        try:
            stream.stop()
            stream.close()
        except Exception:
            pass

    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ARG002
        try:
            block = np.copy(indata[:, 0])
            block = block - float(np.mean(block))
            level = rms(block)
            self.peak_level = max(self.peak_level, level)
            bands = spectrum_bands(block, sample_rate=self.capture_rate)
            pcm = resample(block, self.capture_rate, self.sample_rate)
            if 0.0008 < level < 0.04:
                pcm = np.clip(pcm * min(10.0, 0.04 / level), -1.0, 1.0)
            self.on_block(pcm, level, bands)
        except Exception:
            log.exception("ошибка колбэка микрофона")
