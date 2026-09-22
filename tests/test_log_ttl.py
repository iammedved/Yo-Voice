"""Журнал диктовки живёт 6 часов и не возрождается, пока кот снова не пишет."""

import logging
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

from yo.logutil import (
    DICTATION_LOG_TTL_S,
    ExpiringFileHandler,
    expire_dictation_log,
)


def _stamp(when: float) -> str:
    return datetime.fromtimestamp(when).strftime("%Y-%m-%d %H:%M:%S")


def _write(path: Path, when: float, text: str) -> None:
    path.write_text(f"{_stamp(when)},000 INFO yo.app: {text}\n", encoding="utf-8")


class DictationLogTtlTests(unittest.TestCase):
    def test_young_log_stays(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "daemon.log"
            now = time.time()
            _write(path, now - 60, "свежая фраза")
            self.assertFalse(expire_dictation_log(path, now=now))
            self.assertIn("свежая фраза", path.read_text(encoding="utf-8"))

    def test_log_older_than_six_hours_is_deleted_without_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "daemon.log"
            now = time.time()
            _write(path, now - DICTATION_LOG_TTL_S - 5, "старая фраза")
            self.assertTrue(expire_dictation_log(path, now=now))
            self.assertFalse(path.exists())

    def test_exactly_six_hours_is_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "daemon.log"
            now = time.time()
            _write(path, now - DICTATION_LOG_TTL_S, "ровно шесть")
            self.assertTrue(expire_dictation_log(path, now=now))
            self.assertFalse(path.exists())

    def test_just_under_six_hours_stays(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "daemon.log"
            now = time.time()
            _write(path, now - DICTATION_LOG_TTL_S + 90, "ещё жив")
            self.assertFalse(expire_dictation_log(path, now=now))
            self.assertTrue(path.is_file())

    def test_old_backup_goes_young_log_and_other_files_stay(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            path = folder / "daemon.log"
            backup = folder / "daemon.log.bak-old"
            config = folder / "config.json"
            now = time.time()
            _write(path, now - 30, "текущая")
            _write(backup, now - DICTATION_LOG_TTL_S - 10, "архив")
            config.write_text("{}\n", encoding="utf-8")
            self.assertTrue(expire_dictation_log(path, now=now))
            self.assertIn("текущая", path.read_text(encoding="utf-8"))
            self.assertFalse(backup.exists())
            self.assertTrue(config.is_file())

    def test_next_dictation_creates_a_new_file_without_the_old_phrase(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "daemon.log"
            now = time.time()
            _write(path, now - DICTATION_LOG_TTL_S - 30, "секретная фраза")
            logger = logging.getLogger("yo.test.logttl")
            logger.handlers.clear()
            logger.propagate = False
            logger.setLevel(logging.INFO)
            handler = ExpiringFileHandler(path, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
            logger.addHandler(handler)
            try:
                self.assertTrue(expire_dictation_log(path, now=time.time()))
                self.assertFalse(path.exists())
                logger.info("новая фраза")
                handler.flush()
                text = path.read_text(encoding="utf-8")
            finally:
                logger.removeHandler(handler)
                handler.close()
            self.assertNotIn("секретная", text)
            self.assertIn("новая фраза", text)

    def test_missing_log_is_not_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "daemon.log"
            self.assertFalse(expire_dictation_log(path, now=time.time()))
            self.assertFalse(path.exists())
