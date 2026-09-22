import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from yo.asr import TRANSCRIBE_OPTIONS
from yo.polish import polish_ru
from yo.terms import asr_hotwords, load_rules


def _final(text: str) -> str:
    return polish_ru(text, finalize=True)


class BrandTermsTests(unittest.TestCase):
    def setUp(self):
        load_rules.cache_clear()

    def tearDown(self):
        load_rules.cache_clear()

    def test_grok_family(self):
        self.assertIn("Grok", _final("скажи грок"))
        self.assertIn("Grok 4.6", _final("открой грок 4.6"))
        self.assertIn("Grok 4.6", _final("открой грок 4,6"))
        self.assertIn("Grok 4.5", _final("сравни грок 4.5"))
        self.assertNotIn("грок", _final("скажи грок").lower())

    def test_ai_brands(self):
        text = _final(
            "сравни опен эй ай чат джипити кодекс антропик опус сонет и фейбл"
        )
        self.assertIn("OpenAI", text)
        self.assertIn("ChatGPT", text)
        self.assertIn("Codex", text)
        self.assertIn("Anthropic", text)
        self.assertIn("Opus", text)
        self.assertIn("Sonnet", text)
        self.assertIn("Fable", text)

    def test_latin_spellings_normalized(self):
        text = _final("open ai chatgpt anthropic opus sonnet fable grok")
        self.assertIn("OpenAI", text)
        self.assertIn("ChatGPT", text)
        self.assertIn("Anthropic", text)
        self.assertIn("Opus", text)
        self.assertIn("Sonnet", text)
        self.assertIn("Fable", text)
        self.assertIn("Grok", text)

    def test_whisper_chatgpt_phonetics(self):
        samples = (
            "CatGPT.",
            "ЧатGPT, чатGPT, чатGPT, чатGPT.",
            "Чат Джи Пити, чат Джи Пити, чат Джи Пити.",
            "Джиппити Ча Джиппити.",
            "Каджи Пити.",
            "Ёджи Питьи.",
            "Чаджи Пити.",
        )
        for raw in samples:
            text = _final(raw)
            self.assertIn("ChatGPT", text, msg=raw)
            self.assertNotRegex(text, r"(?i)catgpt|джиппити|каджи|питьи|чаджи", msg=text)

    def test_whisper_sol_56_phonetics(self):
        samples = (
            "стол пять точка шесть.",
            "Солл 5.6.",
            "Солл пять точка шесть.",
            "Соул пять точка шесть.",
            "Солу пять точка шесть.",
            "Сол Sol 5.6.",
            "Сол Сол Сол пять точка шесть.",
            "Долл пять точка шесть.",
            "Лолл пять точка шесть.",
            "колл пять шесть.",
        )
        for raw in samples:
            text = _final(raw)
            self.assertIn("Sol 5.6", text, msg=raw)
            self.assertNotRegex(
                text,
                r"(?i)стол|солл|соул|солу|долл|лолл|колл|точка шесть",
                msg=text,
            )
        once = _final("Sol 5.6.")
        self.assertEqual(once.lower().count("sol 5.6"), 1)
        kept = _final("на столе пять чашек")
        self.assertIn("столе", kept.lower())
        self.assertNotIn("Sol", kept)
        for ordinary in (
            "соль в супе",
            "солнце встало",
            "солдат",
            "соло играет",
            "Болл.",
            "о ул.",
            "Толл.",
            "Бол.",
            "Сол.",
            "Йол.",
            "Солу.",
            "Соул.",
            "Йолл.",
            "позвони пять шесть",
        ):
            text = _final(ordinary)
            self.assertNotIn("Sol", text, msg=ordinary)

    def test_kot_stays_russian(self):
        text = _final("на экране кот слушает")
        self.assertIn("кот", text.lower())
        self.assertNotIn("cat", text.lower())

    def test_legal_kodeks_is_not_codex(self):
        text = _final("читай уголовный кодекс")
        self.assertIn("кодекс", text.lower())
        self.assertNotIn("Codex", text)

    def test_ordinary_russian_is_unchanged(self):
        self.assertEqual(_final("я отправил письмо"), "Я отправил письмо.")
        self.assertIn("Ёхо", polish_ru("йоха снова слушает", finalize=True))

    def test_user_file_extends_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "yo-voice"
            cfg.mkdir()
            (cfg / "replacements.json").write_text(
                json.dumps(
                    [{"heard": ["спейс икс", "space x"], "write": "SpaceX"}],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            env = {"XDG_CONFIG_HOME": tmp}
            if sys.platform == "win32":
                env["APPDATA"] = tmp
            with mock.patch.dict(os.environ, env):
                load_rules.cache_clear()
                text = _final("запусти спейс икс")
            self.assertIn("SpaceX", text)
            self.assertIn("Grok", _final("скажи грок"))

    def test_whisper_is_not_prompted_with_brands(self):
        self.assertNotIn("initial_prompt", TRANSCRIBE_OPTIONS)
        self.assertFalse(TRANSCRIBE_OPTIONS.get("hotwords"))
        prompt = TRANSCRIBE_OPTIONS.get("initial_prompt")
        self.assertTrue(prompt in (None, "", False) or "Grok" not in str(prompt))
        words = asr_hotwords()
        self.assertIn("Grok", words)
        self.assertIn("ChatGPT", words)
        self.assertIn("Ёхо", words)
        self.assertNotIn(".com", words)

    def test_pinterest_like_sites(self):
        cases = (
            ("пинтерест", "Pinterest"),
            ("инстаграм", "Instagram"),
            ("фейсбук", "Facebook"),
            ("ютуб", "YouTube"),
            ("тик ток", "TikTok"),
            ("твиттер", "Twitter"),
            ("реддит", "Reddit"),
            ("линкедин", "LinkedIn"),
            ("тамблер", "Tumblr"),
            ("фликр", "Flickr"),
            ("биханс", "Behance"),
            ("дриббл", "Dribbble"),
            ("снепчат", "Snapchat"),
            ("википедия", "Wikipedia"),
            ("твич", "Twitch"),
        )
        self.assertGreaterEqual(len(cases), 10)
        for heard, write in cases:
            text = _final(f"открой {heard}")
            self.assertIn(write, text, msg=heard)

    def test_github_like_sites(self):
        cases = (
            ("гитхаб", "GitHub"),
            ("гитлаб", "GitLab"),
            ("битбакет", "Bitbucket"),
            ("стек оверфлоу", "Stack Overflow"),
            ("оверфлоу", "Stack Overflow"),
            ("хаггинг фейс", "Hugging Face"),
            ("эн пи эм", "npm"),
            ("пайпиай", "PyPI"),
            ("докер хаб", "Docker Hub"),
            ("версель", "Vercel"),
            ("нетлифай", "Netlify"),
            ("хероку", "Heroku"),
            ("диджитал оушен", "DigitalOcean"),
            ("кодберг", "Codeberg"),
            ("каггл", "Kaggle"),
            ("литкод", "LeetCode"),
        )
        self.assertGreaterEqual(len(cases), 10)
        for heard, write in cases:
            text = _final(f"открой {heard}")
            self.assertIn(write, text, msg=heard)

    def test_bare_overflow_is_stack_overflow(self):
        text = _final("Оверфлоу.")
        self.assertIn("Stack Overflow", text)
        self.assertNotIn("оверфлоу", text.lower())
        stacked = _final("стек оверфлоу")
        self.assertIn("Stack Overflow", stacked)
        self.assertEqual(stacked.lower().count("stack overflow"), 1)

    def test_dot_com_uses_domain(self):
        self.assertIn("pinterest.com", _final("открой пинтерест точка ком"))
        self.assertIn("github.com", _final("открой гитхаб точка ком"))
        self.assertNotIn("точка ком", _final("открой пинтерест точка ком").lower())

    def test_bare_x_is_not_a_site(self):
        text = _final("поставь икс в конце")
        self.assertNotIn("x.com", text.lower())
        self.assertNotRegex(text, r"\bX\b")


if __name__ == "__main__":
    unittest.main()
