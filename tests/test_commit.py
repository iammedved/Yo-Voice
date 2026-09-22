import unittest
from pathlib import Path

from yo.paths import project_root
from yo.phrases import UNRECOGNIZED
from yo.session import accept_asr_commit, empty_speech_feedback


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
        self.assertIn("empty_speech_feedback", src)
        self.assertIn("UNRECOGNIZED", src)
        body = src[src.index("def _commit_raw") : src.index("def _clear_unrecognized")]
        self.assertIn("too_sparse_for_duration", body)


class EmptySpeechFeedbackTests(unittest.TestCase):
    def test_silence_stays_quiet(self):
        self.assertEqual(empty_speech_feedback(speech_seconds=0.2, raw="", polished=""), "")

    def test_speech_without_text_is_reported(self):
        self.assertEqual(
            empty_speech_feedback(speech_seconds=0.8, raw="", polished=""),
            UNRECOGNIZED,
        )
        self.assertEqual(UNRECOGNIZED, "не разобрал")

    def test_text_is_not_an_error(self):
        self.assertEqual(
            empty_speech_feedback(speech_seconds=1.0, raw="привет", polished="Привет."),
            "",
        )
