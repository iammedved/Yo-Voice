import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from yo.asr import AsrEngine
from yo.bind import (
    ToggleBind,
    binds_conflict,
    listen_press_action,
    optional_bind,
    restore_clipboard_after_paste,
)
from yo.config import Config, load_config, save_config
from yo.paths import project_root
from yo.phrases import LISTEN, SPEAK_NOW, TRANSLATE, WAIT, display_label, phrase_for
from yo.polish import polish_en, polish_ru
from yo.session import DictationSession


class FakeSegments:
    def __init__(self, text: str):
        self.text = text
        self.no_speech_prob = 0.1
        self.avg_logprob = -0.2
        self.compression_ratio = 1.1


class FakeModel:
    def __init__(self):
        self.kwargs = None
        self.calls = 0

    def transcribe(self, pcm, **kwargs):
        self.calls += 1
        self.kwargs = kwargs
        self.pcm = pcm
        return iter([FakeSegments("send this tomorrow")]), None


class ListenPressActionTests(unittest.TestCase):
    def test_idle_starts_the_pressed_mode(self):
        self.assertEqual(
            listen_press_action(listening=False, current_task="transcribe", pressed_task="translate"),
            "start",
        )
        self.assertEqual(
            listen_press_action(listening=False, current_task="translate", pressed_task="transcribe"),
            "start",
        )

    def test_same_key_stops(self):
        self.assertEqual(
            listen_press_action(listening=True, current_task="transcribe", pressed_task="transcribe"),
            "stop",
        )
        self.assertEqual(
            listen_press_action(listening=True, current_task="translate", pressed_task="translate"),
            "stop",
        )

    def test_other_key_switches_current_phrase(self):
        self.assertEqual(
            listen_press_action(listening=True, current_task="transcribe", pressed_task="translate"),
            "switch",
        )

    def test_dictation_key_always_stops(self):
        self.assertEqual(
            listen_press_action(listening=True, current_task="translate", pressed_task="transcribe"),
            "stop",
        )


