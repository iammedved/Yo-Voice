import unittest

from yo import __version__
from yo.paths import project_root


class ReleaseDocsTests(unittest.TestCase):
    def test_version_is_1_0_0(self):
        self.assertEqual(__version__, "1.0.0")
        text = (project_root() / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('version = "1.0.0"', text)

    def test_readme_covers_release_claims(self):
        readme = (project_root() / "README.md").read_text(encoding="utf-8")
        self.assertIn("Yo-Voice", readme)
        self.assertIn("ё", readme)
        self.assertIn("tilde", readme.lower())
        self.assertIn("local", readme.lower())
        self.assertIn("cloud", readme.lower())
        self.assertIn("NLLB", readme)
        self.assertIn("DeepL", readme)
        self.assertIn("install.sh", readme)
        self.assertIn("autostart", readme.lower())
        self.assertIn("What it cannot do", readme)
        self.assertIn("git clone", readme)

    def test_hero_and_readme_share_exact_phrase(self):
        path = project_root() / "assets" / "readme-hero.png"
        self.assertTrue(path.exists())
        self.assertGreater(path.stat().st_size, 20_000)
        readme = (project_root() / "README.md").read_text(encoding="utf-8")
        self.assertIn("Нажал ё — текст уже в поле.", readme)
        self.assertIn("assets/readme-hero.png", readme)

    def test_github_docs_do_not_use_the_word_daemon(self):
        root = project_root()
        for name in ("README.md", "CHANGELOG.md"):
            text = (root / name).read_text(encoding="utf-8")
            self.assertNotRegex(
                text,
                r"(?i)daemon",
                f"{name} still contains daemon",
            )
            self.assertNotIn("демон", text)
            self.assertNotIn("Демон", text)
