"""Потоковый VAD: Silero ONNX, запасной EnergyVad. В Whisper только речь."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import numpy as np

from yo.spectrum import EnergyVad, rms

log = logging.getLogger("yo.vad")

FRAME = 512
CONTEXT = 64
SAMPLE_RATE = 16000
START_MS = 40.0
END_MS = 1100.0
# Silero probability drops with amplitude; 0.45 only fires on loud/normal talk.
SILERO_START = 0.28
SILERO_CONTINUE = 0.16
ENERGY_FRAME_THRESH = 0.00035
ENERGY_ASSIST = 0.0007
# One 32 ms click is louder than ENERGY_ASSIST. It must not zero the endpoint.
ENERGY_ASSIST_HOLD_MS = 128.0
VAD_TARGET_RMS = 0.04
VAD_MAX_GAIN = 20.0
# Bridge a short breath; do not keep the minute between two clicks.
GAP_BRIDGE_FRAMES = 6
MIN_ISLAND_FRAMES = 3
ISLAND_JOIN_MS = 200.0


def silero_model_path() -> Path:
    """Locate silero_vad.onnx in a source tree, installed package, or frozen bundle."""
    from yo.paths import project_root

    candidates: list[Path] = []
    try:
        from importlib.resources import files

        resource = files("yo").joinpath("data", "silero_vad.onnx")
        try:
            candidates.append(Path(os.fspath(resource)))
        except TypeError:
            pass
    except (ModuleNotFoundError, FileNotFoundError, OSError, ValueError):
        pass
    candidates.append(project_root() / "yo" / "data" / "silero_vad.onnx")
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        base = Path(meipass)
        candidates.append(base / "yo" / "data" / "silero_vad.onnx")
        candidates.append(base / "data" / "silero_vad.onnx")
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "yo" / "data" / "silero_vad.onnx")
        candidates.append(exe_dir / "_internal" / "yo" / "data" / "silero_vad.onnx")
        candidates.append(exe_dir / "data" / "silero_vad.onnx")
    file = globals().get("__file__")
    if file:
        try:
            candidates.append(Path(file).resolve().parent / "data" / "silero_vad.onnx")
        except OSError:
            pass
    seen: set[str] = set()
    first: Path | None = None
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if first is None:
            first = path
        try:
            if path.is_file():
                return path
        except OSError:
            continue
    log.warning("silero_vad.onnx не найден, пробовал %s", list(seen)[:8])
    return first if first is not None else Path("silero_vad.onnx")


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


def boost_for_vad(frame: np.ndarray) -> np.ndarray:
    """Raise quiet speech to a level Silero can score; stored PCM is unchanged."""
    pcm = np.asarray(frame, dtype=np.float32)
    level = rms(pcm)
    if level <= 1e-8 or level >= VAD_TARGET_RMS:
        return pcm
    gain = min(VAD_MAX_GAIN, VAD_TARGET_RMS / level)
    return np.clip(pcm * gain, -1.0, 1.0).astype(np.float32)


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
        self._energy_ms = 0.0
        self._buf = np.zeros(0, dtype=np.float32)

    def reset(self) -> None:
        self._energy = EnergyVad()
        if self._silero is not None:
            self._silero.reset()
        self.speaking = False
        self._speech_ms = 0.0
        self._silence_ms = 0.0
        self._energy_ms = 0.0
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
        saw_end = False
        while len(self._buf) >= FRAME:
            frame = self._buf[:FRAME]
            self._buf = self._buf[FRAME:]
            last = self._step_silero(frame)
            if last == "end":
                saw_end = True
        # A later frame in the same callback must not hide an endpoint.
        return "end" if saw_end else last

    def _step_silero(self, frame: np.ndarray) -> str:
        assert self._silero is not None
        dt_ms = 1000.0 * FRAME / float(SAMPLE_RATE)
        prob = self._silero.prob(boost_for_vad(frame))
        thresh = SILERO_CONTINUE if self.speaking else SILERO_START
        if prob >= thresh:
            self._energy_ms = 0.0
            is_speech = True
        elif rms(frame) > ENERGY_ASSIST:
            self._energy_ms += dt_ms
            is_speech = self._energy_ms >= ENERGY_ASSIST_HOLD_MS
        else:
            self._energy_ms = 0.0
            is_speech = False
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
                self._energy_ms = 0.0
                return "end"
            return "speech"
        return "silence"


def _bridge_short_gaps(mask: list[bool], bridge: int) -> list[bool]:
    if bridge <= 0 or not mask:
        return list(mask)
    out = list(mask)
    i = 0
    n = len(mask)
    while i < n:
        if mask[i]:
            i += 1
            continue
        j = i
        while j < n and not mask[j]:
            j += 1
        if i > 0 and j < n and mask[i - 1] and mask[j] and (j - i) <= bridge:
            for k in range(i, j):
                out[k] = True
        i = j
    return out


def _speech_islands(mask: list[bool], min_frames: int) -> list[tuple[int, int]]:
    islands: list[tuple[int, int]] = []
    i = 0
    n = len(mask)
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i + 1
        while j < n and mask[j]:
            j += 1
        if j - i >= min_frames:
            islands.append((i, j))
        i = j
    return islands


def _or_masks(left: list[bool], right: list[bool]) -> list[bool]:
    n = min(len(left), len(right))
    if n == 0:
        return left or right
    return [left[i] or right[i] for i in range(n)]


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
        prob = backend.prob(boost_for_vad(chunk))
        thresh = SILERO_CONTINUE if speaking else SILERO_START
        speaking = prob >= thresh
        mask.append(speaking)
    return mask


def trim_to_speech(
    pcm: np.ndarray | None,
    sample_rate: int = SAMPLE_RATE,
    backend: str | None = "auto",
    pad_ms: float = 400.0,
) -> np.ndarray | None:
    if pcm is None or len(pcm) < int(sample_rate * 0.12):
        return None
    audio = np.asarray(pcm, dtype=np.float32)
    requested = backend or "auto"
    mask: list[bool]
    energy = _energy_mask(audio, sample_rate)
    if requested != "energy":
        silero = _try_silero()
        if silero is not None:
            mask = _or_masks(_silero_mask(audio, silero), energy)
        else:
            mask = energy
    else:
        mask = energy
    if not any(mask):
        return None
    islands = _speech_islands(_bridge_short_gaps(mask, GAP_BRIDGE_FRAMES), MIN_ISLAND_FRAMES)
    if not islands:
        return None
    pad_frames = max(0, int(round(pad_ms / (1000.0 * FRAME / float(sample_rate)))))
    keep = [False] * len(mask)
    for start_i, end_i in islands:
        lo = max(0, start_i - pad_frames)
        hi = min(len(mask), end_i + pad_frames)
        for k in range(lo, hi):
            keep[k] = True
    pieces: list[np.ndarray] = []
    join_n = int(sample_rate * ISLAND_JOIN_MS / 1000.0)
    i = 0
    n = len(keep)
    while i < n:
        if not keep[i]:
            j = i + 1
            while j < n and not keep[j]:
                j += 1
            if pieces and j < n and join_n > 0:
                pieces.append(np.zeros(join_n, dtype=np.float32))
            i = j
            continue
        j = i + 1
        while j < n and keep[j]:
            j += 1
        a = i * FRAME
        b = min(len(audio), j * FRAME)
        if b > a:
            pieces.append(audio[a:b])
        i = j
    if not pieces:
        return None
    kept = pieces[0] if len(pieces) == 1 else np.concatenate(pieces)
    if len(kept) < int(sample_rate * 0.12):
        return None
    return kept
