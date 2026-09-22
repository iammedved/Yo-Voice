import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from yo.config import Config, load_config, patch_config, save_config


class ConfigLoadTests(unittest.TestCase):
    def test_corrupt_json_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text("{not json", encoding="utf-8")
            cfg = load_config(path)
            self.assertEqual(cfg.model, Config().model)
            self.assertEqual(path.read_text(encoding="utf-8"), "{not json")

    def test_non_object_json_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text("[1, 2]", encoding="utf-8")
            cfg = load_config(path)
            self.assertEqual(cfg.hotkey_keycode, 49)
            self.assertEqual(path.read_text(encoding="utf-8"), "[1, 2]")

    def test_missing_file_is_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            cfg = load_config(path)
            self.assertEqual(cfg.hotkey_keycode, 49)
            self.assertTrue(path.is_file())
            self.assertFalse(path.with_name(path.name + ".tmp").exists())

    def test_read_error_does_not_overwrite_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            save_config(
                Config(
                    hotkey_kind="button",
                    hotkey_keycode=9,
                    translate_hotkey_kind="button",
                    translate_hotkey_keycode=8,
                    microphone="Razer Barracuda X: USB Audio (hw:1,0)",
                    tray_intro_shown=True,
                ),
                path,
            )
            before = path.read_bytes()
            with mock.patch.object(Path, "read_text", side_effect=OSError("busy")):
                cfg = load_config(path)
            self.assertEqual(cfg.model, Config().model)
            self.assertEqual(cfg.hotkey_keycode, 49)
            self.assertEqual(path.read_bytes(), before)
            loaded = load_config(path)
            self.assertEqual(loaded.hotkey_kind, "button")
            self.assertEqual(loaded.hotkey_keycode, 9)
            self.assertEqual(loaded.translate_hotkey_kind, "button")
            self.assertEqual(loaded.translate_hotkey_keycode, 8)
            self.assertEqual(loaded.microphone, "Razer Barracuda X: USB Audio (hw:1,0)")
            self.assertTrue(loaded.tray_intro_shown)

    def test_patch_does_not_overwrite_unreadable_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_bytes(b"{not json")
            cfg = patch_config(path, tray_intro_shown=True)
            self.assertTrue(cfg.tray_intro_shown)
            self.assertEqual(cfg.hotkey_keycode, 49)
            self.assertEqual(path.read_bytes(), b"{not json")

    def test_save_config_is_atomic_and_leaves_no_tmp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            save_config(
                Config(
                    hotkey_kind="button",
                    hotkey_keycode=9,
                    translate_hotkey_kind="button",
                    translate_hotkey_keycode=8,
                    microphone="Razer Barracuda X: USB Audio (hw:1,0)",
                    tray_intro_shown=True,
                ),
                path,
            )
            self.assertFalse(path.with_name(path.name + ".tmp").exists())
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["hotkey_keycode"], 9)
            self.assertEqual(data["translate_hotkey_keycode"], 8)
            self.assertEqual(data["microphone"], "Razer Barracuda X: USB Audio (hw:1,0)")
            self.assertTrue(data["tray_intro_shown"])
            self.assertTrue(path.read_text(encoding="utf-8").endswith("\n"))

    def test_failed_replace_keeps_previous_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            save_config(Config(microphone="Razer Barracuda X: USB Audio (hw:1,0)"), path)
            before = path.read_bytes()
            with mock.patch("yo.config.os.replace", side_effect=OSError("disk")):
                with self.assertRaises(OSError):
                    save_config(Config(microphone="other"), path)
            self.assertEqual(path.read_bytes(), before)
            loaded = load_config(path)
            self.assertEqual(loaded.microphone, "Razer Barracuda X: USB Audio (hw:1,0)")

    def test_microphone_name_roundtrips(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            save_config(Config(microphone="Razer Barracuda X: USB Audio (hw:1,0)"), path)
            loaded = load_config(path)
            self.assertEqual(loaded.microphone, "Razer Barracuda X: USB Audio (hw:1,0)")
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["microphone"], "Razer Barracuda X: USB Audio (hw:1,0)")
            self.assertIsInstance(data["microphone"], str)

    def test_patch_microphone_keeps_hotkey(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            save_config(Config(hotkey_kind="button", hotkey_keycode=9), path)
            patched = patch_config(path, microphone="Mic")
            self.assertEqual(patched.hotkey_kind, "button")
            self.assertEqual(patched.hotkey_keycode, 9)
            self.assertEqual(patched.microphone, "Mic")
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["hotkey_keycode"], 9)
            self.assertEqual(data["microphone"], "Mic")

    def test_default_microphone_is_empty_auto(self):
        self.assertEqual(Config().microphone, "")

    def test_default_model_is_russian_turbo(self):
        self.assertEqual(Config().model, "coriollon/whisper-large-v3-turbo-russian")
        self.assertNotIn("codeswitch", Config().model)
