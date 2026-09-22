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
        yo = Path(project_root() / "yo")
        for name in ("overlay_linux.py", "overlay_win.py"):
            src = (yo / name).read_text(encoding="utf-8")
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
        yo = Path(project_root() / "yo")
        src = "\n".join(
            (yo / name).read_text(encoding="utf-8")
            for name in ("overlay.py", "overlay_linux.py", "overlay_win.py")
        )
        self.assertIn("on_settings", src)
        self.assertIn("button", src)
        self.assertIn("self.on_settings(event)", src)

    def test_window_fits_logo_lockup(self):
        self.assertGreaterEqual(WIDTH, 180)
        self.assertLess(HEIGHT, 190)

    def test_win_status_is_high_contrast_below_mascot(self):
        src = Path(project_root() / "yo" / "overlay_win.py").read_text(encoding="utf-8")
        start = src.index("def _draw_status")
        body = src[start : src.index("def _draw_waves")]
        self.assertIn("create_rectangle", body)
        self.assertIn('anchor="n"', body)
        self.assertIn('justify="center"', body)
        self.assertIn("#14171c", body)
        self.assertIn("#f4f7fb", body)
        self.assertNotIn('fill="#dbe0e3"', body)
        paint = src[src.index("def _paint") : src.index("def _draw_mascot")]
        self.assertIn("wave_allowed", paint)
        self.assertLess(paint.index("_draw_status"), paint.index("_draw_waves"))
        load = src[src.index("def _load_orb") : src.index("def _voice_speed")]
        self.assertIn("ImageTk", load)
        self.assertIn("_flatten_to_chroma", load)
        self.assertIn("_make_wave_image", src)
        self.assertIn("_edge_fade", src)
        self.assertIn("wave_amplitude", src)
        self.assertIn("voice_loudness", src)
        waves = src[src.index("def _draw_waves") : src.index("def run_demo")]
        self.assertIn("_make_wave_image", waves)
        self.assertIn("_CHROMA", waves)

    def test_park_withdraws_without_clearing_listen_state(self):
        src = Path(project_root() / "yo" / "overlay_win.py").read_text(encoding="utf-8")
        park = src[src.index("def park") : src.index("def unpark")]
        unpark = src[src.index("def unpark") : src.index("def set_task")]
        hide = src[src.index("def hide") : src.index("def park")]
        self.assertIn("withdraw()", park)
        self.assertIn("after_cancel", park)
        self.assertNotIn("self.visible = False", park)
        self.assertNotIn("self.live = False", park)
        self.assertIn("SW_HIDE", park)
        self.assertIn("_map_window", unpark)
        self.assertIn("self.visible", unpark)
        self.assertIn("self.visible = False", hide)
        self.assertIn("self.live = False", hide)
        self.assertIn("_cancel_topmost_pulse", park)
        self.assertIn("_cancel_topmost_pulse", hide)
        self.assertIn("_unown_overlay", park)
        self.assertIn("_unown_overlay", hide)

    def test_overlay_anchors_to_paste_target_not_tray(self):
        from yo.overlay_win import _pos_outside_rect, _skip_attach

        self.assertTrue(_skip_attach("TopLevelWindowForOverflowXamlIsland"))
        self.assertTrue(_skip_attach("Windows.UI.Input.InputSite.WindowClass"))
        self.assertTrue(_skip_attach("NotifyIconOverflowWindow"))
        self.assertTrue(_skip_attach("Shell_TrayWnd"))
        self.assertTrue(_skip_attach("Progman"))
        self.assertFalse(_skip_attach("ConsoleWindowClass"))
        self.assertFalse(_skip_attach("consolewindowclass"))
        self.assertFalse(_skip_attach("via"))
        grok = (0, 0, 1280, 1440)
        self.assertTrue(_pos_outside_rect(1846, 919, 200, 186, grok))
        self.assertTrue(_pos_outside_rect(1846, 919, 200, 186, (0, 0, 960, 1080)))
        self.assertFalse(_pos_outside_rect(540, 1238, 200, 186, grok))
        self.assertFalse(_pos_outside_rect(860, 900, 200, 186, (0, 0, 960, 1080)))
        src = Path(project_root() / "yo" / "overlay_win.py").read_text(encoding="utf-8")
        self.assertIn("def set_anchor", src)
        self.assertIn("def _resolve_anchor", src)
        self.assertIn("_own_to_foreground(hwnd, anchor)", src)
        self.assertIn("оверлей привязан к окну", src)
        place = src[src.index("def _place") : src.index("def _root_hwnd")]
        self.assertIn("_pos_outside_rect", place)
        self.assertIn("_monitor_work_area", place)
