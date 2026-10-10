import sys
import unittest
from pathlib import Path

from yo.play import (
    QUNS_RUNNING_D3D_FULL_SCREEN,
    game_hold_active,
    hotkey_yields_to_game,
    is_steam_game,
    set_game_hold,
    should_hold_dictation,
    window_covers_monitor,
)


SCREEN = (0, 0, 2560, 1440)


class SteamGameTests(unittest.TestCase):
    def test_steamapps_path_is_a_game(self):
        path = r"D:\SteamLibrary\steamapps\common\Hades\Hades.exe"
        self.assertTrue(is_steam_game("Hades.exe", path, "explorer.exe"))

    def test_path_match_is_case_insensitive(self):
        path = r"C:\Program Files (x86)\Steam\SteamApps\common\Game\Bin\game.EXE"
        self.assertTrue(is_steam_game("", path, ""))

    def test_non_steam_shortcut_launched_by_steam_is_a_game(self):
        self.assertTrue(is_steam_game("onimusha.exe", r"E:\Games\onimusha.exe", "steam.exe"))

    def test_steam_library_is_not_a_game(self):
        self.assertFalse(is_steam_game("steamwebhelper.exe", r"C:\Steam\steamwebhelper.exe", "steam.exe"))
        self.assertFalse(is_steam_game("steam.exe", r"C:\Steam\steam.exe", "explorer.exe"))

    def test_overlay_counts_as_still_in_the_game(self):
        self.assertTrue(is_steam_game("GameOverlayUI.exe", r"C:\Steam\GameOverlayUI.exe", "steam.exe"))

    def test_ordinary_window_is_not_a_steam_game(self):
        self.assertFalse(
            is_steam_game("windowsterminal.exe", r"C:\Windows\System32\WindowsTerminal.exe", "explorer.exe")
        )


class HoldTests(unittest.TestCase):
    def test_steam_game_holds_even_when_windowed(self):
        self.assertTrue(
            should_hold_dictation(
                exe_name="Hades.exe",
                image_path=r"D:\SteamLibrary\steamapps\common\Hades\Hades.exe",
                parent_exe="steam.exe",
                notification_state=0,
                covers_screen=False,
            )
        )

    def test_exclusive_fullscreen_holds(self):
        self.assertTrue(
            should_hold_dictation(
                exe_name="game.exe",
                image_path=r"E:\Games\game.exe",
                parent_exe="explorer.exe",
                notification_state=QUNS_RUNNING_D3D_FULL_SCREEN,
                covers_screen=True,
            )
        )

    def test_stuck_fullscreen_flag_does_not_block_a_normal_window(self):
        self.assertFalse(
            should_hold_dictation(
                exe_name="windowsterminal.exe",
                image_path=r"C:\Windows\System32\WindowsTerminal.exe",
                parent_exe="explorer.exe",
                notification_state=QUNS_RUNNING_D3D_FULL_SCREEN,
                covers_screen=False,
            )
        )

    def test_desktop_is_not_a_game_even_if_it_covers_the_screen(self):
        self.assertFalse(
            should_hold_dictation(
                exe_name="explorer.exe",
                image_path=r"C:\Windows\explorer.exe",
                parent_exe="",
                notification_state=QUNS_RUNNING_D3D_FULL_SCREEN,
                covers_screen=True,
            )
        )

    def test_unnamed_exclusive_window_still_holds(self):
        # Античит иногда не отдаёт имя процесса. Полный экран D3D всё равно игра.
        self.assertTrue(
            should_hold_dictation(
                exe_name="",
                image_path="",
                parent_exe="",
                notification_state=QUNS_RUNNING_D3D_FULL_SCREEN,
                covers_screen=True,
            )
        )

    def test_window_must_cover_the_monitor_not_just_the_work_area(self):
        self.assertTrue(window_covers_monitor(SCREEN, [SCREEN]))
        self.assertTrue(window_covers_monitor((-4, -4, 2564, 1444), [SCREEN]))
        self.assertFalse(window_covers_monitor((0, 0, 2560, 1400), [SCREEN]))
        self.assertFalse(window_covers_monitor(None, [SCREEN]))
        self.assertTrue(window_covers_monitor((1920, 0, 3840, 1080), [(1920, 0, 3840, 1080)]))


class HotkeyYieldTests(unittest.TestCase):
    def tearDown(self):
        set_game_hold(False)

    def test_flag_yields_without_asking_windows(self):
        set_game_hold(True)
        self.assertTrue(game_hold_active())
        self.assertTrue(hotkey_yields_to_game())
        set_game_hold(False)
        self.assertFalse(game_hold_active())

    def test_linux_probe_never_holds(self):
        if sys.platform == "win32":
            self.skipTest("probe is windows-only")
        from yo.play import foreground_holds_dictation

        self.assertFalse(foreground_holds_dictation())


class AppWiringTests(unittest.TestCase):
    def test_listen_stops_before_the_overlay_and_does_not_paste(self):
        src = Path(__file__).resolve().parents[1].joinpath("yo", "app.py").read_text(encoding="utf-8")
        start = src[src.index("def start_listen") : src.index("def stop_listen")]
        self.assertLess(start.index("_sync_game_hold"), start.index("session.start"))
        self.assertLess(start.index("_sync_game_hold"), start.index("show_listening"))
        drop = src[src.index("def _drop_listen") : src.index("def _preload_models")]
        self.assertNotIn("_jobs.put", drop)
        self.assertNotIn("transcribe", drop)
        self.assertIn("session.stop", drop)
        hook = Path(__file__).resolve().parents[1].joinpath("yo", "hotkey_win.py").read_text(encoding="utf-8")
        mouse = hook[hook.index("def _mouse_hook") : hook.index("def _hits_overlay")]
        self.assertLess(mouse.index("hotkey_yields_to_game"), mouse.index("return 1"))
        self.assertIn("CallNextHookEx", mouse)


if __name__ == "__main__":
    unittest.main()
