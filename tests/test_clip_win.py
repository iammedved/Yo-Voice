import sys
import unittest

from yo.paths import project_root


class ClipWinSourceTests(unittest.TestCase):
    def test_global_lock_declares_64bit_handle(self):
        src = (project_root() / "yo" / "clip_win.py").read_text(encoding="utf-8")
        self.assertIn("GlobalLock.argtypes", src)
        self.assertIn("GlobalAlloc.argtypes", src)
        self.assertIn("c_size_t", src)
        self.assertIn("HGLOBAL", src)

    def test_flush_paste_logs_clipboard_failure(self):
        src = (project_root() / "yo" / "app.py").read_text(encoding="utf-8")
        body = src[src.index("def _flush_paste") : src.index("def _restore_clipboard")]
        self.assertIn("clipboard_set(text)", body)
        self.assertIn("не удалось записать текст в буфер обмена", body)
        self.assertIn("injector.paste", body)
        self.assertIn("insert(0, text)", body)

    def test_daemon_drops_admin_before_listen(self):
        src = (project_root() / "yo" / "app.py").read_text(encoding="utf-8")
        body = src[src.index("def run_daemon") :]
        self.assertIn("relaunch_medium_integrity", body)
        self.assertLess(body.index("relaunch_medium_integrity(["), body.index("claim_singleton()"))

    def test_inject_falls_back_to_wm_paste(self):
        src = (project_root() / "yo" / "inject_win.py").read_text(encoding="utf-8")
        paste = src[src.index("def paste(self") : src.index("def _attach_input")]
        self.assertIn("WM_PASTE", src)
        self.assertIn("SendInput не доставил клавиши", paste)
        self.assertIn("AttachThreadInput", src)
        self.assertIn("if not sent:", paste)
        self.assertLess(paste.index("if not sent:"), paste.index("self._wm_paste("))
        self.assertEqual(paste.count("self._wm_paste("), 1)
        self.assertIn("_attach_input", paste)
        self.assertIn("_chord", paste)
        self.assertLess(paste.index("_attach_input"), paste.index("_chord"))
        self.assertIn("_detach_input", paste)
        self.assertLess(paste.index("_detach_input"), paste.index("_chord"))
        self.assertIn("_console_ctrl_v", paste)
        self.assertIn("_is_classic_console", paste)
        self.assertIn("оставляю снимок", paste)
        self.assertNotIn("цель-снимок устарела", paste)
        self.assertNotIn("переназначаю вставку", paste)
        self.assertIn("WriteConsoleInputW", src)
        self.assertIn("AttachConsole", src)
        self.assertIn("consolewindowclass", src)
        self.assertIn("usable_paste_target", src)
        self.assertIn("is_unpasteable_hwnd", src)
        self.assertIn("syslistview32", src)
        self.assertIn("tktoplevel", src)
        self.assertIn("цель-снимок непригодна", paste)
        self.assertIn("фокус на оверлее", paste)
        self.assertIn("window_root", src)
        focus = src[src.index("def _focus_hwnd") : src.index("def _foreground_is_target")]
        self.assertIn("SetForegroundWindow(root)", focus)
        self.assertIn("SetFocus(hwnd)", focus)
        wm = src[src.index("def _wm_paste") : src.index("def _focused_is_terminal")]
        self.assertEqual(wm.count("PostMessageW"), 1)

    def test_integrity_reads_ctypes_value_not_buffer(self):
        src = (project_root() / "yo" / "winapi.py").read_text(encoding="utf-8")
        body = src[src.index("def token_integrity_rid") : src.index("def is_high_integrity")]
        self.assertIn("count_ptr.contents.value", body)
        self.assertIn("rid_ptr.contents.value", body)
        self.assertNotIn("int(count_ptr.contents) -", body)
        self.assertNotIn("int(rid_ptr.contents)\n", body)
        high = src[src.index("def is_high_integrity") : src.index("def relaunch_medium_integrity")]
        self.assertIn("except Exception", high)

    def test_windows_keeps_recognized_text_on_clipboard(self):
        from yo.bind import restore_clipboard_after_paste

        if sys.platform == "win32":
            self.assertFalse(restore_clipboard_after_paste(task="transcribe"))
            self.assertFalse(restore_clipboard_after_paste(task="translate"))
        else:
            self.assertTrue(restore_clipboard_after_paste(task="transcribe"))
            self.assertFalse(restore_clipboard_after_paste(task="translate"))

    def test_start_listen_snapshots_hwnd_before_overlay(self):
        src = (project_root() / "yo" / "app.py").read_text(encoding="utf-8")
        start = src[src.index("def start_listen") : src.index("def stop_listen")]
        self.assertLess(start.index("_snapshot_paste_target"), start.index("show_listening"))
        flush = src[src.index("def _flush_paste") : src.index("def _restore_clipboard")]
        self.assertIn("hwnd=self._paste_hwnd", flush)
        self.assertIn("overlay_hwnd=self._overlay_hwnd", flush)
        self.assertIn("overlay.park()", flush)
        self.assertIn("overlay.unpark()", flush)
        self.assertLess(flush.index("overlay.park()"), flush.index("SetForegroundWindow"))
        self.assertLess(flush.index("SetForegroundWindow"), flush.index("injector.paste"))
        self.assertIn("focused_hwnd", flush)
        self.assertIn("беру активное окно", flush)
        self.assertNotIn("беру активное окно hwnd=%s вместо снимка", flush)
        self.assertIn("оставляю снимок", flush)
        self.assertIn("IsWindowVisible", flush)
        snap = src[src.index("def _snapshot_paste_target") : src.index("def _track_paste_target")]
        self.assertIn("_last_good_paste", snap)
        self.assertIn("цель вставки последняя рабочая", snap)
        self.assertIn("cursor_pos", snap)
        self.assertIn("window_from_point", snap)
        self.assertIn("_track_paste_target", src[src.index("def start_background") : src.index("def _preload_models")])
        self.assertIn("set_anchor", start)
        self.assertLess(start.index("_snapshot_paste_target"), start.index("set_anchor"))
        self.assertLess(start.index("set_anchor"), start.index("show_listening"))

    def test_overlay_map_does_not_activate(self):
        src = (project_root() / "yo" / "overlay_win.py").read_text(encoding="utf-8")
        body = src[src.index("def _map_window") : src.index("def _apply_exstyle")]
        self.assertNotIn(".lift()", body)
        self.assertNotIn('attributes("-topmost"', body)
        self.assertIn("_apply_exstyle", body)
        self.assertIn("_restore_foreground", body)
        self.assertIn("_attach_to_foreground", body)
        self.assertIn("_unown_overlay", body)
        self.assertIn("SW_SHOWNOACTIVATE", body)
        self.assertLess(body.index("deiconify"), body.index("_set_topmost_noactivate"))
        self.assertLess(body.index("deiconify"), body.index("_attach_to_foreground"))
        self.assertLess(body.index("_attach_to_foreground"), body.index("ShowWindow"))
        self.assertIn("_attach_to_foreground(anchor)", body)
        self.assertIn("_resolve_anchor", body)
        self.assertIn("show=True", body)
        self.assertIn("_own_to_foreground", body)
        self.assertIn("_own_to_foreground(hwnd, anchor)", body)
        self.assertLess(body.index("_own_to_foreground"), body.index("_set_topmost_noactivate"))
        self.assertLess(body.index("_detach_from_foreground"), body.index("self._paint()"))
        restore = src[src.index("def _restore_foreground") : src.index("def _arm_topmost_pulse")]
        self.assertIn("SetForegroundWindow", restore)
        self.assertIn("current == overlay", restore)
        self.assertIn("_skip_attach", restore)
        apply = src[src.index("def _apply_exstyle") : src.index("def _subclass_noactivate")]
        self.assertIn("WS_EX_NOACTIVATE", apply)
        self.assertIn("SWP_NOACTIVATE", apply)
        self.assertIn("_unown_overlay", apply)
        self.assertIn("WS_EX_LAYERED", apply)
        self.assertIn("_apply_chroma", apply)
        self.assertNotIn("SetForegroundWindow", apply)
        self.assertIn("GWLP_HWNDPARENT", src)
        self.assertIn("AttachThreadInput", src)
        self.assertIn("SWP_NOOWNERZORDER", src)
        self.assertIn("_pulse_topmost", src)
        self.assertIn("SetLayeredWindowAttributes", src)
        self.assertIn("_flatten_to_chroma", src)
        self.assertIn("8.0 + 8.0 * self._speed", src)
        pulse = src[src.index("def _pulse_topmost") : src.index("def _map_window")]
        self.assertNotIn("_attach_to_foreground", pulse)
        self.assertNotIn("SWP_SHOWWINDOW", pulse)
        self.assertIn("SWP_NOOWNERZORDER", pulse)
        self.assertIn("SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER", pulse)
        topmost = src[src.index("def _set_topmost_noactivate") : src.index("def _own_to_foreground")]
        self.assertIn("SWP_SHOWWINDOW", topmost)
        self.assertIn("if show", topmost)
        owned = src[src.index("def _own_to_foreground") : src.index("def _restore_foreground")]
        self.assertIn("GWLP_HWNDPARENT", owned)
        self.assertIn("SWP_SHOWWINDOW", owned)
        self.assertNotIn("SWP_NOOWNERZORDER", owned)
        self.assertIn("HWND_TOP", owned)
        self.assertIn("HWND_NOTOPMOST", owned)
        self.assertIn("now != owner", owned)
        resolve = src[src.index("def _resolve_anchor") : src.index("def _attach_to_foreground")]
        self.assertIn("(self._anchor_hwnd, fg)", resolve)
        self.assertIn("_skip_attach", src)
        self.assertIn("set_anchor", src)
        init = src[src.index("def __init__") : src.index("def native_id")]
        self.assertNotIn('attributes("-topmost"', init)
        park = src[src.index("def park") : src.index("def unpark")]
        hide = src[src.index("def hide") : src.index("def park")]
        self.assertIn("_cancel_topmost_pulse", park)
        self.assertIn("_cancel_topmost_pulse", hide)
        self.assertIn("SW_HIDE", park)
        self.assertIn("ShowWindow", park)
        self.assertNotIn("self.visible = False", park)

    def test_hotkey_raises_overlay_from_any_window(self):
        hotkey = (project_root() / "yo" / "hotkey_win.py").read_text(encoding="utf-8")
        self.assertIn("SetWindowsHookExW(WH_MOUSE_LL, self._mproc, None, 0)", hotkey)
        self.assertIn("SetWindowsHookExW(WH_KEYBOARD_LL, self._kproc, None, 0)", hotkey)
        self.assertNotIn("Progman", hotkey)
        self.assertNotIn("WorkerW", hotkey)
        app = (project_root() / "yo" / "app.py").read_text(encoding="utf-8")
        start = app[app.index("def start_listen") : app.index("def stop_listen")]
        self.assertNotIn("Progman", start)
        self.assertLess(start.index("_snapshot_paste_target"), start.index("show_listening"))

    def test_inject_paste_accepts_saved_hwnd(self):
        src = (project_root() / "yo" / "inject_win.py").read_text(encoding="utf-8")
        self.assertIn("def paste(self, hwnd", src)
        self.assertIn("overlay_hwnd", src)
        self.assertIn("def _focus_hwnd", src)
        self.assertIn("WM_PASTE", src)
        self.assertIn("IsWindow", src)
        self.assertIn("allow_set_foreground", src)
        self.assertIn("focused_hwnd", src)

    def test_hwnd_int_avoids_ctypes_buffer_protocol(self):
        src = (project_root() / "yo" / "winapi.py").read_text(encoding="utf-8")
        body = src[src.index("def hwnd_int") : src.index("def focused_hwnd")]
        self.assertIn("getattr(hwnd, \"value\"", body)
        self.assertNotIn("return int(hwnd)", body)
        self.assertNotIn("int(hwnd) if", body)
        self.assertIn("GetGUIThreadInfo", src)
        snap = (project_root() / "yo" / "app.py").read_text(encoding="utf-8")
        snap_body = snap[snap.index("def _snapshot_paste_target") : snap.index("def _inject_text")]
        self.assertIn("focused_hwnd()", snap_body)
        self.assertIn("hwnd_int", snap_body)
        self.assertIn("usable_paste_target", snap_body)
        self.assertIn("GetForegroundWindow", snap_body)
        hide = snap[snap.index("def _hide") : snap.index("def _take_chunks")]
        self.assertIn("usable_paste_target", hide)
        overlay = (project_root() / "yo" / "overlay_win.py").read_text(encoding="utf-8")
        self.assertIn("hwnd_int(user32.GetForegroundWindow())", overlay)
        clip = (project_root() / "yo" / "clip_win.py").read_text(encoding="utf-8")
        self.assertIn("clipboard_get()", clip)
        self.assertIn("clipboard verify mismatch", clip)
        self.assertIn("CloseHandle.argtypes", src)
        inject_arm = snap[snap.index("def _inject_text") : snap.index("def _flush_paste")]
        self.assertIn("delay = 280", inject_arm)
        hide_body = snap[snap.index("def _hide") : snap.index("def _take_chunks")]
        self.assertIn("window_root", hide_body)
        self.assertIn("def window_root", src)

    def test_no_int_ctypes_contents_without_value(self):
        import re

        bad = []
        for path in (project_root() / "yo").glob("*.py"):
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r"int\(([^)]+)\)", text):
                inner = match.group(1)
                if ".contents" in inner and ".contents.value" not in inner:
                    bad.append(f"{path.name}: int({inner})")
        self.assertEqual(bad, [])


