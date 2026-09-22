"""Подписи оверлея: говорить сейчас или молчать."""

from __future__ import annotations

WAIT = "Жду"
SPEAK_NOW = "Можно говорить"
LISTEN = "Слушаю"
TRANSLATE = "Перевод"
UNRECOGNIZED = "не разобрал"
SPEAK_NOW_SEC = 1.0


def phrase_for(*, live: bool, now: float, live_since: float | None, task: str = "transcribe") -> str:
    if not live or live_since is None:
        return WAIT
    if (now - live_since) < SPEAK_NOW_SEC:
        return SPEAK_NOW
    if task == "translate":
        return TRANSLATE
    return LISTEN


def wave_allowed(*, live: bool, hint: str = "", mic_missing: bool = False) -> bool:
    return bool(live) and not mic_missing and not (hint or "").strip()


def display_label(
    *,
    live: bool,
    now: float,
    live_since: float | None,
    hint: str = "",
    mic_missing: bool = False,
    status: str = "",
    task: str = "transcribe",
) -> str:
    if mic_missing:
        from yo.capture import NO_MIC_HINT

        return (hint or "").strip() or NO_MIC_HINT
    if (hint or "").strip():
        return hint.strip()
    if (status or "").startswith(("ошибка", "загрузка")):
        return status
    if (status or "").strip() == UNRECOGNIZED:
        return UNRECOGNIZED
    return phrase_for(live=live, now=now, live_since=live_since, task=task)
