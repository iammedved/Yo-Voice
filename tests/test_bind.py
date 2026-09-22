import json
import tempfile
import unittest
from pathlib import Path

from yo.bind import (
    DEFAULT_BIND,
    ToggleBind,
    accept_capture_event,
    format_bind,
    normalize_bind,
)
from yo.config import Config, load_config, save_config
from yo.paths import project_root


def _yo_src(*names: str) -> str:
    root = project_root() / "yo"
    return "\n".join((root / name).read_text(encoding="utf-8") for name in names)


class BindModelTests(unittest.TestCase):
    def test_default_is_tilde_key(self):
        bind = normalize_bind(None, None)
        self.assertEqual(bind, DEFAULT_BIND)
        self.assertEqual(bind.kind, "key")
        self.assertEqual(bind.code, 49)
        self.assertIn("ё", format_bind(bind))

    def test_mouse_button_roundtrips_in_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            save_config(Config(hotkey_kind="button", hotkey_keycode=8), path)
            loaded = load_config(path)
            bind = normalize_bind(loaded.hotkey_kind, loaded.hotkey_keycode)
            self.assertEqual(bind, ToggleBind(kind="button", code=8))
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["hotkey_kind"], "button")
            self.assertEqual(data["hotkey_keycode"], 8)
            self.assertIn("мышь", format_bind(bind).lower())

    def test_each_bind_is_a_toggle_not_separate_start_stop(self):
        src = _yo_src("hotkey.py", "hotkey_linux.py", "hotkey_win.py")
        self.assertIn("on_press", src)
        self.assertNotIn("on_start", src)
        self.assertNotIn("on_stop", src)
        app = (project_root() / "yo" / "app.py").read_text(encoding="utf-8")
        self.assertIn("listen_press_action", app)
        self.assertIn("HotkeyWatcher", app)

    def test_right_click_menu_can_rebind_translate(self):
        src = (project_root() / "yo" / "settings.py").read_text(encoding="utf-8")
        self.assertIn("Назначить кнопку перевода", src)
        self.assertIn("on_rebind_translate", src)

    def test_capture_accepts_keyboard_and_mouse(self):
        key = accept_capture_event(event_type="key", code=24, overlay_hit=False)
        self.assertEqual(key, ToggleBind(kind="key", code=24))
        mouse = accept_capture_event(event_type="button", code=8, overlay_hit=False)
        self.assertEqual(mouse, ToggleBind(kind="button", code=8))
        self.assertIsNone(accept_capture_event(event_type="button", code=4, overlay_hit=False))
        self.assertIsNone(accept_capture_event(event_type="button", code=1, overlay_hit=True))
        self.assertIsNone(accept_capture_event(event_type="button", code=3, overlay_hit=True))
        self.assertEqual(
            accept_capture_event(event_type="button", code=8, overlay_hit=True),
            ToggleBind(kind="button", code=8),
        )
        self.assertEqual(
            accept_capture_event(event_type="button", code=9, overlay_hit=True),
            ToggleBind(kind="button", code=9),
        )

    def test_right_click_menu_can_rebind(self):
        src = (project_root() / "yo" / "settings.py").read_text(encoding="utf-8")
        self.assertIn("Назначить кнопку", src)
        self.assertIn("on_rebind", src)
        overlay = _yo_src("overlay.py", "overlay_linux.py", "overlay_win.py")
        self.assertIn("self.on_settings(event)", overlay)


class WatcherBindTests(unittest.TestCase):
    def test_watcher_grabs_mouse_when_bind_is_a_button(self):
        src = _yo_src("hotkey.py", "hotkey_linux.py", "hotkey_win.py")
        self.assertIn("grab_button", src)
        self.assertIn("ungrab_button", src)
        self.assertIn("ButtonPress", src)
        self.assertIn("kind", src)
        self.assertIn("WH_MOUSE_LL", src)

    def test_extra_mouse_buttons_still_toggle_over_the_cat(self):
        src = _yo_src("hotkey.py", "hotkey_linux.py", "hotkey_win.py")
        self.assertIn("OVERLAY_UI_BUTTONS", src)
        self.assertIn("_hits_overlay", src)
