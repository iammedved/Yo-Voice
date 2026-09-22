"""После ASR: услышанное написание → каноническое (часто английское)."""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from yo.paths import replacements_path

log = logging.getLogger("yo.terms")

# Longer phrases first at load time. heard is what Whisper often writes.
_AI_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        (
            "грок 4.6",
            "грок 4,6",
            "грок 4 6",
            "grok 4.6",
            "grok 4,6",
            "grok 4 6",
        ),
        "Grok 4.6",
    ),
    (
        (
            "грок 4.5",
            "грок 4,5",
            "грок 4 5",
            "grok 4.5",
            "grok 4,5",
            "grok 4 5",
        ),
        "Grok 4.5",
    ),
    (
        (
            "стол пять точка шесть",
            "сол пять точка шесть",
            "солл 5.6",
            "солу пять точка шесть",
            "солл пять точка шесть",
            "соул пять точка шесть",
            "долл пять точка шесть",
            "лолл пять точка шесть",
            "колл пять шесть",
            "соль пять точка шесть",
            "sol пять точка шесть",
            "sol 5.6",
            "sol 5,6",
            "sol 5 6",
            "сол 5.6",
            "сол 5,6",
            "соль 5.6",
            "стол 5.6",
            "стол 5,6",
        ),
        "Sol 5.6",
    ),
    (
        (
            "чат джи пи ти",
            "чат джи пити",
            "чат джипити",
            "чатджипити",
            "ча джиппити",
            "джиппити",
            "каджи пити",
            "ёджи питьи",
            "еджи питьи",
            "чаджи пити",
            "catgpt",
            "чатgpt",
        ),
        "ChatGPT",
    ),
    (("опен эй ай", "опенэйай", "опен аи", "open ai", "openai"), "OpenAI"),
    (("чат gpt", "чат гпт", "чатгпт", "chat gpt", "chatgpt"), "ChatGPT"),
    (("anthropic", "антропик", "энтропик"), "Anthropic"),
    (("codex", "кодэкс", "кодикс", "кодекс"), "Codex"),
    (("sonnet", "сонет"), "Sonnet"),
    (("fable", "фейбл", "фабл"), "Fable"),
    (("opus", "опус"), "Opus"),
    (("grok", "грок"), "Grok"),
)

# (English brand, canonical host, Russian/latin heard forms)
_SITES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("Pinterest", "pinterest.com", ("пинтерест", "pinterest")),
    ("Instagram", "instagram.com", ("инстаграм", "инстаграмм", "инста", "instagram")),
    ("Facebook", "facebook.com", ("фейсбук", "facebook")),
    ("YouTube", "youtube.com", ("ютуб", "ютьюб", "ютюб", "you tube", "youtube")),
    ("TikTok", "tiktok.com", ("тикток", "тик ток", "tik tok", "tiktok")),
    ("Twitter", "twitter.com", ("твиттер", "twitter")),
    ("Reddit", "reddit.com", ("реддит", "редит", "reddit")),
    ("LinkedIn", "linkedin.com", ("линкедин", "линкед ин", "linked in", "linkedin")),
    ("Tumblr", "tumblr.com", ("тамблер", "tumblr")),
    ("Flickr", "flickr.com", ("фликр", "фликер", "flickr")),
    ("Behance", "behance.net", ("биханс", "беханс", "behance")),
    ("Dribbble", "dribbble.com", ("дриббл", "дрибл", "dribbble")),
    ("Snapchat", "snapchat.com", ("снепчат", "снэпчат", "snapchat")),
    ("Wikipedia", "wikipedia.org", ("википедия", "wikipedia")),
    ("Twitch", "twitch.tv", ("твич", "твитч", "twitch")),
    ("GitHub", "github.com", ("гитхаб", "гит хаб", "github")),
    ("GitLab", "gitlab.com", ("гитлаб", "гит лаб", "gitlab")),
    ("Bitbucket", "bitbucket.org", ("битбакет", "бит бакет", "bitbucket")),
    (
        "Stack Overflow",
        "stackoverflow.com",
        ("стек оверфлоу", "стэк оверфлоу", "стековерфлоу", "stack overflow", "оверфлоу", "овер флоу"),
    ),
    (
        "Hugging Face",
        "huggingface.co",
        ("хаггинг фейс", "хагинг фейс", "hugging face", "huggingface"),
    ),
    ("npm", "npmjs.com", ("эн пи эм", "npm")),
    ("PyPI", "pypi.org", ("пайпиай", "пай пай ай", "pypi")),
    ("Docker Hub", "hub.docker.com", ("докер хаб", "docker hub")),
    ("Vercel", "vercel.com", ("версель", "верцел", "vercel")),
    ("Netlify", "netlify.com", ("нетлифай", "netlify")),
    ("Heroku", "heroku.com", ("хероку", "heroku")),
    (
        "DigitalOcean",
        "digitalocean.com",
        ("диджитал оушен", "digital ocean", "digitalocean"),
    ),
    ("Codeberg", "codeberg.org", ("кодберг", "codeberg")),
    ("Kaggle", "kaggle.com", ("каггл", "кэггл", "kaggle")),
    ("LeetCode", "leetcode.com", ("литкод", "leet code", "leetcode")),
)


