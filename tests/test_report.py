import inspect
import unittest
from dataclasses import fields
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

from yo.report import DETAIL_LIMIT, Report, build_report, issue_url

NOW = datetime(2026, 9, 22, 15, 4, 5)
UNKNOWN_WHY = "Причина не определена"
WHY_MODEL = "Речевая модель отсутствует или загрузка не удалась."
WHY_CUDA = "Библиотека NVIDIA не запустилась, распознавание может перейти на процессор."
WHY_MIC = "Микрофон не найден или звуковой вход не открылся."
WHY_PASTE = (
    "Windows не дала вставить текст (окно с повышенными правами или нажатие не дошло); "
    "текст может остаться в буфере обмена."
)

BLOCK_CODE = {
    "startup": "YO-START-01",
    "model": "YO-MODEL-01",
    "asr": "YO-ASR-01",
    "microphone": "YO-MIC-01",
    "paste": "YO-PASTE-01",
    "translate": "YO-TRANSLATE-01",
    "hotkey": "YO-HOTKEY-01",
    "overlay": "YO-OVERLAY-01",
    "cuda": "YO-CUDA-01",
    "unknown": "YO-UNKNOWN-01",
}


def _at(action, exc=None, block=None, now=NOW):
    return build_report(action, exc, block=block, now=now)


