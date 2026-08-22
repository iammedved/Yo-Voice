import json
import tempfile
import unittest
from pathlib import Path

from yo.config import Config, load_config, save_config


class ConfigLoadTests(unittest.TestCase):
    def test_corrupt_json_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text("{not json", encoding="utf-8")
            cfg = load_config(path)
            self.assertEqual(cfg.model, Config().model)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["model"], Config().model)

    def test_non_object_json_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text("[1, 2]", encoding="utf-8")
            cfg = load_config(path)
            self.assertEqual(cfg.hotkey_keycode, 49)

    def test_microphone_name_roundtrips(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            save_config(Config(microphone="Razer Barracuda X: USB Audio (hw:1,0)"), path)
            loaded = load_config(path)
            self.assertEqual(loaded.microphone, "Razer Barracuda X: USB Audio (hw:1,0)")
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["microphone"], "Razer Barracuda X: USB Audio (hw:1,0)")
            self.assertIsInstance(data["microphone"], str)

    def test_default_microphone_is_empty_auto(self):
        self.assertEqual(Config().microphone, "")
