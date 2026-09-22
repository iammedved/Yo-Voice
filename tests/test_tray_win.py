import unittest

from yo.tray_win import (
    INTRO_BALLOON,
    NIF_INFO,
    NIF_REALTIME,
    NIN_BALLOONHIDE,
    NIN_BALLOONSHOW,
    NIN_BALLOONTIMEOUT,
    NIN_BALLOONUSERCLICK,
    NIN_SELECT,
    TrayIcon,
    is_balloon_event,
    is_tray_menu_event,
    is_tray_toggle_event,
)
from yo.winapi import WM_CONTEXTMENU, WM_LBUTTONUP, WM_RBUTTONUP


class TrayEventTests(unittest.TestCase):
    def test_balloon_events_do_not_toggle_or_open_menu(self):
        for event in (
            NIN_BALLOONSHOW,
            NIN_BALLOONHIDE,
            NIN_BALLOONTIMEOUT,
            NIN_BALLOONUSERCLICK,
        ):
            self.assertTrue(is_balloon_event(event))
            self.assertFalse(is_tray_toggle_event(event))
            self.assertFalse(is_tray_menu_event(event))

    def test_left_click_and_version4_select_toggle(self):
        self.assertTrue(is_tray_toggle_event(WM_LBUTTONUP))
        self.assertTrue(is_tray_toggle_event(NIN_SELECT))
        self.assertFalse(is_balloon_event(WM_LBUTTONUP))

    def test_right_click_opens_menu(self):
        self.assertTrue(is_tray_menu_event(WM_RBUTTONUP))
        self.assertTrue(is_tray_menu_event(WM_CONTEXTMENU))
        self.assertFalse(is_tray_toggle_event(WM_RBUTTONUP))

    def test_right_click_burst_opens_one_menu(self):
        pops: list[str] = []
        toggles: list[str] = []
        tray = TrayIcon(on_toggle=lambda: toggles.append("t"))
        tray._popup = lambda: pops.append("m")  # type: ignore[method-assign]
        tray._arm_flush = lambda: setattr(tray, "_flush_armed", True)  # type: ignore[method-assign]
        tray._on_tray(WM_RBUTTONUP)
        tray._on_tray(WM_CONTEXTMENU)
        tray._flush()
        self.assertEqual(pops, ["m"])
        self.assertEqual(toggles, [])

    def test_overflow_select_plus_menu_is_one_menu_not_toggle(self):
        toggles: list[str] = []
        pops: list[str] = []
        tray = TrayIcon(on_toggle=lambda: toggles.append("t"))
        tray._popup = lambda: pops.append("m")  # type: ignore[method-assign]
        tray._arm_flush = lambda: setattr(tray, "_flush_armed", True)  # type: ignore[method-assign]
        tray._on_tray(NIN_SELECT)
        tray._on_tray(WM_CONTEXTMENU)
        tray._on_tray(WM_RBUTTONUP)
        tray._flush()
        self.assertEqual(pops, ["m"])
        self.assertEqual(toggles, [])

    def test_legacy_and_v4_left_click_toggle_once(self):
        toggles: list[str] = []
        tray = TrayIcon(on_toggle=lambda: toggles.append("t"))
        tray._arm_flush = lambda: setattr(tray, "_flush_armed", True)  # type: ignore[method-assign]
        tray._on_tray(WM_LBUTTONUP)
        tray._on_tray(NIN_SELECT)
        tray._flush()
        self.assertEqual(toggles, ["t"])

    def test_intro_text_is_the_user_facing_toast(self):
        self.assertIn("Ёхо в трее", INTRO_BALLOON)
        self.assertIn("ё", INTRO_BALLOON)


class TrayNidTests(unittest.TestCase):
    def _tray(self) -> TrayIcon:
        tray = TrayIcon()
        tray._hwnd = 1
        tray._icon = 0
        tray._added = True
        return tray

    def test_empty_or_missing_info_does_not_set_nif_info(self):
        tray = self._tray()
        for info in (None, ""):
            nid = tray._nid(0, balloon=True, info=info)
            self.assertEqual(nid.uFlags & NIF_INFO, 0, msg=repr(info))
            self.assertEqual(nid.szInfo, "")

    def test_nonempty_body_sets_nif_info_and_realtime(self):
        tray = self._tray()
        nid = tray._nid(0, balloon=True, info=INTRO_BALLOON)
        self.assertEqual(nid.uFlags & NIF_INFO, NIF_INFO)
        self.assertEqual(nid.uFlags & NIF_REALTIME, NIF_REALTIME)
        self.assertIn("Ёхо в трее", nid.szInfo)

    def test_balloon_false_never_sets_nif_info(self):
        tray = self._tray()
        nid = tray._nid(0, balloon=False, info=INTRO_BALLOON)
        self.assertEqual(nid.uFlags & NIF_INFO, 0)
        self.assertEqual(nid.szInfo, "")

    def test_clear_balloon_does_not_call_notify(self):
        tray = self._tray()
        tray._balloon_pending = True
        tray._balloon_text = INTRO_BALLOON
        calls: list = []
        tray._notify = lambda *a, **k: calls.append((a, k)) or True  # type: ignore[method-assign]
        tray._clear_balloon()
        self.assertFalse(tray._balloon_pending)
        self.assertEqual(tray._balloon_text, "")
        self.assertEqual(calls, [])

    def test_hide_timeout_click_do_not_notify(self):
        tray = self._tray()
        calls: list = []
        tray._notify = lambda *a, **k: calls.append((a, k)) or True  # type: ignore[method-assign]
        for event in (NIN_BALLOONHIDE, NIN_BALLOONTIMEOUT, NIN_BALLOONUSERCLICK):
            tray._on_tray(event)
        self.assertEqual(calls, [])

    def test_show_message_dedup_same_body(self):
        tray = self._tray()
        calls: list = []
        tray._notify = lambda *a, **k: calls.append((a, k)) or True  # type: ignore[method-assign]
        tray.show_message(INTRO_BALLOON)
        tray.show_message(INTRO_BALLOON)
        self.assertEqual(len(calls), 1)
        tray._clear_balloon()