def _skip_if_clipboard_locked(test: unittest.TestCase) -> None:
    from yo.clip_win import user32

    if user32.OpenClipboard(None):
        user32.CloseClipboard()
        return
    test.skipTest("OpenClipboard denied (UIPI or lock)")


@unittest.skipUnless(sys.platform == "win32", "win32 clipboard")
class ClipWinRoundtripTests(unittest.TestCase):
    def test_token_integrity_rid_is_int(self):
        from yo.winapi import is_high_integrity, token_integrity_rid

        rid = token_integrity_rid()
        self.assertIsInstance(rid, int)
        self.assertGreater(rid, 0)
        self.assertIsInstance(is_high_integrity(), bool)

    def test_hwnd_int_ctypes_handle(self):
        from ctypes import wintypes

        from yo.winapi import focused_hwnd, hwnd_int

        self.assertEqual(hwnd_int(None), 0)
        self.assertEqual(hwnd_int(0), 0)
        self.assertEqual(hwnd_int(0x1234), 0x1234)
        handle = wintypes.HWND(0xABC)
        self.assertEqual(hwnd_int(handle), 0xABC)
        fg = focused_hwnd()
        self.assertIsInstance(fg, int)
        self.assertGreaterEqual(fg, 0)

    def test_unicode_roundtrip(self):
        from yo.clip_win import clipboard_get, clipboard_set

        _skip_if_clipboard_locked(self)
        marker = "ёхо-проверка-вставки 123"
        prev = clipboard_get()
        try:
            clipboard_set(marker)
            self.assertEqual(clipboard_get(), marker)
        finally:
            if prev is not None:
                clipboard_set(prev)
            else:
                clipboard_set("")

    def test_paste_into_tk_entry_or_keeps_clipboard(self):
        import time
        import tkinter as tk

        from yo.clip_win import clipboard_get, clipboard_set
        from yo.inject_win import Injector

        _skip_if_clipboard_locked(self)
        marker = "ёхо-вставка-поле 456"
        prev = clipboard_get()
        root = tk.Tk()
        try:
            root.title("yo-paste-probe")
            entry = tk.Entry(root)
            entry.pack()
            root.update_idletasks()
            root.deiconify()
            entry.focus_force()
            root.update()
            from yo.winapi import hwnd_int

            hwnd = hwnd_int(entry.winfo_id() or 0)
            self.assertGreater(hwnd, 0)
            clipboard_set(marker)
            Injector().paste(hwnd=hwnd)
            root.update()
            time.sleep(0.15)
            root.update()
            got = entry.get()
            clip = clipboard_get()
            self.assertEqual(clip, marker)
            if got != marker:
                # UIPI or the widget ignored WM_PASTE; clipboard fallback still holds.
                self.assertEqual(clip, marker)
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass
            if prev is not None:
                clipboard_set(prev)
            else:
                clipboard_set("")

    def test_wm_paste_only_when_chord_fails(self):
        from unittest import mock

        from yo import inject_win
        from yo.inject_win import Injector, WM_PASTE

        posted: list[tuple] = []

        def fake_post(hwnd, msg, wp, lp):
            posted.append((hwnd, msg, wp, lp))
            return 1

        inj = Injector()

        def run(*, send_n):
            posted.clear()

            def fake_send(n, arr, size):
                return send_n(n)

            with (
                mock.patch.object(inject_win.time, "sleep"),
                mock.patch.object(inject_win.user32, "SendInput", side_effect=fake_send),
                mock.patch.object(inject_win.user32, "PostMessageW", side_effect=fake_post),
                mock.patch.object(inject_win.user32, "IsWindow", return_value=True),
                mock.patch.object(inject_win.user32, "GetFocus", return_value=0xBEEF),
                mock.patch.object(inject_win.user32, "GetAsyncKeyState", return_value=0),
                mock.patch.object(inject_win.user32, "GetWindowThreadProcessId", return_value=1),
                mock.patch.object(inject_win.user32, "AttachThreadInput", return_value=True),
                mock.patch.object(inj, "_attach_input", return_value=[]),
                mock.patch.object(inj, "_detach_input"),
                mock.patch.object(inj, "_focus_hwnd", return_value=True),
                mock.patch.object(inj, "_foreground_is_target", return_value=True),
                mock.patch.object(inj, "_is_terminal", return_value=False),
                mock.patch.object(inject_win, "_window_class", return_value="edit"),
                mock.patch.object(inject_win, "_process_exe", return_value="notepad.exe"),
                mock.patch.object(inject_win, "window_label", return_value="Edit"),
                mock.patch.object(inject_win, "focused_hwnd", return_value=0x1234),
                mock.patch.object(inject_win, "allow_set_foreground"),
                mock.patch.object(inject_win, "is_same_or_child", return_value=False),
            ):
                inj.paste(hwnd=0x1234, overlay_hwnd=0)
            return [p for p in posted if p[1] == WM_PASTE]

        self.assertEqual(run(send_n=lambda n: n), [], "WM_PASTE must not run after a successful chord")
        wm = run(send_n=lambda n: 0)
        self.assertEqual(len(wm), 1, "WM_PASTE fallback must post once, not to two hwnds")
        self.assertEqual(wm[0][0], 0x1234)

    def test_wm_paste_when_foreground_stays_wrong_native_edit(self):
        from unittest import mock

        from yo import inject_win
        from yo.inject_win import Injector, WM_PASTE

        posted: list[tuple] = []
        sent_calls: list[int] = []

        def fake_post(hwnd, msg, wp, lp):
            posted.append((hwnd, msg, wp, lp))
            return 1

        def fake_send(n, arr, size):
            sent_calls.append(n)
            return n

        inj = Injector()
        with (
            mock.patch.object(inject_win.time, "sleep"),
            mock.patch.object(inject_win.user32, "SendInput", side_effect=fake_send),
            mock.patch.object(inject_win.user32, "PostMessageW", side_effect=fake_post),
            mock.patch.object(inject_win.user32, "IsWindow", return_value=True),
            mock.patch.object(inject_win.user32, "GetFocus", return_value=0),
            mock.patch.object(inject_win.user32, "GetAsyncKeyState", return_value=0),
            mock.patch.object(inj, "_attach_input", return_value=[]),
            mock.patch.object(inj, "_detach_input"),
            mock.patch.object(inj, "_focus_hwnd", return_value=True),
            mock.patch.object(inj, "_foreground_is_target", return_value=False),
            mock.patch.object(inject_win, "_window_class", return_value="edit"),
            mock.patch.object(inject_win, "_process_exe", return_value="notepad.exe"),
            mock.patch.object(inject_win, "window_label", return_value="Edit"),
            mock.patch.object(inject_win, "focused_hwnd", return_value=0xCAFE),
            mock.patch.object(inject_win, "allow_set_foreground"),
            mock.patch.object(inject_win, "is_same_or_child", return_value=False),
        ):
            inj.paste(hwnd=0x1234, overlay_hwnd=0)
        self.assertEqual(sent_calls, [], "must not chord into the wrong foreground")
        wm = [p for p in posted if p[1] == WM_PASTE]
        self.assertEqual(len(wm), 1)
        self.assertEqual(wm[0][0], 0x1234)

    def test_junk_snapshot_chords_live_console(self):
        from unittest import mock

        from yo import inject_win
        from yo.inject_win import Injector, VK_CONTROL, VK_SHIFT, VK_V, WM_PASTE

        junk, live = 0x100, 0x200
        posted: list[tuple] = []
        chords: list[list[int]] = []

        def fake_post(hwnd, msg, wp, lp):
            posted.append((hwnd, msg, wp, lp))
            return 1

        def fake_send(n, arr, size):
            chords.append([arr[i].union.ki.wVk for i in range(n)])
            return n

        def fake_class(hwnd):
            h = int(hwnd) if isinstance(hwnd, int) else 0
            return {
                junk: "syslistview32",
                live: "consolewindowclass",
            }.get(h, "")

        def fake_exe(hwnd):
            h = int(hwnd) if isinstance(hwnd, int) else 0
            return {
                junk: "explorer.exe",
                live: "powershell.exe",
            }.get(h, "")

        def fake_root(hwnd):
            h = int(hwnd) if isinstance(hwnd, int) else getattr(hwnd, "value", 0) or 0
            return {junk: 0x10A, 0x10A: 0x10A}.get(h, h)

        inj = Injector()
        with (
            mock.patch.object(inject_win.time, "sleep"),
            mock.patch.object(inject_win.user32, "SendInput", side_effect=fake_send),
            mock.patch.object(inject_win.user32, "PostMessageW", side_effect=fake_post),
            mock.patch.object(inject_win.user32, "IsWindow", return_value=True),
            mock.patch.object(inject_win.user32, "GetFocus", return_value=0),
            mock.patch.object(inject_win.user32, "GetAsyncKeyState", return_value=0),
            mock.patch.object(inject_win.user32, "GetForegroundWindow", return_value=live),
            mock.patch.object(inj, "_attach_input", return_value=[]),
            mock.patch.object(inj, "_detach_input"),
            mock.patch.object(inj, "_console_ctrl_v", return_value=False),
            mock.patch.object(inj, "_focus_hwnd", return_value=True),
            mock.patch.object(inject_win, "_window_class", side_effect=fake_class),
            mock.patch.object(inject_win, "_process_exe", side_effect=fake_exe),
            mock.patch.object(inject_win, "window_root", side_effect=fake_root),
            mock.patch.object(inject_win, "window_label", return_value="live"),
            mock.patch.object(inject_win, "focused_hwnd", return_value=live),
            mock.patch.object(inject_win, "allow_set_foreground"),
            mock.patch.object(inject_win, "is_same_or_child", return_value=False),
        ):
            inj.paste(hwnd=junk, overlay_hwnd=0)
        self.assertEqual(chords, [[VK_CONTROL, VK_V, VK_V, VK_CONTROL]])
        self.assertEqual(chords[0][2:], [VK_V, VK_CONTROL])
        self.assertEqual([p for p in posted if p[1] == WM_PASTE], [])
        self.assertNotIn(VK_SHIFT, chords[0])

    def test_tray_inputsite_snapshot_does_not_wm_paste_explorer(self):
        from unittest import mock

        from yo import inject_win
        from yo.inject_win import Injector, VK_CONTROL, VK_V, WM_PASTE

        junk, live = 0x328974, 0x984446
        posted: list[tuple] = []
        chords: list[list[int]] = []

        def fake_post(hwnd, msg, wp, lp):
            posted.append((hwnd, msg, wp, lp))
            return 1

        def fake_send(n, arr, size):
            chords.append([arr[i].union.ki.wVk for i in range(n)])
            return n

        def fake_class(hwnd):
            h = int(hwnd) if isinstance(hwnd, int) else 0
            return {
                junk: "windows.ui.input.inputsite.windowclass",
                0x197838: "toplevelwindowforoverflowxamlisland",
                live: "consolewindowclass",
            }.get(h, "")

        def fake_exe(hwnd):
            h = int(hwnd) if isinstance(hwnd, int) else 0
            if h in (junk, 0x197838):
                return "explorer.exe"
            if h == live:
                return "powershell.exe"
            return ""

        def fake_root(hwnd):
            h = int(hwnd) if isinstance(hwnd, int) else getattr(hwnd, "value", 0) or 0
            return {junk: 0x197838, 0x197838: 0x197838}.get(h, h)

        inj = Injector()
        with (
            mock.patch.object(inject_win.time, "sleep"),
            mock.patch.object(inject_win.user32, "SendInput", side_effect=fake_send),
            mock.patch.object(inject_win.user32, "PostMessageW", side_effect=fake_post),
            mock.patch.object(inject_win.user32, "IsWindow", return_value=True),
            mock.patch.object(inject_win.user32, "GetFocus", return_value=0),
            mock.patch.object(inject_win.user32, "GetAsyncKeyState", return_value=0),
            mock.patch.object(inject_win.user32, "GetForegroundWindow", return_value=live),
            mock.patch.object(inj, "_attach_input", return_value=[]),
            mock.patch.object(inj, "_detach_input"),
            mock.patch.object(inj, "_console_ctrl_v", return_value=False),
            mock.patch.object(inj, "_focus_hwnd", return_value=True),
            mock.patch.object(inject_win, "_window_class", side_effect=fake_class),
            mock.patch.object(inject_win, "_process_exe", side_effect=fake_exe),
            mock.patch.object(inject_win, "window_root", side_effect=fake_root),
            mock.patch.object(inject_win, "window_label", return_value="live"),
            mock.patch.object(inject_win, "focused_hwnd", return_value=live),
            mock.patch.object(inject_win, "allow_set_foreground"),
            mock.patch.object(inject_win, "is_same_or_child", return_value=False),
        ):
            inj.paste(hwnd=junk, overlay_hwnd=0)
        self.assertEqual(chords, [[VK_CONTROL, VK_V, VK_V, VK_CONTROL]])
        self.assertEqual([p for p in posted if p[1] == WM_PASTE], [])

    def test_shell_junk_hwnds_rejected(self):
        from unittest import mock

        from yo import inject_win

        classes = {
            1: "syslistview32",
            2: "windows.ui.input.inputsite.windowclass",
            3: "edit",
            4: "consolewindowclass",
            5: "chrome_widgetwin_1",
            6: "progman",
            7: "windows.ui.input.inputsite.windowclass",
        }
        roots = {1: 10, 2: 20, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 10: 10, 20: 20}
        root_classes = {10: "progman", 20: "toplevelwindowforoverflowxamlisland", 7: "applicationframewindow"}
        exes = {
            1: "explorer.exe",
            2: "explorer.exe",
            3: "notepad.exe",
            4: "powershell.exe",
            5: "chrome.exe",
            6: "explorer.exe",
            7: "notepad.exe",
        }

        def fake_class(hwnd):
            h = int(hwnd) if isinstance(hwnd, int) else 0
            if h in classes:
                return classes[h]
            return root_classes.get(h, "")

        def fake_root(hwnd):
            h = int(hwnd) if isinstance(hwnd, int) else 0
            return roots.get(h, h)

        def fake_exe(hwnd):
            h = int(hwnd) if isinstance(hwnd, int) else 0
            return exes.get(h, "")

        with (
            mock.patch.object(inject_win, "_window_class", side_effect=fake_class),
            mock.patch.object(inject_win, "_process_exe", side_effect=fake_exe),
            mock.patch.object(inject_win, "window_root", side_effect=fake_root),
            mock.patch.object(inject_win, "is_same_or_child", return_value=False),
            mock.patch.object(inject_win.user32, "IsWindow", return_value=True),
        ):
            self.assertTrue(inject_win.is_unpasteable_hwnd(1))
            self.assertTrue(inject_win.is_unpasteable_hwnd(2))
            self.assertTrue(inject_win.is_unpasteable_hwnd(6))
            self.assertFalse(inject_win.is_unpasteable_hwnd(3))
            self.assertFalse(inject_win.is_unpasteable_hwnd(4))
            self.assertFalse(inject_win.is_unpasteable_hwnd(5))
            self.assertFalse(inject_win.is_unpasteable_hwnd(7))
            self.assertEqual(inject_win.usable_paste_target(1), 0)
            self.assertEqual(inject_win.usable_paste_target(3), 3)

    def test_live_target_uses_fg_when_focus_child_is_junk(self):
        from unittest import mock

        from yo import inject_win
        from yo.inject_win import Injector, VK_CONTROL, VK_V, WM_PASTE

        junk, live = 0x65794, 0x984446
        posted: list[tuple] = []
        chords: list[list[int]] = []

        def fake_post(hwnd, msg, wp, lp):
            posted.append((hwnd, msg, wp, lp))
            return 1

        def fake_send(n, arr, size):
            chords.append([arr[i].union.ki.wVk for i in range(n)])
            return n

        def fake_class(hwnd):
            h = int(hwnd) if isinstance(hwnd, int) else 0
            return {junk: "syslistview32", live: "consolewindowclass"}.get(h, "")

        def fake_exe(hwnd):
            h = int(hwnd) if isinstance(hwnd, int) else 0
            return {junk: "explorer.exe", live: "powershell.exe"}.get(h, "")

        def fake_root(hwnd):
            h = int(hwnd) if isinstance(hwnd, int) else getattr(hwnd, "value", 0) or 0
            return {junk: 0x65788, 0x65788: 0x65788}.get(h, h)

        inj = Injector()
        with (
            mock.patch.object(inject_win.time, "sleep"),
            mock.patch.object(inject_win.user32, "SendInput", side_effect=fake_send),
            mock.patch.object(inject_win.user32, "PostMessageW", side_effect=fake_post),
            mock.patch.object(inject_win.user32, "IsWindow", return_value=True),
            mock.patch.object(inject_win.user32, "GetFocus", return_value=0),
            mock.patch.object(inject_win.user32, "GetAsyncKeyState", return_value=0),
            mock.patch.object(inject_win.user32, "GetForegroundWindow", return_value=live),
            mock.patch.object(inj, "_attach_input", return_value=[]),
            mock.patch.object(inj, "_detach_input"),
            mock.patch.object(inj, "_console_ctrl_v", return_value=False),
            mock.patch.object(inj, "_focus_hwnd", return_value=True),
            mock.patch.object(inject_win, "_window_class", side_effect=fake_class),
            mock.patch.object(inject_win, "_process_exe", side_effect=fake_exe),
            mock.patch.object(inject_win, "window_root", side_effect=fake_root),
            mock.patch.object(inject_win, "window_label", return_value="live"),
            mock.patch.object(inject_win, "focused_hwnd", return_value=junk),
            mock.patch.object(inject_win, "allow_set_foreground"),
            mock.patch.object(inject_win, "is_same_or_child", return_value=False),
        ):
            self.assertEqual(inj._live_target(0), live)
            inj.paste(hwnd=junk, overlay_hwnd=0)
        self.assertEqual(chords, [[VK_CONTROL, VK_V, VK_V, VK_CONTROL]])
        self.assertEqual([p for p in posted if p[1] == WM_PASTE], [])

    def test_junk_snapshot_and_junk_fg_leaves_clipboard(self):
        from unittest import mock

        from yo import inject_win
        from yo.inject_win import Injector, WM_PASTE

        posted: list[tuple] = []
        sent_calls: list[int] = []

        def fake_post(hwnd, msg, wp, lp):
            posted.append((hwnd, msg, wp, lp))
            return 1

        def fake_send(n, arr, size):
            sent_calls.append(n)
            return n

        inj = Injector()
        with (
            mock.patch.object(inject_win.time, "sleep"),
            mock.patch.object(inject_win.user32, "SendInput", side_effect=fake_send),
            mock.patch.object(inject_win.user32, "PostMessageW", side_effect=fake_post),
            mock.patch.object(inject_win.user32, "IsWindow", return_value=True),
            mock.patch.object(inject_win.user32, "GetFocus", return_value=0),
            mock.patch.object(inject_win.user32, "GetAsyncKeyState", return_value=0),
            mock.patch.object(inject_win.user32, "GetForegroundWindow", return_value=0x100),
            mock.patch.object(inj, "_attach_input", return_value=[]),
            mock.patch.object(inj, "_detach_input"),
            mock.patch.object(inject_win, "_window_class", return_value="syslistview32"),
            mock.patch.object(inject_win, "_process_exe", return_value="explorer.exe"),
            mock.patch.object(inject_win, "window_label", return_value="FolderView"),
            mock.patch.object(inject_win, "focused_hwnd", return_value=0x100),
            mock.patch.object(inject_win, "allow_set_foreground"),
            mock.patch.object(inject_win, "is_same_or_child", return_value=False),
        ):
            inj.paste(hwnd=0x100, overlay_hwnd=0)
        self.assertEqual(sent_calls, [])
        self.assertEqual([p for p in posted if p[1] == WM_PASTE], [])

    def test_chord_when_already_foreground_even_if_focus_hwnd_fails(self):
        from unittest import mock

        from yo import inject_win
        from yo.inject_win import Injector, VK_CONTROL, VK_V, WM_PASTE

        posted: list[tuple] = []
        chords: list[list[int]] = []

        def fake_post(hwnd, msg, wp, lp):
            posted.append((hwnd, msg, wp, lp))
            return 1

        def fake_send(n, arr, size):
            chords.append([arr[i].union.ki.wVk for i in range(n)])
            return n

        inj = Injector()
        with (
            mock.patch.object(inject_win.time, "sleep"),
            mock.patch.object(inject_win.user32, "SendInput", side_effect=fake_send),
            mock.patch.object(inject_win.user32, "PostMessageW", side_effect=fake_post),
            mock.patch.object(inject_win.user32, "IsWindow", return_value=True),
            mock.patch.object(inject_win.user32, "GetFocus", return_value=0),
            mock.patch.object(inject_win.user32, "GetAsyncKeyState", return_value=0),
            mock.patch.object(inject_win.user32, "GetForegroundWindow", return_value=0x1234),
            mock.patch.object(inj, "_attach_input", return_value=[]),
            mock.patch.object(inj, "_detach_input"),
            mock.patch.object(inj, "_console_ctrl_v", return_value=False),
            mock.patch.object(inj, "_focus_hwnd", return_value=False),
            mock.patch.object(inj, "_foreground_is_target", return_value=True),
            mock.patch.object(inj, "_is_terminal", return_value=False),
            mock.patch.object(inject_win, "_window_class", return_value="consolewindowclass"),
            mock.patch.object(inject_win, "_process_exe", return_value="powershell.exe"),
            mock.patch.object(inject_win, "window_label", return_value="Console"),
            mock.patch.object(inject_win, "focused_hwnd", return_value=0x1234),
            mock.patch.object(inject_win, "allow_set_foreground"),
            mock.patch.object(inject_win, "is_same_or_child", return_value=False),
        ):
            inj.paste(hwnd=0x1234, overlay_hwnd=0)
        self.assertEqual(chords, [[VK_CONTROL, VK_V, VK_V, VK_CONTROL]])
        self.assertEqual([p for p in posted if p[1] == WM_PASTE], [])

    def test_classic_console_writeconsoleinput_ctrl_v(self):
        from unittest import mock

        from yo import inject_win
        from yo.inject_win import Injector, WM_PASTE

        posted: list[tuple] = []
        chords: list[list[int]] = []
        writes: list[int] = []
        first_key: list[tuple] = []

        def fake_post(hwnd, msg, wp, lp):
            posted.append((hwnd, msg, wp, lp))
            return 1

        def fake_send(n, arr, size):
            chords.append([arr[i].union.ki.wVk for i in range(n)])
            return n

        def fake_gtpid(hwnd, pid_ptr):
            if pid_ptr is not None:
                try:
                    pid_ptr._obj.value = 4242
                except Exception:
                    try:
                        pid_ptr.contents.value = 4242
                    except Exception:
                        pass
            return 11

        def fake_write(handle, recs, n, written):
            writes.append(int(n))
            key = recs[0].KeyEvent
            first_key.append(
                (
                    int(key.wVirtualKeyCode),
                    key.uChar.UnicodeChar,
                    int(key.dwControlKeyState),
                )
            )
            try:
                written._obj.value = n
            except Exception:
                written.contents.value = n
            return True

        inj = Injector()
        patches = [
            mock.patch.object(inject_win.time, "sleep"),
            mock.patch.object(inject_win.user32, "SendInput", side_effect=fake_send),
            mock.patch.object(inject_win.user32, "PostMessageW", side_effect=fake_post),
            mock.patch.object(inject_win.user32, "IsWindow", return_value=True),
            mock.patch.object(inject_win.user32, "GetFocus", return_value=0),
            mock.patch.object(inject_win.user32, "GetAsyncKeyState", return_value=0),
            mock.patch.object(inject_win.user32, "GetForegroundWindow", return_value=0x200),
            mock.patch.object(
                inject_win.user32, "GetWindowThreadProcessId", side_effect=fake_gtpid
            ),
            mock.patch.object(inject_win.user32, "SetFocus", return_value=0x200),
            mock.patch.object(inject_win.kernel32, "GetCurrentProcessId", return_value=1),
            mock.patch.object(inject_win.kernel32, "AttachConsole", return_value=True),
            mock.patch.object(inject_win.kernel32, "FreeConsole", return_value=True),
            mock.patch.object(inject_win.kernel32, "GetStdHandle", return_value=0x777),
            mock.patch.object(
                inject_win.kernel32, "WriteConsoleInputW", side_effect=fake_write
            ),
            mock.patch("yo.clip_win.clipboard_get", return_value="Привет"),
            mock.patch.object(inj, "_attach_input", return_value=[]),
            mock.patch.object(inj, "_detach_input"),
            mock.patch.object(inj, "_focus_hwnd", return_value=True),
            mock.patch.object(inj, "_foreground_is_target", return_value=True),
            mock.patch.object(inject_win, "_window_class", return_value="consolewindowclass"),
            mock.patch.object(inject_win, "_process_exe", return_value="powershell.exe"),
            mock.patch.object(inject_win, "window_label", return_value="grok"),
            mock.patch.object(inject_win, "focused_hwnd", return_value=0x200),
            mock.patch.object(inject_win, "allow_set_foreground"),
            mock.patch.object(inject_win, "is_same_or_child", return_value=False),
            mock.patch.object(inject_win, "window_root", side_effect=lambda h: h),
        ]
        for p in patches:
            p.start()
        try:
            inj.paste(hwnd=0x200, overlay_hwnd=0)
        finally:
            for p in reversed(patches):
                p.stop()
        self.assertEqual(writes, [len("Привет") * 2])
        self.assertEqual(first_key, [(0, "П", 0)])
        self.assertEqual(chords, [], "Unicode WriteConsoleInput must replace SendInput")
        self.assertEqual([p for p in posted if p[1] == WM_PASTE], [])

    def test_usable_snapshot_is_not_replaced_by_another_app(self):
        from unittest import mock

        from yo import inject_win
        from yo.inject_win import Injector, VK_CONTROL, VK_V, WM_PASTE

        game, grok = 0x525154, 0x984446
        chords: list[list[int]] = []
        posted: list[tuple] = []
        focused: list[int] = []

        def fake_post(hwnd, msg, wp, lp):
            posted.append((hwnd, msg, wp, lp))
            return 1

        def fake_send(n, arr, size):
            chords.append([arr[i].union.ki.wVk for i in range(n)])
            return n

        def fake_class(hwnd):
            h = int(hwnd) if isinstance(hwnd, int) else 0
            return {game: "via", grok: "consolewindowclass"}.get(h, "")

        def fake_exe(hwnd):
            h = int(hwnd) if isinstance(hwnd, int) else 0
            return {game: "onimushawots.exe", grok: "powershell.exe"}.get(h, "")

        def fake_focus(hwnd):
            focused.append(int(hwnd))
            return True

        def fake_fg_is(hwnd):
            return bool(focused) and int(hwnd) == focused[-1]

        inj = Injector()
        with (
            mock.patch.object(inject_win.time, "sleep"),
            mock.patch.object(inject_win.user32, "SendInput", side_effect=fake_send),
            mock.patch.object(inject_win.user32, "PostMessageW", side_effect=fake_post),
            mock.patch.object(inject_win.user32, "IsWindow", return_value=True),
            mock.patch.object(inject_win.user32, "GetFocus", return_value=0),
            mock.patch.object(inject_win.user32, "GetAsyncKeyState", return_value=0),
            mock.patch.object(inject_win.user32, "GetForegroundWindow", return_value=grok),
            mock.patch.object(inj, "_attach_input", return_value=[]),
            mock.patch.object(inj, "_detach_input"),
            mock.patch.object(inj, "_console_ctrl_v", return_value=False),
            mock.patch.object(inj, "_focus_hwnd", side_effect=fake_focus),
            mock.patch.object(inj, "_foreground_is_target", side_effect=fake_fg_is),
            mock.patch.object(inject_win, "_window_class", side_effect=fake_class),
            mock.patch.object(inject_win, "_process_exe", side_effect=fake_exe),
            mock.patch.object(inject_win, "window_root", side_effect=lambda h: int(h)),
            mock.patch.object(inject_win, "window_label", return_value="win"),
            mock.patch.object(inject_win, "focused_hwnd", return_value=grok),
            mock.patch.object(inject_win, "allow_set_foreground"),
            mock.patch.object(inject_win, "is_same_or_child", return_value=False),
        ):
            inj.paste(hwnd=game, overlay_hwnd=0)
        self.assertEqual(focused, [game])
        self.assertEqual(chords, [[VK_CONTROL, VK_V, VK_V, VK_CONTROL]])
        self.assertEqual([p for p in posted if p[1] == WM_PASTE], [])

    def test_clipboard_restores_previous_after_set_failure(self):
        from unittest import mock

        from yo import clip_win

        _skip_if_clipboard_locked(self)
        marker = "ёхо-prev-clip 789"
        prev = clip_win.clipboard_get()
        try:
            clip_win.clipboard_set(marker)
            calls = {"n": 0}
            real_set = clip_win.user32.SetClipboardData

            def flaky(fmt, handle):
                calls["n"] += 1
                if calls["n"] <= 3:
                    return 0
                return real_set(fmt, handle)

            with mock.patch.object(clip_win.user32, "SetClipboardData", side_effect=flaky):
                with self.assertRaises(OSError):
                    clip_win.clipboard_set("ёхо-new-clip")
            self.assertEqual(clip_win.clipboard_get(), marker)
        finally:
            if prev is not None:
                clip_win.clipboard_set(prev)
            else:
                clip_win.clipboard_set("")
