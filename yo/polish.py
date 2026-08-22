"""Нормализация русской расшифровки: пробелы, регистр, пунктуация."""

from __future__ import annotations

import re

_SPACE_RE = re.compile(r"\s+")
_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?…])")
_AFTER_PUNCT_RE = re.compile(r"([,.;:!?…])([^\s\d»\"”])")
_MULTI_PUNCT_RE = re.compile(r"([.!?]){2,}")
_WORD_RE = re.compile(r"[а-яёa-z]+", re.IGNORECASE)

QUESTION_START = {
    "кто",
    "что",
    "где",
    "когда",
    "куда",
    "откуда",
    "почему",
    "зачем",
    "как",
    "какой",
    "какая",
    "какое",
    "какие",
    "каким",
    "какую",
    "каков",
    "какова",
    "сколько",
    "чей",
    "чья",
    "чьё",
    "чьи",
    "разве",
    "неужели",
    "отчего",
    "насколько",
}

QUESTION_PARTICLES = {"ли", "разве", "неужели"}

LONG_STATEMENT_STARTERS = {"как", "что", "когда"}

HALLUCINATIONS = (
    "продолжение следует",
    "субтитры создавал",
    "субтитры сделал",
    "спасибо за просмотр",
    "подписывайтесь на канал",
    "ставьте лайки",
    "редактор субтитров",
    "ссылка в описании",
    "пишите в комментариях",
    "нажмите на колокольчик",
    "music",
    "[музыка]",
    "(музыка)",
)

EXACT_HALLUCINATIONS = {
    "спасибо",
    "благодарю",
    "пожалуйста",
    "thanks",
    "thank you",
    "thankyou",
    "продолжение следует",
}

_TERMINAL = set(".!?…")

_FUSED_U_SLOV = re.compile(r"\bуслов\b", re.IGNORECASE)
_DOUBLE_NE = re.compile(r"\bне\s+(неправильн)", re.IGNORECASE)
_OKONCHANIE_U_SLOV = re.compile(r"\bокончание(\s+у\s+слов)", re.IGNORECASE)
_NEPRAVILN_OKONCHANI = re.compile(
    r"\bнеправильн[а-яё]*\s+(?:на\s+)?окончани[а-яё]*",
    re.IGNORECASE,
)
_YO_NAME = re.compile(
    r"\b(?:ёхо|ехо|йоха|йохо|ёха|йох[ао]|еха|проха)\b",
    re.IGNORECASE,
)
_BEZ_RUCHN = re.compile(r"\bбезручн([а-яё]*)", re.IGNORECASE)
_I_SLUSHAI = re.compile(r"\bи\s+слушай\b", re.IGNORECASE)
_USLUH = re.compile(r"\bуслух\b", re.IGNORECASE)
_U_TORA = re.compile(r"\bу тора\b", re.IGNORECASE)
_GROMKO_TONKO = re.compile(r"\bгромко и тонко\b", re.IGNORECASE)
_ELKA_YOSH = re.compile(r"\bёлк[ао],\s*ёш\b", re.IGNORECASE)
_I_SADITSYA = re.compile(r"\bи садиться\b", re.IGNORECASE)
_ZAVTRA_SREDA = re.compile(r"\bзавтра расцвета\b", re.IGNORECASE)
_POL_POL = re.compile(r"\bпол\s+полсекунды\b", re.IGNORECASE)
_NE_OHA = re.compile(r"\bчерез букву не оха\b", re.IGNORECASE)
_NAHOD_SORTA = re.compile(r"\bнаходятся сорта\b", re.IGNORECASE)
_YOHO_DUP = re.compile(r"(Ёхо)(?:\s+Ёхо)+")
_ELKA_HYPHEN = re.compile(r"\bёлк[аи]\s*[-,]\s*ёш[ьъ]?\b", re.IGNORECASE)
_BUKVA_YO = re.compile(r"\bчерез букву\s+(?:по\s+)?(?:её|ее|е|йо)\b", re.IGNORECASE)
_ZAVTRA_V_SREDA = re.compile(r"\bзавтра\s+в\s+среда\b", re.IGNORECASE)
_SADIT_CTX = re.compile(r"(^|полз[её]т\s+)садиться\b", re.IGNORECASE)
_LYZHERA = re.compile(r"\bлыжера\b", re.IGNORECASE)
_LYZHER = re.compile(r"\bлыжер\b", re.IGNORECASE)
_STOIT_MON = re.compile(r"\bстоит монитора\b", re.IGNORECASE)
_BUKVA_ZVUKU = re.compile(r"\bчерез букву\s+звуку\b", re.IGNORECASE)
_BUKVA_YO_WORD = re.compile(r"\bбуква\s+йо\b", re.IGNORECASE)
_YOZH_ESH = re.compile(r"\bёж\s+ешь\b", re.IGNORECASE)
_ZAVTRA_V_DA = re.compile(r"\bзавтра\s+в\s+да\b", re.IGNORECASE)
_POLZET_SADIT = re.compile(r"\bполз[её]т\s+садится\b", re.IGNORECASE)
_GROMKO_CHETKO = re.compile(r"\bгромко\s+четко\b", re.IGNORECASE)
_U_SORTA = re.compile(r"\bу сорта\b", re.IGNORECASE)
_VKL_USLUG = re.compile(r"\bвключение услуг\b", re.IGNORECASE)
_BUKVA_YO_EE = re.compile(r"\bбукву ё\s+(?:её|ее)\b", re.IGNORECASE)
_VYHODITSA = re.compile(r"\bнаходится\s+выходится\b", re.IGNORECASE)
_NA_POLCHET = re.compile(r"\bна полчет\b", re.IGNORECASE)
_VOLNA_POLCHET = re.compile(r"\bволна\s+на полчет\b", re.IGNORECASE)
_I_SLUSHAYA = re.compile(r"\bи слушая\b", re.IGNORECASE)
_U_SHEPOTOM = re.compile(r"\bу шёпотом\b", re.IGNORECASE)
_RECH_SET = re.compile(r"\bречь сеть\b", re.IGNORECASE)
_V_ZAHODITSA = re.compile(r"\bв заходится\b", re.IGNORECASE)
_GOLOS_DUP = re.compile(r"\bголос и голос\b", re.IGNORECASE)
_SLUSHAT_DUP = re.compile(r"\bслушать\s+тих[а-яё]*\s+и\s+слушать\b", re.IGNORECASE)


