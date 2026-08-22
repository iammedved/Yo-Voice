import unittest

from yo.paths import project_root
from yo.settings import place_near_anchor, window_flags


class SettingsFocusTests(unittest.TestCase):
    def test_listening_does_not_accept_or_steal_focus(self):
        flags = window_flags(listening=True)
        self.assertFalse(flags["focus_on_map"])
        self.assertFalse(flags["accept_focus"])

    def test_idle_settings_can_be_used_without_focus_on_map(self):
        flags = window_flags(listening=False)
        self.assertFalse(flags["focus_on_map"])
        self.assertTrue(flags["accept_focus"])

    def test_overlay_still_rejects_focus(self):
        src = (project_root() / "yo" / "overlay.py").read_text(encoding="utf-8")
        self.assertIn("set_accept_focus(False)", src)
        self.assertIn("set_focus_on_map(False)", src)

    def test_menu_sits_beside_the_cat_not_at_origin(self):
        x, y = place_near_anchor(
            anchor=(720, 480, 200, 186),
            size=(240, 140),
            screen=(0, 0, 1920, 1080),
        )
        self.assertNotEqual((x, y), (0, 0))
        self.assertGreaterEqual(x, 720 + 200)
        self.assertLess(abs(y - 480), 24)

    def test_menu_flips_left_when_the_cat_is_at_the_right_edge(self):
        x, y = place_near_anchor(
            anchor=(1740, 500, 200, 186),
            size=(240, 140),
            screen=(0, 0, 1920, 1080),
        )
        self.assertLessEqual(x + 240, 1740)
        self.assertGreaterEqual(x, 0)

    def test_right_click_does_not_spawn_a_corner_window(self):
        src = (project_root() / "yo" / "app.py").read_text(encoding="utf-8")
        start = src.index("def _open_settings")
        body = src[start : src.index("def _reload_config")]
        self.assertNotIn('"-m", "yo", "settings"', body)
        self.assertIn("popup_mic_menu", body)

    def test_cli_has_settings_and_does_not_spawn_daemon(self):
        src = (project_root() / "yo" / "__main__.py").read_text(encoding="utf-8")
        start = src.index("def main")
        body = src[start : src.index("def _spawn_daemon")]
        self.assertIn('"settings"', body)
        self.assertIn('args.command == "settings"', body)
        self.assertLess(body.index('args.command == "settings"'), body.index("if not daemon_alive()"))
