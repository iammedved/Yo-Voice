import ast
import unittest
from pathlib import Path

from yo.overlay import HEIGHT, MASCOT_HEIGHT, STATUS_HEIGHT, WAVE_GAP, WAVE_HEIGHT, WIDTH
from yo.paths import orb_path, project_root


class OverlayLayoutTests(unittest.TestCase):
    def test_overlay_asset_is_logo(self):
        path = orb_path()
        self.assertEqual(path.name, "logo.png")
        self.assertTrue(path.exists())

    def test_logo_is_transparent_png_not_giraffe_file(self):
        path = orb_path()
        data = path.read_bytes()
        self.assertTrue(data.startswith(b"\x89PNG"))
        self.assertGreater(path.stat().st_size, 10_000)

    def test_waves_sit_below_logo(self):
        self.assertGreater(WAVE_GAP, 0)
        self.assertGreater(STATUS_HEIGHT, 12)
        used = 4 + MASCOT_HEIGHT + WAVE_GAP + STATUS_HEIGHT + WAVE_GAP + WAVE_HEIGHT
        self.assertLessEqual(used, HEIGHT)
        self.assertLess(MASCOT_HEIGHT, HEIGHT)

    def test_scene_draws_logo_then_status_then_waves(self):
        src = Path(project_root() / "yo" / "overlay.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        fn = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_draw_scene"
        )
        names = [
            node.func.id
            for node in ast.walk(fn)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        self.assertIn("_draw_mascot", names)
        self.assertIn("_draw_status", names)
        self.assertIn("_draw_waves", names)
        self.assertLess(names.index("_draw_mascot"), names.index("_draw_status"))
        self.assertLess(names.index("_draw_status"), names.index("_draw_waves"))

    def test_right_click_opens_settings(self):
        src = Path(project_root() / "yo" / "overlay.py").read_text(encoding="utf-8")
        self.assertIn("on_settings", src)
        self.assertIn("button", src)
        self.assertIn("self.on_settings(event)", src)

    def test_window_fits_logo_lockup(self):
        self.assertGreaterEqual(WIDTH, 180)
        self.assertLess(HEIGHT, 190)
