"""Сессия диктовки: слушает, отдаёт фразы в активное поле."""

from __future__ import annotations

from collections.abc import Callable

from yo.polish import polish_ru

InjectFn = Callable[[str], None]


def accept_asr_commit(
    *,
    token: int,
    current_token: int,
    listening: bool,
    stopping: bool,
) -> bool:
    """Keep every chunk of this listen session; drop only a previous session."""
    if token != current_token:
        return False
    return listening or stopping


_ENDINGS = (
    "ами",
    "ями",
    "ого",
    "его",
    "ому",
    "ему",
    "ыми",
    "ими",
    "ых",
    "их",
    "ой",
    "ый",
    "ая",
    "ое",
    "ые",
    "ие",
    "ую",
    "юю",
    "ов",
    "ев",
    "ей",
    "ом",
    "ем",
    "ах",
    "ях",
    "ам",
    "ям",
    "а",
    "я",
    "у",
    "ю",
    "е",
    "и",
    "о",
    "ы",
    "ь",
)


def _norm_word(word: str) -> str:
    return word.lower().strip(".,!?;:…«»\"'()[]")


def _stem(word: str) -> str:
    w = _norm_word(word)
    for end in _ENDINGS:
        if len(w) - len(end) >= 4 and w.endswith(end):
            return w[: -len(end)]
    return w


def _same_token(left: str, right: str) -> bool:
    a, b = _norm_word(left), _norm_word(right)
    if a == b:
        return True
    if min(len(a), len(b)) < 5:
        return False
    if _stem(a) == _stem(b):
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) >= 6 and longer.endswith(shorter) and len(longer) - len(shorter) <= 3:
        return True
    return False


def _dedupe_variants(words: list[str]) -> list[str]:
    out: list[str] = []
    for word in words:
        if out and _same_token(out[-1], word):
            continue
        out.append(word)
    return out


class DictationSession:
    def __init__(self, inject: InjectFn) -> None:
        self._inject = inject
        self.listening = False
        self._first_inject = True

    def start(self) -> None:
        self.listening = True
        self._first_inject = True

    def stop(self) -> None:
        self.listening = False

    def commit_utterance(self, hypothesis: str) -> str:
        if not self.listening:
            return ""
        polished = polish_ru(hypothesis, finalize=True)
        words = _dedupe_variants(polished.split())
        if not words:
            return ""
        text = " ".join(words)
        payload = text if self._first_inject else f" {text}"
        self._first_inject = False
        self._inject(payload)
        return payload