def _site_rules(
    sites: tuple[tuple[str, str, tuple[str, ...]], ...],
) -> tuple[tuple[tuple[str, ...], str], ...]:
    rules: list[tuple[tuple[str, ...], str]] = []
    for brand, domain, heard in sites:
        rules.append((heard, brand))
        com = [domain]
        for form in heard:
            com.append(f"{form} точка ком")
            com.append(f"{form}.com")
        rules.append((tuple(dict.fromkeys(com)), domain))
    return tuple(rules)


DEFAULT_RULES: tuple[tuple[tuple[str, ...], str], ...] = _AI_RULES + _site_rules(_SITES)


def asr_hotwords(limit: int = 20) -> str:
    """Short brand list kept for tests and docs. Whisper is not given hotwords."""
    seen: list[str] = []

    def add(token: str) -> None:
        text = (token or "").strip()
        if not text or "." in text or text in seen:
            return
        seen.append(text)

    add("Ёхо")
    add("Sol")
    add("ChatGPT")
    for _heard, write in DEFAULT_RULES:
        add(write)
        if len(seen) >= limit:
            break
    return " ".join(seen[:limit])

_LEGAL_KODEKS = re.compile(
    r"\b((?:уголовн|гражданск|семейн|трудов|налогов|жилищн|административн|"
    r"процессуальн|бюджетн|земельн|лесн|водн|таможенн|градостроительн|"
    r"арбитражн)[а-яё]*\s+кодекс)\b",
    re.IGNORECASE,
)

_EDGE = r"0-9A-Za-zА-Яа-яЁё"

# Whisper often splits or respells brands; aliases above miss spacing/script mix.
_CHATGPT_RE = re.compile(
    r"(?<![\wА-Яа-яЁё])"
    r"(?:"
    r"c[ha]t[\s\-]*gpt"
    r"|чат[\s\-]*gpt"
    r"|чат[\s\-]*гпт"
    r"|(?:чат|ча|ка|ё|е)?\s*джи?\s*п+[ие]?\s*т[иыь]и?"
    r")"
    r"(?![\wА-Яа-яЁё])",
    re.IGNORECASE,
)
_SOL_STEM = r"(?:sol|soul|сол[ллуеаоыьъ]?|соул|стол|долл|лолл|болл?|йолл?|толл|колл|о\s*ул)"
_SOL56_RE = re.compile(
    r"(?<![\wА-Яа-яЁё])"
    rf"(?:{_SOL_STEM}[\s,]*)+"
    r"(?:5(?:[.,]\s*|\s+)6|пять(?:\s+точка)?\s+шесть)"
    r"(?![\wА-Яа-яЁё])",
    re.IGNORECASE,
)
def _rewrite_spoken_models(text: str) -> str:
    text = _CHATGPT_RE.sub("ChatGPT", text)
    return _SOL56_RE.sub("Sol 5.6", text)


def replacements_file() -> Path:
    return replacements_path()


@lru_cache(maxsize=1)
def load_rules() -> tuple[tuple[str, str], ...]:
    by_heard: dict[str, str] = {}
    for heard_forms, write in DEFAULT_RULES:
        for heard in heard_forms:
            by_heard[_norm_heard(heard)] = write
    path = replacements_file()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            log.warning("битый словарь замен %s, беру встроенный", path)
        else:
            for heard, write in _parse_user_rules(data):
                by_heard[_norm_heard(heard)] = write
    pairs = [(heard, write) for heard, write in by_heard.items() if heard and write]
    pairs.sort(key=lambda item: len(item[0]), reverse=True)
    return tuple(pairs)


def apply_brand_terms(text: str, rules: tuple[tuple[str, str], ...] | None = None) -> str:
    if not text:
        return text
    saved: list[str] = []

    def _hold(match: re.Match[str]) -> str:
        saved.append(match.group(1))
        return f"\x00K{len(saved) - 1}\x00"

    text = _LEGAL_KODEKS.sub(_hold, text)
    text = _rewrite_spoken_models(text)
    for heard, write in rules if rules is not None else load_rules():
        text = re.sub(_heard_pattern(heard), write, text, flags=re.IGNORECASE)
    for i, chunk in enumerate(saved):
        text = text.replace(f"\x00K{i}\x00", chunk)
    return text


def _parse_user_rules(data: object) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if isinstance(data, dict):
        for heard, write in data.items():
            if isinstance(heard, str) and isinstance(write, str):
                out.append((heard, write))
        return out
    if not isinstance(data, list):
        log.warning("словарь замен не список и не объект, игнорирую")
        return out
    for item in data:
        if not isinstance(item, dict):
            continue
        write = item.get("write")
        heard = item.get("heard")
        if not isinstance(write, str) or not write.strip():
            continue
        if isinstance(heard, str):
            out.append((heard, write))
        elif isinstance(heard, list):
            for form in heard:
                if isinstance(form, str) and form.strip():
                    out.append((form, write))
    return out


def _norm_heard(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _heard_pattern(heard: str) -> str:
    # Do not eat Pinterest inside pinterest.com; still allow "грок." at sentence end.
    return (
        rf"(?<![{_EDGE}]){re.escape(heard)}"
        rf"(?![{_EDGE}]|\.(?:com|org|net|io|tv|co|ai|app|dev|ru|info|me|cc)\b)"
    )
