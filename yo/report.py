"""Отчёт о сбое: поля для пользователя и ссылка на новую задачу GitHub."""

from __future__ import annotations

import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlencode

ISSUE_NEW = "https://github.com/iammedved/Yo-Voice/issues/new"
DETAIL_LIMIT = 1200
UNKNOWN_WHY = "Причина не определена"

_WHY_MODEL = "Речевая модель отсутствует или загрузка не удалась."
_WHY_CUDA = "Библиотека NVIDIA не запустилась, распознавание может перейти на процессор."
_WHY_MIC = "Микрофон не найден или звуковой вход не открылся."
_WHY_PASTE = (
    "Windows не дала вставить текст (окно с повышенными правами или нажатие не дошло); "
    "текст может остаться в буфере обмена."
)
_WHY_HOTKEY = "Горячую клавишу уже заняла другая программа."
_WHY_ASR = "Речь не распозналась локальной моделью."
_WHY_TRANSLATE = "Локальный перевод не собрал английский текст."

# Stable ids. startup/microphone use the short codes from the public list.
_BLOCK_CODE = {
    "startup": "YO-START-01",
    "model": "YO-MODEL-01",
    "asr": "YO-ASR-01",
    "microphone": "YO-MIC-01",
    "paste": "YO-PASTE-01",
    "translate": "YO-TRANSLATE-01",
    "hotkey": "YO-HOTKEY-01",
    "overlay": "YO-OVERLAY-01",
    "cuda": "YO-CUDA-01",
    "unknown": "YO-UNKNOWN-01",
}


@dataclass(frozen=True)
class Report:
    when: str
    block: str
    code: str
    what: str
    why: str
    detail: str

    def text(self) -> str:
        lines = (
            _line("Когда", self.when),
            _line("Блок", self.block),
            _line("Код", self.code),
            _line("Что делали", self.what),
            _line("Почему", self.why),
            _line("Подробности", self.detail),
        )
        return "\n".join(lines)


def build_report(
    action: str,
    exc: BaseException | None = None,
    *,
    block: str | None = None,
    now: datetime,
) -> Report:
    """Собрать отчёт. ``now`` печатается как есть, без сдвига часового пояса."""
    what = action if isinstance(action, str) else ("" if action is None else str(action))
    if exc is not None and not isinstance(exc, BaseException):
        raise TypeError("exc must be an exception or None")
    known = _known_cause(what, exc)
    if known is None:
        block_name = _normalize_block(block)
        why = UNKNOWN_WHY
    else:
        block_name, why = known
    return Report(
        when=_format_when(now),
        block=block_name,
        code=_BLOCK_CODE[block_name],
        what=what,
        why=why,
        detail=_detail(exc),
    )


def issue_url(report: Report) -> str:
    """Ссылка на новую задачу GitHub. Секретов в адресе нет."""
    query = urlencode(
        {"title": _issue_title(report), "body": report.text()},
        quote_via=quote,
    )
    return f"{ISSUE_NEW}?{query}"


def _line(label: str, value: str) -> str:
    if value == "":
        return f"{label}:"
    return f"{label}: {value}"


def _format_when(now: datetime) -> str:
    return f"{now.year:04d}-{now.month:02d}-{now.day:02d} {now.hour:02d}:{now.minute:02d}:{now.second:02d}"


def _issue_title(report: Report) -> str:
    extra = " ".join(report.what.split())
    if not extra:
        return report.code
    title = f"{report.code}: {extra}"
    if len(title) <= 180:
        return title
    room = 180 - len(report.code) - 2
    if room < 1:
        return report.code
    return f"{report.code}: {extra[:room].rstrip()}"


def _normalize_block(block: str | None) -> str:
    if not isinstance(block, str):
        return "unknown"
    name = block.strip().lower()
    if name in _BLOCK_CODE:
        return name
    return "unknown"


def _known_cause(action: str, exc: BaseException | None) -> tuple[str, str] | None:
    """First matching rule wins: model, then cuda, microphone, paste."""
    folded = _signals(action, exc).casefold()
    if _has(folded, "model.bin", "prefetcherror", "missing model", "hf download"):
        return ("model", _WHY_MODEL)
    if _has(folded, "cublas", "cuda"):
        return ("cuda", _WHY_CUDA)
    if _has(folded, "sounddevice", "portaudio", "микрофон", "no input device"):
        return ("microphone", _WHY_MIC)
    if _is_paste(folded):
        return ("paste", _WHY_PASTE)
    if _has(folded, "клавиша", "hotkey"):
        return ("hotkey", _WHY_HOTKEY)
    if _has(folded, "перевод фразы", "nllb"):
        return ("translate", _WHY_TRANSLATE)
    if _has(folded, "распознавание фразы"):
        return ("asr", _WHY_ASR)
    return None


def _has(folded: str, *needles: str) -> bool:
    return any(needle.casefold() in folded for needle in needles)


def _is_paste(folded: str) -> bool:
    if _has(folded, "clipboard", "uipi", "paste", "буфер обмена"):
        return True
    if "sendinput" not in folded:
        return False
    return _has(folded, "access denied", "access is denied", "отказано в доступе", "не доставил")


def _signals(action: str, exc: BaseException | None) -> str:
    parts: list[str] = []
    if action:
        parts.append(action)
    seen: set[int] = set()
    current: BaseException | None = exc
    hops = 0
    while isinstance(current, BaseException) and id(current) not in seen and hops < 8:
        seen.add(id(current))
        hops += 1
        kind = type(current)
        parts.append(kind.__module__)
        for cls in kind.__mro__:
            if cls is object:
                break
            parts.append(cls.__name__)
        message = str(current)
        if message:
            parts.append(message)
        grouped = getattr(current, "exceptions", None)
        if isinstance(grouped, tuple):
            for sub in grouped:
                if isinstance(sub, BaseException) and id(sub) not in seen:
                    parts.append(_signals("", sub))
        cause = current.__cause__
        if cause is None and not current.__suppress_context__:
            cause = current.__context__
        current = cause if isinstance(cause, BaseException) else None
    return "\n".join(parts)


def _detail(exc: BaseException | None) -> str:
    if exc is None:
        return ""
    name = type(exc).__name__
    message = str(exc)
    head = f"{name}: {message}" if message else name
    frame = _top_frame(exc)
    if not frame:
        return head[:DETAIL_LIMIT]
    suffix = f"\n{frame}"
    # Keep file:function:line even when the message is long.
    room = DETAIL_LIMIT - len(suffix)
    if room < 1:
        return (head + suffix)[:DETAIL_LIMIT]
    if len(head) > room:
        head = head[:room]
    return head + suffix


def _top_frame(exc: BaseException) -> str:
    tb = exc.__traceback__
    if tb is None:
        return ""
    frames = traceback.extract_tb(tb)
    if not frames:
        return ""
    last = frames[-1]
    filename = Path(last.filename).name or last.filename
    func = last.name or "<module>"
    line = 0 if last.lineno is None else last.lineno
    return f"{filename}:{func}:{line}"
