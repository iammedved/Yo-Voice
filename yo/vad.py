"""Потоковый VAD: Silero ONNX, запасной EnergyVad. В Whisper только речь."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from yo.spectrum import EnergyVad, rms

log = logging.getLogger("yo.vad")

FRAME = 512
CONTEXT = 64
SAMPLE_RATE = 16000
START_MS = 40.0
END_MS = 1100.0
SILERO_START = 0.45
SILERO_CONTINUE = 0.30
ENERGY_FRAME_THRESH = 0.0007


def silero_model_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "silero_vad.onnx"


_SESSION = None


def _silero_session():
    global _SESSION
    if _SESSION is False:
        return None
    if _SESSION is not None:
        return _SESSION
    path = silero_model_path()
    if not path.exists():
        _SESSION = False
        return None
    try:
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        _SESSION = ort.InferenceSession(
            str(path),
            providers=["CPUExecutionProvider"],
            sess_options=opts,
        )
        return _SESSION
    except Exception:
        log.warning("Silero VAD не загрузился, беру EnergyVad", exc_info=True)
        _SESSION = False
        return None


class SileroBackend:
    def __init__(self, path: Path | None = None) -> None:
        session = _silero_session()
        if session is None:
            raise RuntimeError("silero session missing")
        self.session = session
        self.reset()

    def reset(self) -> None:
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, CONTEXT), dtype=np.float32)

    def prob(self, frame: np.ndarray) -> float:
        chunk = np.asarray(frame, dtype=np.float32).reshape(1, -1)
        if chunk.shape[1] < FRAME:
            chunk = np.pad(chunk, ((0, 0), (0, FRAME - chunk.shape[1])))
        elif chunk.shape[1] > FRAME:
            chunk = chunk[:, :FRAME]
        x = np.concatenate([self._context, chunk], axis=1)
        out, state = self.session.run(
            None,
            {
                "input": x,
                "state": self._state,
                "sr": np.array(16000, dtype=np.int64),
            },
        )
        self._state = np.asarray(state, dtype=np.float32)
        self._context = x[:, -CONTEXT:]
        return float(out.reshape(-1)[0])


def _try_silero() -> SileroBackend | None:
    if _silero_session() is None:
        return None
    try:
        return SileroBackend()
    except Exception:
        log.warning("Silero VAD не загрузился, беру EnergyVad", exc_info=True)
        return None


class SpeechGate:
    def __init__(self, backend: str | None = None) -> None:
        requested = backend or "auto"
        self._energy = EnergyVad()
        self._silero: SileroBackend | None = None
        if requested == "energy":
            self._backend = "energy"
        else:
            self._silero = _try_silero()
            self._backend = "silero" if self._silero is not None else "energy"
        self.speaking = False
        self._speech_ms = 0.0
        self._silence_ms = 0.0
        self._buf = np.zeros(0, dtype=np.float32)

    def reset(self) -> None:
        self._energy = EnergyVad()
        if self._silero is not None:
            self._silero.reset()
        self.speaking = False
        self._speech_ms = 0.0
        self._silence_ms = 0.0
        self._buf = np.zeros(0, dtype=np.float32)

    def process(self, pcm: np.ndarray, sample_rate: int = SAMPLE_RATE) -> str:
        pcm = np.asarray(pcm, dtype=np.float32)
        if sample_rate != SAMPLE_RATE:
            from yo.spectrum import resample

            pcm = resample(pcm, sample_rate, SAMPLE_RATE)
        if self._backend == "energy":
            dt_ms = 1000.0 * len(pcm) / float(SAMPLE_RATE)
            event = self._energy.process(rms(pcm), dt_ms)
            self.speaking = self._energy.speaking
            return event
        self._buf = np.concatenate([self._buf, pcm]) if len(self._buf) else pcm
        last = "silence"
        while len(self._buf) >= FRAME:
            frame = self._buf[:FRAME]
            self._buf = self._buf[FRAME:]
            last = self._step_silero(frame)
        return last

    def _step_silero(self, frame: np.ndarray) -> str:
        assert self._silero is not None
        dt_ms = 1000.0 * FRAME / float(SAMPLE_RATE)
        prob = self._silero.prob(frame)
        thresh = SILERO_CONTINUE if self.speaking else SILERO_START
        is_speech = prob >= thresh
        if is_speech:
            self._speech_ms += dt_ms
            self._silence_ms = 0.0
            if not self.speaking and self._speech_ms > START_MS:
                self.speaking = True
                return "start"
            return "speech" if self.speaking else "silence"
        self._speech_ms = 0.0
        if self.speaking:
            self._silence_ms += dt_ms
            if self._silence_ms > END_MS:
                self.speaking = False
                self._silence_ms = 0.0
                return "end"
            return "speech"
        return "silence"


def _energy_mask(pcm: np.ndarray, sample_rate: int, frame: int = FRAME) -> list[bool]:
    mask: list[bool] = []
    for i in range(0, len(pcm), frame):
        chunk = pcm[i : i + frame]
        if len(chunk) < frame // 2:
            break
        mask.append(rms(chunk) > ENERGY_FRAME_THRESH)
    return mask


def _silero_mask(pcm: np.ndarray, backend: SileroBackend, frame: int = FRAME) -> list[bool]:
    backend.reset()
    mask: list[bool] = []
    speaking = False
    for i in range(0, len(pcm), frame):
        chunk = pcm[i : i + frame]
        if len(chunk) < frame:
            chunk = np.pad(chunk, (0, frame - len(chunk)))
        prob = backend.prob(chunk)
        thresh = SILERO_CONTINUE if speaking else SILERO_START
        speaking = prob >= thresh
        mask.append(speaking)
    return mask


def trim_to_speech(
    pcm: np.ndarray | None,
    sample_rate: int = SAMPLE_RATE,
    backend: str | None = "energy",
    pad_ms: float = 200.0,
) -> np.ndarray | None:
    if pcm is None or len(pcm) < int(sample_rate * 0.12):
        return None
    audio = np.asarray(pcm, dtype=np.float32)
    requested = backend or "auto"
    mask: list[bool]
    if requested != "energy":
        silero = _try_silero()
        if silero is not None:
            mask = _silero_mask(audio, silero)
        else:
            mask = _energy_mask(audio, sample_rate)
    else:
        mask = _energy_mask(audio, sample_rate)
    if not any(mask):
        return None
    first = next(i for i, flag in enumerate(mask) if flag)
    last = len(mask) - 1 - next(i for i, flag in enumerate(reversed(mask)) if flag)
    pad_frames = max(0, int(round(pad_ms / (1000.0 * FRAME / sample_rate))))
    start = max(0, (first - pad_frames) * FRAME)
    end = min(len(audio), (last + 1 + pad_frames) * FRAME)
    kept = audio[start:end]
    if len(kept) < int(sample_rate * 0.12):
        return None
    return kept
