"""Long dictation must reach the field even when the clipboard will not hold it."""

import importlib
import logging
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from yo.cliptext import clipboard_text, describe_mismatch, same_clipboard_text

LONG = (
    "Смотри, значит, я тебе отправляю два скриншота, на которых, значит, указано на втором. "
    "Вот загрузить реализации. " * 30
).strip()


class ClipTextTests(unittest.TestCase):
    def test_nul_is_dropped_because_it_ends_a_clipboard_string(self):
        self.assertEqual(clipboard_text("до\x00после"), "допосле")
        self.assertEqual(clipboard_text(None), "")

    def test_crlf_conversion_by_another_program_is_not_a_mismatch(self):
        self.assertTrue(same_clipboard_text("а\r\nб", "а\nб"))
        self.assertFalse(same_clipboard_text(None, ""))
        self.assertFalse(same_clipboard_text("а", "б"))

    def test_mismatch_description_has_sizes_not_the_dictation(self):
        got = describe_mismatch(LONG[:500], LONG)
        self.assertIn("got=500", got)
        self.assertIn(f"want={len(LONG)}", got)
        self.assertIn("diff_at=500", got)
        self.assertNotIn("Смотри", got)
        self.assertEqual(describe_mismatch(None, "абв"), "got=no-text want=3")


def _load_clip_win():
    """Import yo.clip_win against a fake Win32 layer (the logic, not the API)."""
    fake = SimpleNamespace(
        CF_UNICODETEXT=13,
        GMEM_MOVEABLE=2,
        kernel32=mock.MagicMock(),
        user32=mock.MagicMock(),
    )
    with mock.patch.dict(sys.modules, {"yo.winapi": fake}):
        sys.modules.pop("yo.clip_win", None)
        module = importlib.import_module("yo.clip_win")
    sys.modules.pop("yo.clip_win", None)
    return module


class FakeBoard:
    """Clipboard with an optional program that rewrites whatever we put there."""

    def __init__(self, text=None, *, rewrite=None, fail_set=False):
        self.text = text
        self.seq = 1
        self.rewrite = rewrite
        self.fail_set = fail_set
        self.writes: list[str] = []

    def set_once(self, text):
        if self.fail_set:
            from_err = OSError("SetClipboardData err=5")
            raise from_err
        self.writes.append(text)
        self.text = text
        self.seq += 1
        seq = self.seq
        if self.rewrite is not None:
            self.text = self.rewrite(text)
            self.seq += 1
        return seq

    def read(self, retries=50):
        return True, self.text


