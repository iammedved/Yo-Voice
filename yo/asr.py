"""Локальный ASR: faster-whisper на GPU, русский язык."""

from __future__ import annotations

import threading
from collections.abc import Callable

import numpy as np

ProgressFn = Callable[[str], None]

# Без initial_prompt и без condition_on_previous_text: иначе Whisper
# подмешивает прошлую фразу / «продолжжение следует» как контекст.
TRANSCRIBE_OPTIONS = {
    "language": "ru",
    "beam_size": 5,
    "vad_filter": False,
    "condition_on_previous_text": False,
    "without_timestamps": True,
    "no_speech_threshold": 0.6,
    "log_prob_threshold": -1.0,
    "compression_ratio_threshold": 2.4,
    "temperature": 0.0,
}

def prepare_pcm(
    audio: np.ndarray,
    sample_rate: int = 16000,
    *,
    min_seconds: float = 0.18,
    min_level: float = 0.00055,
) -> np.ndarray | None:
    if audio is None or len(audio) < int(sample_rate * min_seconds):
        return None
    pcm = np.asarray(audio, dtype=np.float32)
    level = float(np.sqrt(np.mean(np.square(pcm)))) if len(pcm) else 0.0
    if level < min_level:
        return None
    if level < 0.08:
        pcm = pcm * min(22.0, 0.08 / max(level, 1e-6))
    peak = float(np.max(np.abs(pcm))) if len(pcm) else 0.0
    if peak > 0.99:
        pcm = pcm / peak * 0.99
    return pcm


class AsrEngine:
    def __init__(self, model_name: str = "large-v3-turbo", device: str = "auto") -> None:
        self.model_name = model_name
        self.device_pref = device
        self.model = None
        self.device = "cpu"
        self.error: str | None = None
        self._lock = threading.Lock()

    def loaded(self) -> bool:
        return self.model is not None

    def load(self, progress: ProgressFn | None = None) -> None:
        if self.model is not None:
            return
        from yo.cuda_env import setup_cuda_libs

        setup_cuda_libs()
        with self._lock:
            if self.model is not None:
                return
            if progress:
                progress("загрузка модели")
            from faster_whisper import WhisperModel

            device = self._pick_device()
            compute = "float16" if device == "cuda" else "int8"
            try:
                self.model = WhisperModel(self.model_name, device=device, compute_type=compute)
                self.device = device
                self.error = None
            except Exception as exc:
                if device != "cpu":
                    if progress:
                        progress("GPU недоступен, CPU")
                    self.model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
                    self.device = "cpu"
                    self.error = None
                else:
                    self.error = str(exc)
                    raise

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        if self.model is None:
            self.load()
        pcm = prepare_pcm(audio, sample_rate)
        if pcm is None:
            return ""
        with self._lock:
            segments, _info = self.model.transcribe(pcm, **TRANSCRIBE_OPTIONS)
            parts = [seg.text for seg in segments if keep_segment(seg)]
        return " ".join(p.strip() for p in parts if p and p.strip()).strip()

    def _pick_device(self) -> str:
        if self.device_pref in {"cuda", "cpu"}:
            return self.device_pref
        try:
            import ctranslate2

            if ctranslate2.get_cuda_device_count() > 0:
                return "cuda"
        except Exception:
            pass
        return "cpu"


def keep_segment(seg) -> bool:
    """GitHub/OpenAI: не брать сегменты с высокой no_speech_prob / слабым logprob."""
    text = (getattr(seg, "text", "") or "").strip()
    if not text:
        return False
    nsp = float(getattr(seg, "no_speech_prob", 0.0) or 0.0)
    logp = float(getattr(seg, "avg_logprob", 0.0) or 0.0)
    ratio = float(getattr(seg, "compression_ratio", 1.0) or 1.0)
    if nsp > 0.8:
        return False
    if nsp > 0.6 and logp < -0.5:
        return False
    if logp < -1.2:
        return False
    if ratio > 2.4:
        return False
    return True
