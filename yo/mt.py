"""Локальный перевод русского текста на английский: NLLB через CTranslate2."""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable

from yo.compute import choose_device, cpu_thread_count, cuda_device_count
from yo.paths import xdg_cache
from yo.polish import polish_ru

log = logging.getLogger("yo.mt")

ProgressFn = Callable[[str], None]
TranslateFn = Callable[[str], str]

SRC_LANG = "rus_Cyrl"
TGT_LANG = "eng_Latn"
CT2_REPO = "JustFrederik/nllb-200-distilled-600M-ct2-int8"
TOKENIZER_REPO = "facebook/nllb-200-distilled-600M"
MAX_CHUNK_CHARS = 400
TOKENIZER_PATTERNS = (
    "tokenizer.json",
    "tokenizer_config.json",
    "sentencepiece.bpe.model",
    "special_tokens_map.json",
    "added_tokens.json",
)

_SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+")


def split_mt_chunks(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    parts = [p.strip() for p in _SENTENCE_RE.split(text) if p.strip()]
    if not parts:
        parts = [text]
    chunks: list[str] = []
    buf = ""
    for part in parts:
        candidate = f"{buf} {part}".strip() if buf else part
        if buf and len(candidate) > max_chars:
            chunks.extend(_hard_split(buf, max_chars))
            buf = part
        else:
            buf = candidate
    if buf:
        chunks.extend(_hard_split(buf, max_chars))
    return [c for c in chunks if c]


def _hard_split(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]


def english_from_russian_asr(raw: str, translate_ru_en: TranslateFn) -> str:
    russian = polish_ru(raw, finalize=True)
    if not russian:
        return ""
    return (translate_ru_en(russian) or "").strip()


class LocalTranslator:
    def __init__(self, device: str = "auto") -> None:
        self.device_pref = device
        self.device = "cpu"
        self.error: str | None = None
        self._translator = None
        self._tokenizer = None
        self._lock = threading.Lock()

    def loaded(self) -> bool:
        return self._translator is not None and self._tokenizer is not None

    def load(self, progress: ProgressFn | None = None) -> None:
        if self.loaded():
            return
        import logging as _logging

        from huggingface_hub import snapshot_download
        import ctranslate2

        _logging.getLogger("transformers").setLevel(_logging.ERROR)
        from transformers import AutoTokenizer

        cache = xdg_cache() / "huggingface"
        with self._lock:
            if self.loaded():
                return
            if progress:
                progress("загрузка перевода")
            from yo.logutil import hush_progress_bars

            hush_progress_bars()

            def _snap(repo: str, **kwargs):
                try:
                    return snapshot_download(repo, local_files_only=True, cache_dir=str(cache), **kwargs)
                except Exception:
                    return snapshot_download(repo, cache_dir=str(cache), **kwargs)

            model_dir = _snap(CT2_REPO)
            tok_dir = _snap(TOKENIZER_REPO, allow_patterns=list(TOKENIZER_PATTERNS))
            tokenizer = AutoTokenizer.from_pretrained(tok_dir, src_lang=SRC_LANG)
            device = self._pick_device()
            translator = None
            if device != "cpu":
                from yo.cuda_env import setup_cuda_libs

                setup_cuda_libs()
                try:
                    translator = ctranslate2.Translator(model_dir, device=device)
                    translator.translate_batch([[SRC_LANG]], target_prefix=[[TGT_LANG]], max_decoding_length=8)
                    self.device = device
                except Exception:
                    translator = None
                    if progress:
                        progress("GPU недоступен, CPU")
            if translator is None:
                threads = cpu_thread_count()
                translator = ctranslate2.Translator(
                    model_dir,
                    device="cpu",
                    intra_threads=threads,
                    inter_threads=1,
                )
                self.device = "cpu"
                log.info("перевод на процессоре: потоков %s", threads)
            self._tokenizer = tokenizer
            self._translator = translator
            self.error = None
            log.info("NLLB загружен device=%s", self.device)

    def translate_ru_en(self, text: str) -> str:
        text = (text or "").strip()
        if not text:
            return ""
        if not self.loaded():
            self.load()
        chunks = split_mt_chunks(text)
        parts = [self._translate_chunk(chunk) for chunk in chunks]
        return " ".join(p for p in parts if p).strip()

    def _translate_chunk(self, chunk: str) -> str:
        tokenizer = self._tokenizer
        translator = self._translator
        if tokenizer is None or translator is None:
            return ""
        tokenizer.src_lang = SRC_LANG
        source = tokenizer.convert_ids_to_tokens(tokenizer.encode(chunk))
        with self._lock:
            results = translator.translate_batch(
                [source],
                target_prefix=[[TGT_LANG]],
                beam_size=4,
                max_decoding_length=512,
            )
        hyp = list(results[0].hypotheses[0]) if results and results[0].hypotheses else []
        if hyp and hyp[0] == TGT_LANG:
            hyp = hyp[1:]
        ids = tokenizer.convert_tokens_to_ids(hyp)
        return tokenizer.decode(ids, skip_special_tokens=True).strip()

    def _pick_device(self) -> str:
        return choose_device(self.device_pref, cuda_device_count())
