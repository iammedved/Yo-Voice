import sys
import threading
import unittest
from pathlib import Path


class WindowsPortTests(unittest.TestCase):
    def test_facades_do_not_import_x11_or_gtk(self):
        for name in list(sys.modules):
            if name == "gi" or name.startswith("gi.") or name == "Xlib" or name.startswith("Xlib."):
                sys.modules.pop(name, None)
        import yo.hotkey  # noqa: F401
        import yo.inject  # noqa: F401
        import yo.ipc  # noqa: F401
        import yo.overlay  # noqa: F401
        import yo.paths  # noqa: F401

        self.assertNotIn("gi", sys.modules)
        self.assertFalse(any(n.startswith("gi.") for n in sys.modules))
        self.assertNotIn("Xlib", sys.modules)
        self.assertFalse(any(n.startswith("Xlib.") for n in sys.modules))
        if sys.platform == "win32":
            self.assertTrue(yo.hotkey.HotkeyWatcher.__module__.endswith("hotkey_win"))
            self.assertTrue(yo.overlay.Overlay.__module__.endswith("overlay_win"))
            self.assertTrue(yo.inject.Injector.__module__.endswith("inject_win"))
            self.assertTrue(yo.ipc.IpcServer.__module__.endswith("ipc_win"))

    def test_grave_keycode_maps_to_vk_oem_3(self):
        from yo.hotkey_win import VK_OEM_3, vk_from_code, vk_label

        self.assertEqual(vk_from_code(49), VK_OEM_3)
        self.assertEqual(VK_OEM_3, 0xC0)
        self.assertEqual(vk_from_code(0xC0), 0xC0)
        self.assertEqual(vk_label(49), "ё")
        self.assertEqual(vk_label(0xC0), "ё")

    def test_keyboard_hook_lets_shift_yo_through(self):
        src = Path(__file__).resolve().parents[1].joinpath("yo", "hotkey_win.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("WH_KEYBOARD_LL", src)
        self.assertIn("RegisterHotKey would swallow", src)
        self.assertIn("_mods_down", src)
        self.assertIn("return 1", src)

    def test_windows_paths_use_appdata(self):
        from yo.paths import socket_path, xdg_cache, xdg_config

        if sys.platform != "win32":
            self.skipTest("Windows paths")
        config = xdg_config()
        cache = xdg_cache()
        appdata = Path(__import__("os").environ["APPDATA"])
        local = Path(__import__("os").environ["LOCALAPPDATA"])
        self.assertEqual(config, appdata / "yo-voice")
        self.assertEqual(cache, local / "yo-voice")
        self.assertEqual(socket_path(), local / "yo-voice" / "yo.port")

    def test_dictation_restores_clipboard_translate_does_not(self):
        from yo.bind import restore_clipboard_after_paste

        if sys.platform == "win32":
            self.assertFalse(restore_clipboard_after_paste(task="transcribe"))
            self.assertFalse(restore_clipboard_after_paste(task="translate"))
        else:
            self.assertTrue(restore_clipboard_after_paste(task="transcribe"))
            self.assertFalse(restore_clipboard_after_paste(task="translate"))

    def test_inject_detects_windows_terminal_preview(self):
        from yo.inject_win import TERMINAL_CLASSES, TERMINAL_EXES, TERMINAL_HINTS

        self.assertIn("windowsterminal.exe", TERMINAL_EXES)
        self.assertIn("windowsterminalpreview.exe", TERMINAL_EXES)
        self.assertNotIn("conhost.exe", TERMINAL_EXES)
        self.assertNotIn("consolewindowclass", TERMINAL_CLASSES)
        blob = " ".join(TERMINAL_HINTS)
        self.assertIn("windowsterminalpreview", blob)

    def test_mouse_ptt_swallows_xbutton(self):
        src = Path(__file__).resolve().parents[1].joinpath("yo", "hotkey_win.py").read_text(
            encoding="utf-8"
        )
        mouse = src[src.index("def _mouse_hook") : src.index("def _hits_overlay")]
        self.assertIn("return 1", mouse)
        self.assertIn("_button_up_from_ll", mouse)
        self.assertIn("CallNextHookEx", mouse)

    def test_ipc_localhost_ping(self):
        if sys.platform != "win32":
            self.skipTest("Windows IPC")
        from yo.ipc_win import IpcServer, daemon_alive, send_command
        from yo.paths import socket_path

        def handler(command: str) -> str:
            return "ok"

        server = IpcServer(handler)
        server.start()
        for _ in range(50):
            if socket_path().exists():
                break
            threading.Event().wait(0.05)
        else:
            server.stop()
            self.fail("IPC port file was not created")
        try:
            self.assertTrue(daemon_alive())
            self.assertEqual(send_command("ping"), "pong")
            self.assertEqual(send_command("status"), "ok")
        finally:
            server.stop()
            server.join(timeout=2.0)

    def test_autostart_command_is_user_level_pythonw(self):
        from yo.autostart_win import VALUE_NAME, command

        cmd = command()
        self.assertIn("-m yo daemon", cmd)
        self.assertTrue(cmd.lower().endswith(' -m yo daemon') or "pythonw" in cmd.lower() or "python" in cmd.lower())
        self.assertEqual(VALUE_NAME, "Yo-Voice")
        self.assertNotIn("powershell", cmd.lower())

    def test_frozen_double_click_starts_daemon(self):
        from yo.__main__ import default_command

        self.assertEqual(default_command(frozen=True, platform="win32"), "daemon")
        self.assertEqual(default_command(frozen=False, platform="win32"), "toggle")
        self.assertEqual(default_command(frozen=True, platform="linux"), "toggle")
        self.assertEqual(default_command(frozen=False, platform="linux"), "toggle")
        root = Path(__file__).resolve().parents[1]
        src = (root / "yo" / "__main__.py").read_text(encoding="utf-8")
        self.assertIn("default=default_command()", src)
        self.assertIn("_report_fatal", src)
        self.assertIn("MessageBoxW", src)
        self.assertIn("FILE_TYPE_PIPE", src)
        self.assertIn("GetFileType", src)
        app = (root / "yo" / "app.py").read_text(encoding="utf-8")
        self.assertIn("TrayIcon", app)
        self.assertIn("claim_singleton", app)
        ipc = (root / "yo" / "ipc_win.py").read_text(encoding="utf-8")
        self.assertIn("_pid_alive", ipc)
        self.assertIn("if not path.exists()", ipc)
        alive_fn = ipc[ipc.index("def daemon_alive") : ipc.index("def send_command")]
        self.assertLess(alive_fn.index("if _pid_alive()"), alive_fn.index("sock.unlink()"))
        tray = (root / "yo" / "tray_win.py").read_text(encoding="utf-8")
        self.assertIn("Shell_NotifyIconW", tray)
        self.assertIn("Настройки", tray)
        self.assertIn("Открыть журнал", tray)
        self.assertIn("Выход", tray)
        self.assertIn("NIM_SETVERSION", tray)
        self.assertIn("is_balloon_event", tray)
        self.assertIn("INTRO_BALLOON", tray)
        self.assertIn("NIF_REALTIME", tray)
        self.assertNotIn('INTRO_BALLOON if info is None', tray)
        self.assertNotIn('balloon=True, info=""', tray)
        self.assertIn("def restore", tray)
        self.assertIn("balloon: bool = False", tray)
        cfg = (root / "yo" / "config.py").read_text(encoding="utf-8")
        self.assertIn("tray_intro_shown", cfg)
        self.assertIn("def patch_config", cfg)
        self.assertIn("tray_intro_shown", app)
        self.assertIn("balloon=show_intro", app)
        self.assertIn("patch_config", app)
        iss = (root / "installer" / "yo-voice.iss").read_text(encoding="utf-8")
        self.assertIn("Yo-Voice.exe", iss)
        self.assertIn('Parameters: "daemon"', iss)
        self.assertIn('Parameters: "prefetch"', iss)
        self.assertIn("prefetch.choice", iss)
        iss_lines = [line.strip() for line in iss.splitlines()]
        self.assertIn(
            'Name: modelnow; Description: "{cm:ModelDownloadNow}"; GroupDescription: "{cm:ModelGroup}"; Flags: exclusive',
            iss_lines,
        )
        self.assertIn(
            'Name: modellater; Description: "{cm:ModelDownloadLater}"; GroupDescription: "{cm:ModelGroup}"; Flags: exclusive unchecked',
            iss_lines,
        )
        self.assertIn(
            'Name: autostart; Description: "{cm:AutostartTask}"; GroupDescription: "{cm:AutostartGroup}"',
            iss,
        )
        self.assertIn("Сообщить о сбое", tray)
        settings = (root / "yo" / "settings_win.py").read_text(encoding="utf-8")
        self.assertNotIn(".tk_popup(", settings)
        overlay = (root / "yo" / "overlay_win.py").read_text(encoding="utf-8")
        apply = overlay[overlay.index("def _apply_exstyle") : overlay.index("def _subclass_noactivate")]
        self.assertNotIn("_subclass_noactivate(", apply)
        ipc = app[app.index("def _on_ipc") : app.index("def run_daemon")]
        self.assertEqual(ipc.count('if cmd == "rebind":'), 1)
        self.assertIn("def _cancel_rebind", app)
        start_fn = app[app.index("def start_listen") : app.index("def stop_listen")]
        self.assertIn("self._cancel_rebind()", start_fn)
        stop_fn = app[app.index("def stop_listen") : app.index("def quit")]
        self.assertIn("self._cancel_rebind()", stop_fn)
        loop = (root / "yo" / "loop_win.py").read_text(encoding="utf-8")
        self.assertIn("WS_POPUP", loop)
        self.assertNotIn("HWND_MESSAGE", loop)
        wnd = loop[loop.index("def _wndproc") : loop.index("def _drain")]
        self.assertNotIn("fn(*args)", wnd)
        self.assertNotIn("_run_job", wnd)
        self.assertIn("_pending.append", wnd)
        self.assertIn("TaskbarCreated", loop)
        self.assertIn("def _drain", loop)
        settings = (root / "yo" / "settings_win.py").read_text(encoding="utf-8")
        self.assertIn("listening: bool | None = None", settings)
        self.assertIn("update_idletasks", settings)
        self.assertIn("own_loop and daemon_alive()", settings)
        self.assertIn("winfo_exists", settings)
        self.assertIn(".lift()", settings)
        self.assertNotIn("_LIVE_WIN.destroy()", settings)

    def test_overlay_exports_layout_constants(self):
        from yo.overlay import HEIGHT, WIDTH
        from yo.overlay_win import MA_NOACTIVATE, WS_EX_NOACTIVATE

        self.assertEqual(WIDTH, 200)
        self.assertEqual(HEIGHT, 186)
        self.assertEqual(WS_EX_NOACTIVATE, 0x08000000)
        self.assertEqual(MA_NOACTIVATE, 3)


if __name__ == "__main__":
    unittest.main()