def polish_ru(text: str, *, finalize: bool = False, continuation: bool = False) -> str:
    text = _normalize_spaces(text)
    if not text:
        return ""
    text = _strip_hallucinations(text)
    if not text:
        return ""
    text = _fix_asr_glues(text)
    text = _fix_punct_spacing(text)
    if continuation:
        text = _uncap_leading(text)
        text = _capitalize_sentences(text, cap_first=False)
    else:
        text = _capitalize_sentences(text, cap_first=True)
    if finalize:
        text = _ensure_terminal_punct(text)
    return text


def _fix_asr_glues(text: str) -> str:
    text = _DOUBLE_NE.sub(r"\1", text)
    text = _FUSED_U_SLOV.sub("у слов", text)
    text = _OKONCHANIE_U_SLOV.sub(r"окончания\1", text)
    text = _NEPRAVILN_OKONCHANI.sub("неправильные окончания", text)
    text = _USLUH.sub("у слов", text)
    text = _U_TORA.sub("у монитора", text)
    text = _YO_NAME.sub("Ёхо", text)
    text = _YOHO_DUP.sub(r"\1", text)
    text = _BEZ_RUCHN.sub(r"без ручн\1", text)
    text = _I_SLUSHAI.sub("и слушает", text)
    text = _GROMKO_TONKO.sub("громко и чётко", text)
    text = _ELKA_YOSH.sub("ёлка, ёж", text)
    text = _I_SADITSYA.sub("и садится", text)
    text = _ZAVTRA_SREDA.sub("завтра среда", text)
    text = _POL_POL.sub("полсекунды", text)
    text = _NE_OHA.sub("через букву ё, не йоха", text)
    text = _NAHOD_SORTA.sub("находится у рта", text)
    text = _ELKA_HYPHEN.sub("ёлка, ёж", text)
    text = _BUKVA_YO.sub("через букву ё", text)
    text = _ZAVTRA_V_SREDA.sub("завтра среда", text)
    text = _SADIT_CTX.sub(r"\1садится", text)
    text = _LYZHERA.sub("жирафа", text)
    text = _LYZHER.sub("жираф", text)
    text = _STOIT_MON.sub("стоит у монитора", text)
    text = _BUKVA_ZVUKU.sub("через букву ё", text)
    text = _BUKVA_YO_WORD.sub("буква ё", text)
    text = _YOZH_ESH.sub("ёж", text)
    text = _ZAVTRA_V_DA.sub("завтра среда", text)
    text = _POLZET_SADIT.sub("ползёт и садится", text)
    text = _GROMKO_CHETKO.sub("громко и чётко", text)
    text = _U_SHEPOTOM.sub("у монитора", text)
    text = _RECH_SET.sub("речь быстрая", text)
    text = _V_ZAHODITSA.sub("у рта", text)
    text = _GOLOS_DUP.sub("голос", text)
    text = _SLUSHAT_DUP.sub("слушает", text)
    text = _U_SORTA.sub("у рта", text)
    text = _VKL_USLUG.sub("у слов", text)
    text = _BUKVA_YO_EE.sub("букву ё", text)
    text = _VYHODITSA.sub("находится", text)
    text = _VOLNA_POLCHET.sub("волна ползёт", text)
    text = _NA_POLCHET.sub("ползёт", text)
    text = _I_SLUSHAYA.sub("и слушает", text)
    return text