class ClipboardSetTests(unittest.TestCase):
    def setUp(self):
        self.clip = _load_clip_win()

    def run_set(self, board, text, previous_reads=None):
        with (
            mock.patch.object(self.clip, "_clipboard_set_once", side_effect=board.set_once),
            mock.patch.object(self.clip, "_read_clipboard", side_effect=board.read),
            mock.patch.object(self.clip, "_sequence", side_effect=lambda: board.seq),
            mock.patch.object(self.clip, "_owner_label", return_value="owner=sync.exe"),
            mock.patch.object(self.clip.time, "sleep"),
        ):
            self.clip.clipboard_set(text)

    def test_untouched_clipboard_is_trusted_by_sequence_number(self):
        board = FakeBoard("старое")
        with mock.patch.object(board, "read", wraps=board.read) as reads:
            self.run_set(board, LONG)
        self.assertEqual(board.text, LONG)
        self.assertEqual(reads.call_count, 1)  # only the "previous" snapshot

    def test_crlf_rewrite_by_another_program_is_accepted(self):
        board = FakeBoard(rewrite=lambda t: t.replace("\n", "\r\n"))
        self.run_set(board, "строка один\nстрока два")
        self.assertEqual(board.writes, ["строка один\nстрока два"])

    def test_text_with_nul_goes_on_without_it(self):
        board = FakeBoard()
        self.run_set(board, "раз\x00два")
        self.assertEqual(board.writes, ["раздва"])

    def test_program_that_keeps_replacing_text_raises_and_keeps_our_text_placed(self):
        board = FakeBoard("прежний буфер", rewrite=lambda t: t[:200])
        with self.assertRaises(self.clip.ClipboardError) as caught:
            self.run_set(board, LONG)
        err = caught.exception
        self.assertTrue(err.placed)
        self.assertIn("changed by another program", str(err))
        self.assertIn("owner=sync.exe", str(err))
        self.assertIn("got=200", str(err))
        self.assertNotIn("Смотри", str(err))
        self.assertEqual(len(board.writes), self.clip.SET_ATTEMPTS)
        # The old clipboard is not put back over the dictation.
        self.assertNotIn("прежний буфер", board.writes)

    def test_set_that_never_succeeds_puts_previous_back(self):
        board = FakeBoard("прежний буфер", fail_set=True)
        restored: list[str] = []

        def set_once(text):
            if text == "прежний буфер":
                restored.append(text)
                return 1
            return board.set_once(text)

        with (
            mock.patch.object(self.clip, "_clipboard_set_once", side_effect=set_once),
            mock.patch.object(self.clip, "_read_clipboard", side_effect=board.read),
            mock.patch.object(self.clip, "_sequence", side_effect=lambda: board.seq),
            mock.patch.object(self.clip.time, "sleep"),
        ):
            with self.assertRaises(self.clip.ClipboardError) as caught:
                self.clip.clipboard_set(LONG)
        self.assertFalse(caught.exception.placed)
        self.assertEqual(restored, ["прежний буфер"])

    def test_busy_clipboard_is_reread_before_giving_up(self):
        board = FakeBoard(rewrite=lambda t: t)  # same text, new sequence number
        answers = iter([(True, None), (False, None), (False, None), (True, LONG)])
        with (
            mock.patch.object(self.clip, "_clipboard_set_once", side_effect=board.set_once),
            mock.patch.object(self.clip, "_read_clipboard", side_effect=lambda retries=50: next(answers)),
            mock.patch.object(self.clip, "_sequence", side_effect=lambda: board.seq),
            mock.patch.object(self.clip.time, "sleep"),
        ):
            self.clip.clipboard_set(LONG)
        self.assertEqual(board.writes, [LONG])


_APP = []


def _import_app():
    if _APP:
        return _APP[0]
    stubs = {
        name: mock.MagicMock()
        for name in (
            "yo.loop",
            "yo.loop_linux",
            "yo.overlay",
            "yo.overlay_linux",
            "yo.hotkey",
            "yo.hotkey_linux",
            "yo.inject",
            "yo.inject_linux",
            "yo.ipc",
        )
    }
    try:
        with mock.patch.dict(sys.modules, stubs):
            sys.modules.pop("yo.app", None)
            module = importlib.import_module("yo.app")
        sys.modules.pop("yo.app", None)
        _APP.append(module)
        return module
    except Exception as exc:  # audio / model libs missing on this machine
        raise unittest.SkipTest(f"yo.app does not import here: {exc}")


