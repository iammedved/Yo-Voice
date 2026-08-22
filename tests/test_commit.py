import unittest
from pathlib import Path

from yo.paths import project_root
from yo.session import accept_asr_commit


class AcceptAsrCommitTests(unittest.TestCase):
    def test_keeps_older_utterance_in_same_session(self):
        self.assertTrue(
            accept_asr_commit(
                token=3,
                current_token=3,
                listening=True,
                stopping=False,
            )
        )

    def test_keeps_chunk_while_stopping(self):
        self.assertTrue(
            accept_asr_commit(
                token=3,
                current_token=3,
                listening=True,
                stopping=True,
            )
        )

    def test_drops_previous_listen_session(self):
        self.assertFalse(
            accept_asr_commit(
                token=3,
                current_token=4,
                listening=True,
                stopping=False,
            )
        )


class CommitRawWiringTests(unittest.TestCase):
    def test_does_not_drop_when_later_utterance_started(self):
        src = (project_root() / "yo" / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("utt != self._utt", src)
        self.assertIn("accept_asr_commit", src)