def _strip_hallucinations(text: str) -> str:
    parts = re.split(r"(?<=[.!?…])\s+", text)
    kept = [part.strip() for part in parts if part.strip() and not _is_hallucination(part)]
    return " ".join(kept)


def _normalize_spaces(text: str) -> str:
    return _SPACE_RE.sub(" ", (text or "").replace("\u00a0", " ")).strip()


def _fix_punct_spacing(text: str) -> str:
    text = _BEFORE_PUNCT_RE.sub(r"\1", text)
    text = _AFTER_PUNCT_RE.sub(r"\1 \2", text)
    text = text.replace(" ,", ",").replace(" .", ".")
    return _normalize_spaces(text)


def _uncap_leading(text: str) -> str:
    first = text.split(None, 1)[0] if text.split() else ""
    if first.lower().replace("е", "ё") in {"ёхо"} or first in {"Ёхо", "ёхо"}:
        rest = text[len(first) :]
        return "Ёхо" + rest
    i = 0
    while i < len(text) and not text[i].isalpha():
        i += 1
    if i < len(text) and text[i].isupper():
        return text[:i] + text[i].lower() + text[i + 1 :]
    return text


def _capitalize_sentences(text: str, *, cap_first: bool = True) -> str:
    chars = list(text)
    cap_next = cap_first
    for i, ch in enumerate(chars):
        if cap_next and ch.isalpha():
            chars[i] = ch.upper()
            cap_next = False
        elif ch in _TERMINAL:
            cap_next = True
    return "".join(chars)


def _ensure_terminal_punct(text: str) -> str:
    stripped = text.rstrip()
    if not stripped:
        return stripped
    if stripped[-1] in _TERMINAL:
        return stripped
    if stripped[-1] in "»\"”":
        return stripped
    last = _last_sentence(stripped)
    if _is_question(last):
        return stripped + "?"
    return stripped + "."


def _last_sentence(text: str) -> str:
    end = 0
    for i, ch in enumerate(text):
        if ch in _TERMINAL:
            end = i + 1
    tail = text[end:].strip()
    return tail or text


def _is_question(text: str) -> bool:
    words = [w.lower() for w in _WORD_RE.findall(text)]
    if not words:
        return False
    if any(w in QUESTION_PARTICLES for w in words):
        return True
    first = words[0]
    if first not in QUESTION_START:
        return False
    if first in LONG_STATEMENT_STARTERS and len(words) > 7:
        return False
    return True


def _is_hallucination(text: str) -> bool:
    folded = text.strip().lower()
    words = _WORD_RE.findall(folded)
    joined = " ".join(words)
    if joined in EXACT_HALLUCINATIONS:
        return True
    return any(token in folded for token in HALLUCINATIONS)
