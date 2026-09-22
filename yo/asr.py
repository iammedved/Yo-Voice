"""Локальный ASR: faster-whisper на GPU, русский язык."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

import numpy as np

from yo.compute import choose_device, cpu_model_kwargs, cuda_device_count, windows_adapter_names

log = logging.getLogger("yo.asr")

ProgressFn = Callable[[str], None]

DEFAULT_MODEL = "coriollon/whisper-large-v3-turbo-russian"
LEGACY_TURBO = "large-v3-turbo"
CODESWITCH_MODEL = "coriollon/whisper-large-v3-turbo-russian-codeswitch"
RU_TURBO_CT2 = "ct2_int8_float16"

# Без initial_prompt, без hotwords и без condition_on_previous_text:
# иначе Whisper подмешивает бренды / прошлую фразу как контекст.
TRANSCRIBE_OPTIONS = {
    "language": "ru",
    "beam_size": 5,
    "vad_filter": False,
    "condition_on_previous_text": False,
    "without_timestamps": True,
    "no_speech_threshold": 0.72,
    "log_prob_threshold": -1.0,
    "compression_ratio_threshold": 2.4,
    "temperature": 0.0,
}


def resolve_asr_model(name: str | None) -> str:
    if not name or name == LEGACY_TURBO:
        return DEFAULT_MODEL
    return name


def uses_russian_ct2(name: str | None) -> bool:
    return "whisper-large-v3-turbo-russian" in resolve_asr_model(name)


def whisper_compute_type(device: str, model_name: str | None) -> str:
    if device == "cuda" and uses_russian_ct2(model_name):
        return "int8_float16"
    if device == "cuda":
        return "float16"
    return "int8"


def resolve_whisper_path(model_name: str | None, download=None) -> str:
    name = resolve_asr_model(model_name)
    if not uses_russian_ct2(name):
        return name
    downloader = download or _hf_snapshot
    root = downloader(repo_id=name, allow_patterns=[f"{RU_TURBO_CT2}/*"])
    return str(Path(root) / RU_TURBO_CT2)


def _hf_snapshot(*, repo_id: str, allow_patterns):
    from huggingface_hub import snapshot_download

    from yo.logutil import hush_progress_bars

    hush_progress_bars()
    kwargs = {"repo_id": repo_id, "allow_patterns": allow_patterns, "max_workers": 1}
    try:
        return snapshot_download(local_files_only=True, **kwargs)
    except Exception:
        return snapshot_download(**kwargs)


def prepare_pcm(
    audio: np.ndarray,
    sample_rate: int = 16000,
    *,
    min_seconds: float = 0.18,
    min_level: float = 0.00016,
) -> np.ndarray | None:
    if audio is None or len(audio) < int(sample_rate * min_seconds):
        return None
    pcm = np.asarray(audio, dtype=np.float32)
    pcm = pcm - float(np.mean(pcm))
    level = float(np.sqrt(np.mean(np.square(pcm)))) if len(pcm) else 0.0
    if level < min_level:
        return None
    if level < 0.05:
        pcm = pcm * min(40.0, 0.05 / max(level, 1e-6))
    peak = float(np.max(np.abs(pcm))) if len(pcm) else 0.0
    if peak > 0.99:
        pcm = pcm / peak * 0.99
    return pcm


class AsrEngine:
    def __init__(self, model_name: str = DEFAULT_MODEL, device: str = "auto") -> None:
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
        with self._lock:
            if self.model is not None:
                return
            if progress:
                progress("загрузка модели")
            from faster_whisper import WhisperModel

            device = self._pick_device()
            if device == "cuda":
                from yo.cuda_env import setup_cuda_libs

                setup_cuda_libs()
            else:
                threads = cpu_model_kwargs()["cpu_threads"]
                names = ", ".join(windows_adapter_names())
                if names:
                    log.info(
                        "распознавание на процессоре: int8, потоков %s. Видеокарты NVIDIA нет (%s). Встроенная графика не используется.",
                        threads,
                        names,
                    )
                else:
                    log.info(
                        "распознавание на процессоре: int8, потоков %s. Видеокарты NVIDIA нет. Встроенная графика не используется.",
                        threads,
                    )
            path = resolve_whisper_path(self.model_name)
            compute = whisper_compute_type(device, self.model_name)
            try:
                self.model = WhisperModel(path, **_whisper_kwargs(device, compute))
                self.device = device
                self.error = None
            except Exception as exc:
                if device != "cpu":
                    if progress:
                        progress("GPU недоступен, CPU")
                    log.warning("CUDA не поднялась, распознавание на процессоре: %s", exc)
                    self.model = WhisperModel(path, **_whisper_kwargs("cpu", "int8"))
                    self.device = "cpu"
                    self.error = None
                else:
                    self.error = str(exc)
                    raise

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000, *, task: str = "transcribe") -> str:
        if self.model is None:
            self.load()
        pcm = prepare_pcm(audio, sample_rate)
        if pcm is None:
            return ""
        options = dict(TRANSCRIBE_OPTIONS)
        # task= оставлен у вызова: перевод делает локальный NLLB, Whisper всегда пишет русский.
        options["task"] = "transcribe"
        with self._lock:
            segments, _info = self.model.transcribe(pcm, **options)
            parts = [seg.text for seg in segments if keep_segment(seg)]
        return " ".join(p.strip() for p in parts if p and p.strip()).strip()

    def _pick_device(self) -> str:
        return choose_device(self.device_pref, cuda_device_count())


def _whisper_kwargs(device: str, compute: str) -> dict:
    kwargs: dict = {"device": device, "compute_type": compute}
    if device == "cpu":
        kwargs.update(cpu_model_kwargs())
    return kwargs


def keep_segment(seg) -> bool:
    """GitHub/OpenAI: не брать сегменты с высокой no_speech_prob / слабым logprob."""
    text = (getattr(seg, "text", "") or "").strip()
    if not text:
        return False
    nsp = float(getattr(seg, "no_speech_prob", 0.0) or 0.0)
    logp = float(getattr(seg, "avg_logprob", 0.0) or 0.0)
    ratio = float(getattr(seg, "compression_ratio", 1.0) or 1.0)
    if nsp > 0.88:
        return False
    if nsp > 0.7 and logp < -0.6:
        return False
    if logp < -1.2:
        return False
    if ratio > 2.4:
        return False
    return True