class TranslateBindTests(unittest.TestCase):
    def test_translate_bind_defaults_to_unset(self):
        cfg = Config()
        self.assertIsNone(optional_bind(cfg.translate_hotkey_kind, cfg.translate_hotkey_keycode))
        self.assertEqual(cfg.translate_hotkey_kind, "")
        self.assertEqual(cfg.translate_hotkey_keycode, 0)

    def test_translate_bind_roundtrips(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            save_config(
                Config(translate_hotkey_kind="button", translate_hotkey_keycode=8),
                path,
            )
            loaded = load_config(path)
            bind = optional_bind(loaded.translate_hotkey_kind, loaded.translate_hotkey_keycode)
            self.assertEqual(bind, ToggleBind(kind="button", code=8))
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["translate_hotkey_kind"], "button")
            self.assertEqual(data["translate_hotkey_keycode"], 8)

    def test_old_config_without_translate_keys_stays_unset(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(
                json.dumps({"model": "large-v3-turbo", "hotkey_kind": "key", "hotkey_keycode": 49}),
                encoding="utf-8",
            )
            loaded = load_config(path)
            self.assertIsNone(optional_bind(loaded.translate_hotkey_kind, loaded.translate_hotkey_keycode))

    def test_same_bind_on_both_modes_conflicts(self):
        dictation = ToggleBind(kind="key", code=49)
        translate = ToggleBind(kind="key", code=49)
        other = ToggleBind(kind="button", code=8)
        self.assertTrue(binds_conflict(dictation, translate))
        self.assertFalse(binds_conflict(dictation, other))
        self.assertFalse(binds_conflict(dictation, None))

    def test_clipboard_stays_only_after_translate(self):
        import sys

        if sys.platform == "win32":
            self.assertFalse(restore_clipboard_after_paste(task="transcribe"))
            self.assertFalse(restore_clipboard_after_paste(task="translate"))
        else:
            self.assertTrue(restore_clipboard_after_paste(task="transcribe"))
            self.assertFalse(restore_clipboard_after_paste(task="translate"))


class TranslateAsrTests(unittest.TestCase):
    def test_translate_flag_still_transcribes_russian(self):
        engine = AsrEngine()
        engine.model = FakeModel()
        engine.device = "cpu"
        audio = (0.04 * np.sin(np.linspace(0, 40, 16000))).astype(np.float32)
        engine.transcribe(audio, 16000, task="translate")
        self.assertIs(engine.model.__class__, FakeModel)
        self.assertEqual(engine.model.calls, 1)
        self.assertEqual(engine.model.kwargs["task"], "transcribe")
        self.assertEqual(engine.model.kwargs["language"], "ru")

    def test_default_task_is_transcribe(self):
        engine = AsrEngine()
        engine.model = FakeModel()
        audio = (0.04 * np.sin(np.linspace(0, 40, 16000))).astype(np.float32)
        engine.transcribe(audio, 16000)
        self.assertEqual(engine.model.kwargs["task"], "transcribe")


class TranslatePhraseTests(unittest.TestCase):
    def test_translate_mode_says_perevod_after_speak_now(self):
        self.assertEqual(
            phrase_for(live=True, now=11.0, live_since=10.0, task="translate"),
            TRANSLATE,
        )
        self.assertEqual(TRANSLATE, "Перевод")
        self.assertEqual(
            phrase_for(live=True, now=10.4, live_since=10.0, task="translate"),
            SPEAK_NOW,
        )
        self.assertEqual(phrase_for(live=False, now=12.0, live_since=10.0, task="translate"), WAIT)

    def test_dictation_still_says_slushayu(self):
        self.assertEqual(phrase_for(live=True, now=11.0, live_since=10.0), LISTEN)
        self.assertEqual(
            display_label(live=True, now=12.0, live_since=10.0, task="translate"),
            TRANSLATE,
        )


class PolishEnTests(unittest.TestCase):
    def test_english_gets_capital_and_period(self):
        self.assertEqual(polish_en("send this tomorrow", finalize=True), "Send this tomorrow.")

    def test_drops_whisper_thanks(self):
        self.assertEqual(polish_en("thank you", finalize=True), "")
        self.assertEqual(polish_en("Thanks for watching", finalize=True), "")

    def test_does_not_run_russian_question_logic(self):
        self.assertEqual(polish_en("how are you", finalize=True), "How are you.")
        self.assertNotEqual(polish_ru("как дела", finalize=True), polish_en("как дела", finalize=True))


class TranslateSessionTests(unittest.TestCase):
    def setUp(self):
        self.injected = []
        self.session = DictationSession(inject=self.injected.append)

    def test_translate_commit_uses_english_polish(self):
        self.session.start(task="translate")
        text = self.session.commit_utterance("send this tomorrow")
        self.assertEqual(text, "Send this tomorrow.")
        self.assertEqual(self.injected, ["Send this tomorrow."])

    def test_switch_task_keeps_listening(self):
        self.session.start(task="transcribe")
        self.session.set_task("translate")
        self.assertTrue(self.session.listening)
        self.assertEqual(self.session.task, "translate")
        text = self.session.commit_utterance("send this tomorrow")
        self.assertEqual(text, "Send this tomorrow.")

    def test_queued_task_wins_over_live_mode(self):
        self.session.start(task="translate")
        text = self.session.commit_utterance("я отправил письмо", task="transcribe")
        self.assertEqual(text, "Я отправил письмо.")


class TranslateWiringTests(unittest.TestCase):
    def test_menu_can_assign_translate_button(self):
        src = (project_root() / "yo" / "settings.py").read_text(encoding="utf-8")
        self.assertIn("Назначить кнопку перевода", src)
        self.assertIn("on_rebind_translate", src)
        self.assertIn("не назначена", src)

    def test_app_starts_two_toggles_without_reloading_model(self):
        src = (project_root() / "yo" / "app.py").read_text(encoding="utf-8")
        self.assertIn("listen_press_action", src)
        self.assertIn('_press("translate")', src)
        self.assertIn("restore_clipboard_after_paste", src)
        self.assertIn("_pause_hotkeys", src)
        self.assertIn("_restart_hotkey", src)
        toggle = src[src.index("def toggle") : src.index("def start_listen")]
        self.assertNotIn("engine.load", toggle)

    def test_start_listen_sets_task_before_show(self):
        src = (project_root() / "yo" / "app.py").read_text(encoding="utf-8")
        body = src[src.index("def start_listen") : src.index("def stop_listen")]
        self.assertLess(body.index("set_task(task)"), body.index("show_listening"))
        self.assertIn("set_live(True)", body)

    def test_finalize_passes_queued_task_not_live_mode(self):
        src = (project_root() / "yo" / "app.py").read_text(encoding="utf-8")
        start = src.index("def _finalize")
        body = src[start : src.index("def _finalize_failed")]
        self.assertIn("task", body)
        self.assertIn("self.engine.transcribe", body)
        self.assertNotIn("task=task", body)
        self.assertIn("english_from_russian_asr", body)
        self.assertIn("LocalTranslator", src)

    def test_translate_path_has_no_cloud_translator(self):
        root = project_root()
        haystack = "\n".join(
            (root / "yo" / name).read_text(encoding="utf-8")
            for name in ("app.py", "asr.py", "mt.py")
        )
        self.assertNotIn("deepl", haystack.lower())
        self.assertNotIn("www.deepl.com", haystack.lower())
        asr = (root / "yo" / "asr.py").read_text(encoding="utf-8")
        self.assertNotIn('"task": "translate"', asr)
        self.assertNotIn("'task': 'translate'", asr)

    def test_overlay_forwards_task_to_status(self):
        yo = project_root() / "yo"
        linux = (yo / "overlay_linux.py").read_text(encoding="utf-8")
        win = (yo / "overlay_win.py").read_text(encoding="utf-8")
        self.assertIn("task=overlay.task", linux)
        self.assertIn("task=self.task", win)
        phrases = (yo / "phrases.py").read_text(encoding="utf-8")
        self.assertIn('TRANSLATE = "Перевод"', phrases)


if __name__ == "__main__":
    unittest.main()