class ReportBuildTests(unittest.TestCase):
    def test_signature_is_keyword_only_for_block_and_now(self):
        sig = inspect.signature(build_report)
        self.assertEqual(list(sig.parameters), ["action", "exc", "block", "now"])
        self.assertEqual(sig.parameters["exc"].default, None)
        self.assertEqual(sig.parameters["block"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertEqual(sig.parameters["block"].default, None)
        self.assertEqual(sig.parameters["now"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIs(sig.parameters["now"].default, inspect.Parameter.empty)
        self.assertEqual(list(inspect.signature(issue_url).parameters), ["report"])
        with self.assertRaises(TypeError):
            build_report("Нажимал кнопку.")

    def test_fields_and_exact_text(self):
        report = _at("Нажимал кнопку.")
        self.assertIsInstance(report, Report)
        self.assertEqual(
            [item.name for item in fields(report)],
            ["when", "block", "code", "what", "why", "detail"],
        )
        self.assertEqual(
            report.text(),
            "\n".join(
                [
                    "Когда: 2026-09-22 15:04:05",
                    "Блок: unknown",
                    "Код: YO-UNKNOWN-01",
                    "Что делали: Нажимал кнопку.",
                    "Почему: Причина не определена",
                    "Подробности:",
                ]
            ),
        )
        self._assert_plain(report)
        with self.assertRaises(AttributeError):
            report.when = "1999-01-01 00:00:00"

    def test_when_uses_passed_clock_not_the_live_one(self):
        report = _at("Ждал.", now=datetime(2026, 1, 2, 3, 4, 5))
        self.assertEqual(report.when, "2026-01-02 03:04:05")
        self.assertEqual(report.what, "Ждал.")

    def test_action_is_kept_as_passed(self):
        action = "  Говорил в поле.  "
        report = _at(action)
        self.assertEqual(report.what, action)
        self.assertIn(f"Что делали: {action}", report.text())

    def test_model_markers(self):
        cases = (
            ("missing model", RuntimeError("missing model weights")),
            ("hf download", RuntimeError("HF download failed")),
            ("model.bin", FileNotFoundError(r"C:\cache\model.bin")),
            ("prefetch type", _PrefetchError("cache")),
            ("prefetch text", RuntimeError("PrefetchError while fetching")),
        )
        for name, exc in cases:
            with self.subTest(name=name):
                report = _at("Скачивал речь.", exc)
                self.assertEqual(report.block, "model")
                self.assertEqual(report.code, "YO-MODEL-01")
                self.assertEqual(report.why, WHY_MODEL)
                self.assertNotEqual(report.why, UNKNOWN_WHY)
                self._assert_plain(report)

    def test_chained_prefetch_is_model(self):
        try:
            try:
                raise _PrefetchError("disk")
            except _PrefetchError as inner:
                raise RuntimeError("wrapper") from inner
        except RuntimeError as exc:
            caught = exc
        report = _at("Скачивал речь.", caught)
        self.assertEqual(report.block, "model")
        self.assertEqual(report.code, "YO-MODEL-01")
        self.assertIn("RuntimeError: wrapper", report.detail)
        self.assertRegex(report.detail.splitlines()[-1], r"^test_report\.py:test_chained_prefetch_is_model:\d+$")

    def test_cuda_markers(self):
        for message in ("cuda device", "cublas64_12.dll", "CUDA"):
            with self.subTest(message=message):
                report = _at("Слушал фразу.", RuntimeError(message))
                self.assertEqual(report.block, "cuda")
                self.assertEqual(report.code, "YO-CUDA-01")
                self.assertEqual(report.why, WHY_CUDA)
                self.assertIn("NVIDIA", report.why)
                self.assertIn("процессор", report.why)
                self._assert_plain(report)

    def test_model_bin_wins_over_cuda_word(self):
        report = _at("x", RuntimeError("CUDA failed to open model.bin"))
        self.assertEqual(report.block, "model")
        self.assertEqual(report.code, "YO-MODEL-01")

    def test_microphone_markers(self):
        for message in (
            "sounddevice",
            "PortAudio",
            "подключите микрофон",
            "no input device",
        ):
            with self.subTest(message=message):
                report = _at("Слушал фразу.", RuntimeError(message))
                self.assertEqual(report.block, "microphone")
                self.assertEqual(report.code, "YO-MIC-01")
                self.assertEqual(report.why, WHY_MIC)
                self.assertIn("микрофон", report.why.casefold())
                self._assert_plain(report)

    def test_sounddevice_type_without_message(self):
        report = _at("Слушал фразу.", _SoundDeviceError())
        self.assertEqual(report.block, "microphone")
        self.assertEqual(report.code, "YO-MIC-01")

    def test_paste_markers(self):
        for message in (
            "clipboard is locked",
            "UIPI",
            "paste",
            "access denied on SendInput",
            "SendInput: Access is denied",
            "SendInput не доставил клавиши",
        ):
            with self.subTest(message=message):
                report = _at("Вставлял фразу.", RuntimeError(message))
                self.assertEqual(report.block, "paste")
                self.assertEqual(report.code, "YO-PASTE-01")
                self.assertEqual(report.why, WHY_PASTE)
                self.assertIn("Windows", report.why)
                self.assertIn("буфер", report.why)
                self.assertIn("нажатие", report.why)
                self._assert_plain(report)

    def test_access_denied_or_sendinput_alone_is_unknown(self):
        for message in ("access denied", "SendInput", "error 5"):
            with self.subTest(message=message):
                report = _at("Вставлял фразу.", RuntimeError(message))
                self.assertEqual(report.block, "unknown")
                self.assertEqual(report.code, "YO-UNKNOWN-01")
                self.assertEqual(report.why, UNKNOWN_WHY)

    def test_unknown_without_exception(self):
        report = _at("Смотрел на кота.")
        self.assertEqual(report.block, "unknown")
        self.assertEqual(report.code, "YO-UNKNOWN-01")
        self.assertEqual(report.why, UNKNOWN_WHY)
        self.assertEqual(report.detail, "")

    def test_explicit_block_when_cause_is_unknown(self):
        for block, code in BLOCK_CODE.items():
            with self.subTest(block=block):
                report = _at("Открывал окно.", RuntimeError("boom"), block=f"  {block.upper()}  ")
                self.assertEqual(report.block, block)
                self.assertEqual(report.code, code)
                self.assertEqual(report.why, UNKNOWN_WHY)
                self.assertTrue(code.startswith("YO-") and code.endswith("-01"))

    def test_invalid_block_falls_back_to_unknown(self):
        report = _at("Открывал окно.", block="mic")
        self.assertEqual(report.block, "unknown")
        self.assertEqual(report.code, "YO-UNKNOWN-01")
        self.assertEqual(report.why, UNKNOWN_WHY)

    def test_known_cause_wins_over_explicit_block(self):
        report = _at("Скачивал речь.", RuntimeError("model.bin"), block="paste")
        self.assertEqual(report.block, "model")
        self.assertEqual(report.code, "YO-MODEL-01")
        self.assertEqual(report.why, WHY_MODEL)

    def test_detail_without_traceback(self):
        report = _at("x", RuntimeError("k"))
        self.assertEqual(report.detail, "RuntimeError: k")
        self.assertEqual(_at("x", RuntimeError()).detail, "RuntimeError")
        self.assertEqual(_at("x", RuntimeError("a\nb")).detail, "RuntimeError: a\nb")

    def test_detail_top_frame_and_cap(self):
        def boom():
            raise RuntimeError("Z" * 5000)

        try:
            boom()
        except RuntimeError as exc:
            caught = exc
        report = _at("Длинная ошибка.", caught)
        self.assertEqual(len(report.detail), DETAIL_LIMIT)
        self.assertLessEqual(DETAIL_LIMIT, 1200)
        self.assertTrue(report.detail.startswith("RuntimeError: "))
        self.assertRegex(report.detail, r"test_report\.py:boom:\d+")
        self.assertNotIn("демон", report.detail)
        self.assertNotIn("daemon", report.detail.casefold())

    def _assert_plain(self, report: Report) -> None:
        text = report.text()
        self.assertNotIn("daemon", text.casefold())
        self.assertNotIn("демон", text)


class _PrefetchError(OSError):
    pass


class _SoundDeviceError(OSError):
    __module__ = "sounddevice"


class IssueUrlTests(unittest.TestCase):
    def test_url_points_at_the_public_issue_form(self):
        report = _at("Нажимал кнопку. 1+1=2 и 100% готово")
        url = issue_url(report)
        parts = urlsplit(url)
        self.assertEqual(parts.scheme, "https")
        self.assertEqual(parts.netloc, "github.com")
        self.assertEqual(parts.path, "/iammedved/Yo-Voice/issues/new")
        self.assertEqual(parts.username, None)
        self.assertEqual(parts.password, None)
        self.assertNotIn(" ", url)
        self.assertNotIn("\n", url)
        self.assertNotIn("Когда", url)
        self.assertIn("%20", url)
        self.assertNotIn("+", parts.query)
        query = parse_qs(parts.query, keep_blank_values=True)
        self.assertIn(report.code, query["title"][0])
        self.assertEqual(query["body"][0], report.text())
        self.assertIn("1+1=2", query["body"][0])
        self.assertIn("100% готово", query["body"][0])
        lowered = url.casefold()
        self.assertNotIn("ghp_", lowered)
        self.assertNotIn("github_pat_", lowered)
        self.assertNotIn("password", lowered)
        self.assertNotIn("token=", lowered)

    def test_long_report_stays_in_the_query(self):
        report = _at("Я" * 2000)
        url = issue_url(report)
        self.assertGreater(len(url), 1800)
        query = parse_qs(urlsplit(url).query, keep_blank_values=True)
        self.assertIn(report.code, query["title"][0])
        self.assertIn("Я" * 2000, query["body"][0])
        self.assertEqual(query["body"][0], report.text())

    def test_builder_import_does_not_open_a_window(self):
        import sys

        self.assertNotIn("yo.report_ui", sys.modules)
        self.assertNotIn("tkinter", sys.modules)


if __name__ == "__main__":
    unittest.main()
