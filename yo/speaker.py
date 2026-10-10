"""Только мой голос: отпечаток голоса и отсев чужой речи до Whisper.

A small on-device speaker model (WeSpeaker ResNet34, ONNX, ~26 MB) turns a
stretch of speech into a 256-number voiceprint. The user records a sample
once; afterwards every phrase is cut into short windows, each window is
compared with the saved voiceprint, and only windows that sound like the
user reach recognition. Nothing leaves this computer.

Overlapping voices (the user and a TV at the same moment) cannot be pulled
apart this way: the window is kept or dropped as a whole.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path

import numpy as np

log = logging.getLogger("yo.speaker")

SAMPLE_RATE = 16000
MODEL_NAME = "wespeaker_en_voxceleb_resnet34_LM.onnx"
MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
    "speaker-recongition-models/wespeaker_en_voxceleb_resnet34_LM.onnx"
)
MODEL_SHA256 = "e9848563da86f263117134dfd7ad63c92355b37de492b55e325400c9d9c39012"
MODEL_ID = "wespeaker-resnet34-lm"

# Cosine similarity to the voiceprint. Same person on another day and mic
# usually scores 0.5-0.8 with this model, other people 0.0-0.3.
DEFAULT_THRESHOLD = 0.40
WINDOW_S = 1.5
HOP_S = 0.75
# A phrase shorter than this is scored as one piece.
WHOLE_CLIP_S = 2.0
MIN_SCORED_S = 0.5
JOIN_GAP_S = 0.2
ENROLL_CHUNK_S = 3.0
ENROLL_MIN_SPEECH_S = 8.0
ENROLL_SECONDS = 25.0

ENROLL_TEXT = (
    "Выключите телевизор и музыку: записываться должен только ваш голос.\n"
    "Прочитайте вслух обычным голосом, как будто диктуете:\n\n"
    "«Сегодня я проверяю голосовой ввод. Программа должна слушать только меня "
    "и не обращать внимания на телевизор, музыку и чужие разговоры. "
    "Раз, два, три, четыре, пять. Съешь же ещё этих мягких французских булок "
    "да выпей чаю. Если я говорю тихо или быстро, это всё равно мой голос.»"
)

NO_SAMPLE_HINT = "запишите свой голос"

ProgressFn = Callable[[str], None]


# --- features -------------------------------------------------------------

_FRAME_LEN = 400  # 25 ms
_FRAME_SHIFT = 160  # 10 ms
_NFFT = 512
_NUM_MELS = 80
_EPS = float(np.finfo(np.float32).eps)


def _mel(freq):
    return 1127.0 * np.log(1.0 + np.asarray(freq, dtype=np.float64) / 700.0)


def _mel_banks() -> np.ndarray:
    """Kaldi triangular mel filters, 20 Hz to Nyquist, as in torchaudio's kaldi.fbank."""
    bin_width = SAMPLE_RATE / _NFFT
    low, high = _mel(20.0), _mel(SAMPLE_RATE / 2.0)
    delta = (high - low) / (_NUM_MELS + 1)
    fft_mel = _mel(bin_width * np.arange(_NFFT // 2))
    left = low + delta * np.arange(_NUM_MELS)[:, None]
    center = left + delta
    right = center + delta
    up = (fft_mel[None, :] - left) / (center - left)
    down = (right - fft_mel[None, :]) / (right - center)
    banks = np.maximum(0.0, np.minimum(up, down))
    # Nyquist bin carries no weight.
    return np.pad(banks, ((0, 0), (0, 1))).astype(np.float32)


_BANKS = _mel_banks()
_WINDOW = (0.54 - 0.46 * np.cos(2 * np.pi * np.arange(_FRAME_LEN) / (_FRAME_LEN - 1))).astype(np.float32)


def fbank(pcm: np.ndarray) -> np.ndarray:
    """80-dim log-mel filterbank, Kaldi defaults, mean-normalized over time.

    Input is float PCM in [-1, 1] at 16 kHz; the model was trained on int16
    scale, so the samples are multiplied by 32768 first.
    """
    x = np.asarray(pcm, dtype=np.float32) * 32768.0
    if len(x) < _FRAME_LEN:
        return np.zeros((0, _NUM_MELS), dtype=np.float32)
    count = 1 + (len(x) - _FRAME_LEN) // _FRAME_SHIFT
    idx = np.arange(_FRAME_LEN)[None, :] + _FRAME_SHIFT * np.arange(count)[:, None]
    frames = x[idx]
    frames = frames - frames.mean(axis=1, keepdims=True)
    prev = np.concatenate([frames[:, :1], frames[:, :-1]], axis=1)
    frames = (frames - 0.97 * prev) * _WINDOW
    spec = np.fft.rfft(frames, n=_NFFT, axis=1)
    power = (spec.real**2 + spec.imag**2).astype(np.float32)
    feats = np.log(np.maximum(power @ _BANKS.T, _EPS))
    feats = feats - feats.mean(axis=0, keepdims=True)
    return feats.astype(np.float32)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float32).reshape(-1)
    b = np.asarray(b, dtype=np.float32).reshape(-1)
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na <= 1e-9 or nb <= 1e-9:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


# --- model ----------------------------------------------------------------


def model_path() -> Path:
    from yo.paths import xdg_cache

    return xdg_cache() / "speaker" / MODEL_NAME


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def model_ready(path: Path | None = None) -> bool:
    file = path or model_path()
    try:
        return file.is_file() and file.stat().st_size > 1_000_000
    except OSError:
        return False


def ensure_model(progress: ProgressFn | None = None, *, path: Path | None = None, url: str = MODEL_URL) -> Path:
    """Download the speaker model once; the file is checked against its hash."""
    file = path or model_path()
    if model_ready(file):
        return file
    file.parent.mkdir(parents=True, exist_ok=True)
    tmp = file.with_name(file.name + ".part")
    log.info("скачиваю модель голоса %s", url)
    with urllib.request.urlopen(url, timeout=60) as resp, tmp.open("wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        last = 0.0
        while True:
            block = resp.read(1 << 16)
            if not block:
                break
            out.write(block)
            done += len(block)
            now = time.monotonic()
            if progress is not None and (now - last > 0.25):
                last = now
                mb = done / 1e6
                progress(f"модель голоса: {mb:.0f} из {total / 1e6:.0f} МБ" if total else f"модель голоса: {mb:.0f} МБ")
    if _sha256(tmp) != MODEL_SHA256:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("модель голоса скачалась с ошибкой, попробуйте ещё раз")
    os.replace(tmp, file)
    return file


class SpeakerEncoder:
    """ONNX speaker embedding model, loaded on first use."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._session = None
        self._lock = threading.Lock()

    def _load(self):
        if self._session is None:
            import onnxruntime as ort

            opts = ort.SessionOptions()
            opts.inter_op_num_threads = 1
            opts.intra_op_num_threads = 2
            self._session = ort.InferenceSession(
                str(self.path or model_path()),
                providers=["CPUExecutionProvider"],
                sess_options=opts,
            )
        return self._session

    def embed_many(self, clips: list[np.ndarray]) -> np.ndarray:
        """One embedding per clip. Clips of equal length run as one batch."""
        out: list[np.ndarray | None] = [None] * len(clips)
        groups: dict[int, list[int]] = {}
        for i, clip in enumerate(clips):
            groups.setdefault(len(clip), []).append(i)
        with self._lock:
            session = self._load()
            for _n, members in groups.items():
                feats = np.stack([fbank(clips[i]) for i in members])
                if feats.shape[1] == 0:
                    for i in members:
                        out[i] = np.zeros(256, dtype=np.float32)
                    continue
                embs = session.run(None, {"feats": feats})[0]
                for i, emb in zip(members, embs):
                    out[i] = np.asarray(emb, dtype=np.float32)
        return np.stack(out) if out else np.zeros((0, 256), dtype=np.float32)

    def embed(self, clip: np.ndarray) -> np.ndarray:
        return self.embed_many([clip])[0]


# --- voiceprint -----------------------------------------------------------


def voiceprint_path() -> Path:
    from yo.paths import xdg_config

    return xdg_config() / "voiceprint.json"


def save_voiceprint(vector: np.ndarray, *, quality: float, seconds: float, path: Path | None = None) -> None:
    file = path or voiceprint_path()
    vec = np.asarray(vector, dtype=np.float32).reshape(-1)
    payload = {
        "model": MODEL_ID,
        "vector": [round(float(v), 6) for v in vec],
        "quality": round(float(quality), 4),
        "seconds": round(float(seconds), 1),
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    tmp = file.with_name(file.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, file)


def load_voiceprint(path: Path | None = None) -> np.ndarray | None:
    file = path or voiceprint_path()
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception:
        log.warning("битый отпечаток голоса %s", file)
        return None
    if not isinstance(data, dict) or data.get("model") != MODEL_ID:
        return None
    try:
        vec = np.asarray(data.get("vector") or [], dtype=np.float32)
    except (TypeError, ValueError):
        return None
    if vec.ndim != 1 or vec.size == 0 or not np.all(np.isfinite(vec)) or float(np.linalg.norm(vec)) <= 1e-9:
        return None
    return vec / np.linalg.norm(vec)


def has_voiceprint(path: Path | None = None) -> bool:
    return load_voiceprint(path) is not None


def build_voiceprint(speech: np.ndarray, encoder: SpeakerEncoder) -> tuple[np.ndarray, float]:
    """Average the embeddings of 3 s chunks of the user's speech.

    Returns the unit voiceprint and the lowest chunk score against it; a
    low value means the sample had noise or another voice in it.
    """
    pcm = np.asarray(speech, dtype=np.float32)
    step = int(ENROLL_CHUNK_S * SAMPLE_RATE)
    chunks = [pcm[i : i + step] for i in range(0, len(pcm) - step + 1, step)]
    if not chunks:
        chunks = [pcm]
    embs = encoder.embed_many(chunks)
    norms = np.linalg.norm(embs, axis=1, keepdims=True)
    embs = embs / np.maximum(norms, 1e-9)
    mean = embs.mean(axis=0)
    mean = mean / max(float(np.linalg.norm(mean)), 1e-9)
    quality = min(cosine(e, mean) for e in embs)
    return mean.astype(np.float32), float(quality)


# --- gating ---------------------------------------------------------------


def _windows(n: int, sample_rate: int) -> list[tuple[int, int]]:
    win = int(WINDOW_S * sample_rate)
    hop = int(HOP_S * sample_rate)
    if n <= int(WHOLE_CLIP_S * sample_rate):
        return [(0, n)]
    starts = list(range(0, n - win + 1, hop))
    if starts[-1] + win < n:
        starts.append(n - win)
    return [(s, s + win) for s in starts]


def slot_scores(n: int, spans: list[tuple[int, int]], scores: list[float], slot: int) -> list[float]:
    """Score each hop-long slot by the mean of the windows that cover it.

    Deciding per slot instead of per window keeps a neighbour's voice from
    riding in on the edge of a 1.5 s window that was mostly the user.
    """
    out: list[float] = []
    for a in range(0, n, slot):
        b = min(n, a + slot)
        covering = [s for (lo, hi), s in zip(spans, scores) if lo < b and hi > a]
        out.append(float(np.mean(covering)) if covering else 0.0)
    return out


def own_voice_only(
    pcm: np.ndarray | None,
    voiceprint: np.ndarray,
    encoder: SpeakerEncoder,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    sample_rate: int = SAMPLE_RATE,
) -> tuple[np.ndarray | None, list[float]]:
    """Keep only the parts of a phrase that match the voiceprint.

    Returns the kept audio (None if nothing is the user) and the window
    scores for the log.
    """
    if pcm is None:
        return None, []
    audio = np.asarray(pcm, dtype=np.float32)
    if len(audio) < int(MIN_SCORED_S * sample_rate):
        # Too short to establish identity; do not let brief TV words bypass it.
        return None, []
    spans = _windows(len(audio), sample_rate)
    embs = encoder.embed_many([audio[a:b] for a, b in spans])
    scores = [cosine(e, voiceprint) for e in embs]
    if len(spans) == 1:
        return (audio if scores[0] >= threshold else None), scores
    slot = int(HOP_S * sample_rate)
    keep = [s >= threshold for s in slot_scores(len(audio), spans, scores, slot)]
    if not any(keep):
        return None, scores
    if all(keep):
        return audio, scores
    pieces: list[np.ndarray] = []
    gap = np.zeros(int(JOIN_GAP_S * sample_rate), dtype=np.float32)
    i = 0
    while i < len(keep):
        if not keep[i]:
            i += 1
            continue
        j = i
        while j < len(keep) and keep[j]:
            j += 1
        if pieces:
            pieces.append(gap)
        pieces.append(audio[i * slot : min(len(audio), j * slot)])
        i = j
    return np.concatenate(pieces), scores


class SpeakerFilter:
    """Only verified speech passes while the user has enabled this filter."""

    def __init__(self, encoder: SpeakerEncoder | None = None) -> None:
        self.encoder = encoder or SpeakerEncoder()
        self._print: np.ndarray | None = None
        self._print_mtime: float | None = None
        self._print_path: Path | None = None
        self._warned = False
        # True when input is blocked because the sample/model is missing.
        self.missing_sample = False

    def _voiceprint(self, path: Path | None = None) -> np.ndarray | None:
        file = path or voiceprint_path()
        try:
            mtime = file.stat().st_mtime
        except OSError:
            self._print = None
            self._print_mtime = None
            return None
        if self._print is None or mtime != self._print_mtime or file != self._print_path:
            self._print = load_voiceprint(file)
            self._print_mtime = mtime
            self._print_path = file
        return self._print

    def apply(self, pcm: np.ndarray | None, *, threshold: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray | None:
        voiceprint = self._voiceprint()
        self.missing_sample = voiceprint is None or not model_ready(self.encoder.path)
        if self.missing_sample:
            if not self._warned:
                self._warned = True
                log.warning("«только мой голос»: нет образца или модели — речь заблокирована")
            return None
        try:
            kept, scores = own_voice_only(
                pcm, voiceprint, self.encoder, threshold=threshold, sample_rate=sample_rate
            )
        except Exception as exc:
            raise RuntimeError("Не удалось проверить голос — фраза заблокирована") from exc
        if scores:
            log.info(
                "голос: %s порог=%.2f → %s",
                " ".join(f"{s:.2f}" for s in scores),
                threshold,
                "чужой" if kept is None else ("свой" if pcm is not None and len(kept) == len(pcm) else "частично"),
            )
        return kept


# --- enrollment -----------------------------------------------------------


def enroll_from_pcm(
    pcm: np.ndarray,
    *,
    encoder: SpeakerEncoder | None = None,
    sample_rate: int = SAMPLE_RATE,
    path: Path | None = None,
) -> tuple[float, float]:
    """Trim silence, build and save the voiceprint. Returns (quality, speech seconds)."""
    from yo.vad import trim_to_speech

    speech = trim_to_speech(pcm, sample_rate, backend="auto", pad_ms=0.0)
    seconds = 0.0 if speech is None else len(speech) / float(sample_rate)
    if speech is None or seconds < ENROLL_MIN_SPEECH_S:
        raise ValueError(
            f"мало речи в образце ({seconds:.0f} с из нужных {ENROLL_MIN_SPEECH_S:.0f}) — "
            "говорите ближе к микрофону и дочитайте текст"
        )
    vector, quality = build_voiceprint(speech, encoder or SpeakerEncoder())
    save_voiceprint(vector, quality=quality, seconds=seconds, path=path)
    return quality, seconds


def open_capture(capture, microphone: str = "") -> int | None:
    """Open the dictation mic the way the app does: every host-API copy of
    the chosen device (WASAPI first), shared mode
    before exclusive. One driver refusing (WDM-KS) must not stop the sample.
    """
    import sys

    from yo.capture import capture_candidate_indices

    try:
        candidates: list[int | None] = list(capture_candidate_indices(microphone))
    except Exception:
        candidates = []
    if not microphone and None not in candidates:
        candidates.append(None)
    modes = [False, True] if sys.platform == "win32" else [False]
    first_error: Exception | None = None
    for exclusive in modes:
        for device in candidates:
            try:
                capture.start(device=device, exclusive=exclusive)
                log.info("образец голоса: микрофон %s exclusive=%s", device, exclusive)
                return device
            except Exception as exc:
                log.warning("образец голоса: device=%s exclusive=%s: %s", device, exclusive, exc)
                if first_error is None:
                    first_error = exc
    raise RuntimeError(f"не удалось открыть микрофон: {first_error}")


def record_pcm(
    seconds: float,
    microphone: str = "",
    *,
    on_level: Callable[[float, float], None] | None = None,
    capture_factory=None,
) -> np.ndarray:
    """Record 16 kHz mono from the dictation mic, reporting (elapsed, rms)."""
    if capture_factory is None:
        from yo.audio import AudioCapture

        capture_factory = AudioCapture
    chunks: list[np.ndarray] = []
    clock = {"start": time.monotonic()}

    def on_block(pcm, level, _bands) -> None:
        chunks.append(np.asarray(pcm, dtype=np.float32).copy())
        if on_level is not None:
            try:
                on_level(time.monotonic() - clock["start"], float(level))
            except Exception:
                pass

    capture = capture_factory(on_block, sample_rate=SAMPLE_RATE)
    open_capture(capture, microphone)
    clock["start"] = time.monotonic()
    try:
        while time.monotonic() - clock["start"] < seconds:
            time.sleep(0.05)
    finally:
        capture.stop(drain=False)
    if not chunks:
        raise RuntimeError("микрофон не дал звука — проверьте, что он включён")
    return np.concatenate(chunks)


def run_enrollment(
    progress: ProgressFn,
    *,
    microphone: str = "",
    seconds: float = ENROLL_SECONDS,
) -> tuple[float, float]:
    """Download the model, record the user reading, save the voiceprint.

    Returns (quality, speech seconds). Raises with a message for the user.
    """
    ensure_model(progress)
    progress("говорите…")

    def on_level(elapsed: float, _level: float) -> None:
        left = max(0, int(round(seconds - elapsed)))
        progress(f"говорите… осталось {left} с")

    pcm = record_pcm(seconds, microphone, on_level=on_level)
    progress("сохраняю отпечаток голоса…")
    return enroll_from_pcm(pcm)


def quality_note(quality: float) -> str:
    if quality >= 0.6:
        return "образец чистый"
    return "в образце был шум или чужой голос — лучше перезаписать в тишине"
