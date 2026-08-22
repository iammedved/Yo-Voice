"""Подписи оверлея: говорить сейчас или молчать."""

from __future__ import annotations

WAIT = "Жду"
SPEAK_NOW = "Можно говорить"
LISTEN = "Слушаю"
SPEAK_NOW_SEC = 1.0


def phrase_for(*, live: bool, now: float, live_since: float | None) -> str:
    if not live or live_since is None:
        return WAIT
    if (now - live_since) < SPEAK_NOW_SEC:
        return SPEAK_NOW
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
) -> str:
    if mic_missing:
        from yo.capture import NO_MIC_HINT

        return (hint or "").strip() or NO_MIC_HINT
    if (hint or "").strip():
        return hint.strip()
    if (status or "").startswith("ошибка"):
        return status
    return phrase_for(live=live, now=now, live_since=live_since)
