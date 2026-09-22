"""Захват микрофона: PCM, RMS, спектр тембра."""

from __future__ import annotations

import logging
import sys
import threading
import time
from collections.abc import Callable

import numpy as np
import sounddevice as sd

from yo.spectrum import SAMPLE_RATE, resample, rms, spectrum_bands

log = logging.getLogger("yo.audio")

BlockHandler = Callable[[np.ndarray, float, list[float]], None]

DEAD_STREAM_MS = 900.0
# WASAPI auto-convert / mute: genuine zeros. MME Barracuda floor ~1.51e-05 is alive.
DEAD_STREAM_RMS = 1e-6
STOP_TAIL_MS = 300
PROBE_SILENT_S = 0.45


def drain_timeout_s(block_ms: float = 100.0) -> float:
    """Wait up to one PortAudio block plus slack so the last word is not dropped."""
    return min(0.25, max(0.12, (block_ms / 1000.0) * 1.8))


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
        self._drain = threading.Event()
        self._drain.set()
        self._drain_pending = False

    def start(self, device: int | None = None, *, exclusive: bool = False) -> None:
        self.stop(drain=False)
        self.peak_level = 0.0
        self._drain_pending = False
        self._drain.set()
        last_error: Exception | None = None
        silent_keys: set[tuple] = set()
        for kwargs in _input_stream_plans(device, self.sample_rate, exclusive=exclusive):
            key = (kwargs.get("samplerate"), bool(kwargs.get("extra_settings")))
            if key in silent_keys:
                continue
            stream = None
            try:
                stream = sd.InputStream(**kwargs, callback=self._callback)
                stream.start()
            except Exception as exc:
                last_error = exc
                log.warning(
                    "микрофон не открылся device=%s sr=%s ch=%s: %s",
                    kwargs.get("device"),
                    kwargs.get("samplerate"),
                    kwargs.get("channels"),
                    exc,
                )
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass
                continue
            self.capture_rate = int(kwargs["samplerate"])
            self._stream = stream
            log.info(
                "микрофон открыт device=%s sr=%s ch=%s exclusive=%s",
                kwargs.get("device"),
                self.capture_rate,
                kwargs.get("channels"),
                bool(kwargs.get("extra_settings")),
            )
            if sys.platform == "win32" and _probe_stream_silent(self):
                log.warning(
                    "тихий поток sr=%s peak_rms=%s — другой формат",
                    self.capture_rate,
                    self.peak_level,
                )
                silent_keys.add(key)
                self._stream = None
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
                last_error = RuntimeError("микрофон молчит")
                self.peak_level = 0.0
                continue
            return
        if last_error is not None:
            raise last_error
        raise RuntimeError("микрофон не найден")

    def stop(self, *, drain: bool = True) -> None:
        stream = self._stream
        if stream is None:
            return
        if drain:
            self._drain.clear()
            self._drain_pending = True
            self._drain.wait(timeout=drain_timeout_s())
            self._drain_pending = False
        self._stream = None
        try:
            stream.stop()
            stream.close()
        except Exception:
            pass
        self._drain.set()

    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ARG002
        try:
            if status:
                log.warning("портaudio: %s", status)
            if indata.ndim > 1 and indata.shape[1] > 1:
                block = np.mean(indata, axis=1)
            else:
                block = np.copy(indata[:, 0] if indata.ndim > 1 else indata)
            block = np.asarray(block, dtype=np.float32)
            block = block - float(np.mean(block))
            level = rms(block)
            self.peak_level = max(self.peak_level, level)
            bands = spectrum_bands(block, sample_rate=self.capture_rate)
            pcm = resample(block, self.capture_rate, self.sample_rate)
            self.on_block(pcm, level, bands)
        except Exception:
            log.exception("ошибка колбэка микрофона")
        finally:
            if self._drain_pending:
                self._drain_pending = False
                self._drain.set()


def _wasapi_capture_rates(native_rate: int) -> list[int]:
    """Win11 Communications USB at 16 kHz + AUTOCONVERTPCM yields silent PCM.

    Open shared-mode at the mixer rate (>=44100). Never request 16 kHz via
    WASAPI conversion; resample to 16 kHz in-app after capture.
    """
    rates: list[int] = []
    native = int(native_rate or 0)
    if native >= 44100:
        rates.append(native)
    for rate in (48000, 44100):
        if rate not in rates:
            rates.append(rate)
    return rates


def _probe_stream_silent(capture: AudioCapture, timeout_s: float = PROBE_SILENT_S) -> bool:
    deadline = time.monotonic() + max(0.12, float(timeout_s))
    while time.monotonic() < deadline:
        if capture.peak_level >= DEAD_STREAM_RMS:
            return False
        time.sleep(0.04)
    return capture.peak_level < DEAD_STREAM_RMS


def _input_stream_plans(device: int | None, sample_rate: int, *, exclusive: bool = False) -> list[dict]:
    """WASAPI: shared mix rate, no AUTOCONVERTPCM. Exclusive is last resort."""
    try:
        info = sd.query_devices(device) if device is not None else sd.query_devices(kind="input")
    except Exception:
        info = {}
    native_rate = int(info.get("default_samplerate") or 48000)
    try:
        max_in = max(1, int(info.get("max_input_channels") or 1))
    except (TypeError, ValueError):
        max_in = 1
    host = ""
    try:
        host = str(sd.query_hostapis(int(info.get("hostapi")))["name"]).lower()
    except Exception:
        host = ""
    wasapi = sys.platform == "win32" and "wasapi" in host
    extras: list[object] = [None]
    if exclusive:
        if not wasapi:
            return []
        try:
            extras = [sd.WasapiSettings(exclusive=True)]
        except Exception:
            return []
    channel_opts: list[int] = []
    for count in (min(max_in, 2), 1, max_in):
        if count >= 1 and count not in channel_opts:
            channel_opts.append(count)
    if wasapi:
        rates = _wasapi_capture_rates(native_rate)
    else:
        rates = []
        rate_opts = (native_rate, 48000, 44100)
        if sys.platform != "win32":
            rate_opts = (native_rate, 48000, 44100, sample_rate)
        for rate in rate_opts:
            if rate and rate not in rates:
                rates.append(int(rate))
    plans: list[dict] = []
    for extra in extras:
        for rate in rates:
            for channels in channel_opts:
                kwargs: dict = {
                    "samplerate": rate,
                    "channels": channels,
                    "dtype": "float32",
                    "latency": "high",
                }
                if device is not None:
                    kwargs["device"] = device
                if sys.platform == "win32":
                    kwargs["blocksize"] = 0
                else:
                    kwargs["blocksize"] = max(256, int(round(rate * 512 / sample_rate)))
                if extra is not None:
                    kwargs["extra_settings"] = extra
                plans.append(kwargs)
    return plans