class FlushPasteTests(unittest.TestCase):
    def setUp(self):
        self.app_mod = _import_app()
        self.timeouts: list = []
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

    def make_app(self):
        app = self.app_mod.YoApp.__new__(self.app_mod.YoApp)
        app._paste_q = []
        app._paste_armed = True
        app._clip_owned = False
        app._saved_clip = None
        app._paste_fail = 0
        app._pending_pastes = 0
        app._paste_hwnd = 0
        app._overlay_hwnd = 0
        app.overlay = SimpleNamespace(visible=False)
        app.session = SimpleNamespace(listening=False, task="transcribe")
        app.injector = mock.MagicMock()
        app._show_defect = mock.MagicMock()
        return app

    def drain(self, app):
        app._flush_paste()
        for _ in range(20):
            due = [cb for _, cb in self.timeouts if cb == app._flush_paste]
            self.timeouts.clear()
            if not due:
                return
            app._flush_paste()

    def patches(self, platform, clip_error=None):
        clip_set = mock.MagicMock(side_effect=clip_error)
        return clip_set, (
            mock.patch.object(self.app_mod.sys, "platform", platform),
            mock.patch.object(self.app_mod, "clipboard_set", clip_set),
            mock.patch.object(self.app_mod, "clipboard_get", return_value="прежний"),
            mock.patch.object(
                self.app_mod, "timeout_add", side_effect=lambda ms, cb, *a: self.timeouts.append((ms, cb))
            ),
        )

    def test_windows_types_text_when_clipboard_refuses_it(self):
        app = self.make_app()
        app._paste_q = [LONG]
        app.injector.paste.return_value = True
        clip_set, ps = self.patches("win32", OSError("clipboard changed by another program"))
        with ps[0], ps[1], ps[2], ps[3]:
            self.drain(app)
        self.assertEqual(clip_set.call_count, 3)
        app.injector.paste.assert_called_once_with(hwnd=None, overlay_hwnd=None, text=LONG)
        app._show_defect.assert_not_called()
        self.assertFalse(app._paste_armed)
        self.assertEqual(app._paste_fail, 0)

    def test_text_is_saved_to_disk_when_typing_fails_too(self):
        app = self.make_app()
        app._paste_q = [LONG]
        app.injector.paste.return_value = False
        clip_set, ps = self.patches("win32", OSError("clipboard changed by another program"))
        with tempfile.TemporaryDirectory() as tmp, ps[0], ps[1], ps[2], ps[3]:
            with mock.patch("yo.paths.xdg_cache", return_value=Path(tmp)):
                self.drain(app)
            saved = (Path(tmp) / self.app_mod.LOST_TEXT_FILE).read_text(encoding="utf-8")
        self.assertEqual(saved, LONG)
        app._show_defect.assert_called_once()
        action, err, block = app._show_defect.call_args.args
        self.assertEqual(block, "paste")
        self.assertIn("lost-dictation.txt", str(err))
        self.assertNotIn(tmp, str(err))

        from datetime import datetime

        from yo.report import build_report

        report = build_report(action, err, block=block, now=datetime(2026, 10, 15))
        self.assertEqual(report.code, "YO-PASTE-01")
        self.assertIn("lost-dictation.txt", report.why)

    def test_failed_text_does_not_eat_the_next_ones_retries(self):
        app = self.make_app()
        app._paste_q = ["первая", "вторая"]
        calls: list[str] = []

        def flaky(text):
            calls.append(text)
            if text == "первая" or calls.count("вторая") < 3:
                raise OSError("clipboard busy")

        clip_set, ps = self.patches("linux", None)
        clip_set.side_effect = flaky
        with tempfile.TemporaryDirectory() as tmp, ps[0], ps[1], ps[2], ps[3]:
            with mock.patch("yo.paths.xdg_cache", return_value=Path(tmp)):
                self.drain(app)
        # The second text still gets its own three tries and is pasted.
        self.assertEqual(calls.count("первая"), 3)
        self.assertEqual(calls.count("вторая"), 3)
        app.injector.paste.assert_called_once()

    def test_restore_waits_for_a_paste_still_retrying(self):
        app = self.make_app()
        app._paste_q = ["текст"]
        app._clip_owned = True
        app._saved_clip = "прежний"
        _, ps = self.patches("linux", None)
        with ps[0], ps[1], ps[2], ps[3]:
            app._restore_clipboard()
        self.assertTrue(app._clip_owned)
        self.assertEqual(self.timeouts[0][1], app._restore_clipboard)


class PlaceholderTests(unittest.TestCase):
    def test_continuation_keeps_domain_at_start_and_never_leaks_nul(self):
        from yo.polish import polish_ru

        for text in ("google.com это сайт", "yandex.ru. вот", "вот yandex.ru и google.com"):
            for continuation in (False, True):
                out = polish_ru(text, finalize=True, continuation=continuation)
                self.assertNotIn("\x00", out)
                self.assertFalse(any("" <= ch <= "" for ch in out), out)
        self.assertEqual(polish_ru("google.com это сайт", continuation=True), "google.com это сайт")

    def test_user_rule_on_a_letter_cannot_break_held_codex(self):
        from yo.terms import apply_brand_terms

        out = apply_brand_terms("уголовный кодекс", rules=(("k", "КАПУТ"), ("d", "X")))
        self.assertEqual(out, "уголовный кодекс")


if __name__ == "__main__":
    unittest.main()
