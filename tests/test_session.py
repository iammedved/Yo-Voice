import unittest

from yo.session import DictationSession, too_sparse_for_duration


class DictationSessionTests(unittest.TestCase):
    def setUp(self):
        self.injected = []
        self.session = DictationSession(inject=self.injected.append)

    def test_toggle_listening(self):
        self.assertFalse(self.session.listening)
        self.session.start()
        self.assertTrue(self.session.listening)
        self.session.stop()
        self.assertFalse(self.session.listening)

    def test_first_utterance_has_no_leading_space(self):
        self.session.start()
        text = self.session.commit_utterance("я отправил письмо")
        self.assertEqual(text, "Я отправил письмо.")
        self.assertEqual(self.injected, ["Я отправил письмо."])

    def test_next_utterance_is_separated_by_space(self):
        self.session.start()
        self.session.commit_utterance("привет")
        self.session.commit_utterance("как дела")
        self.assertEqual(self.injected, ["Привет.", " Как дела?"])

    def test_empty_and_hallucination_are_not_injected(self):
        self.session.start()
        self.assertEqual(self.session.commit_utterance("   "), "")
        self.assertEqual(self.session.commit_utterance("Продолжение следует"), "")
        self.assertEqual(self.injected, [])

    def test_stop_does_not_listen(self):
        self.session.start()
        self.session.stop()
        self.assertEqual(self.session.commit_utterance("привет"), "")
        self.assertEqual(self.injected, [])

    def test_consecutive_variant_is_deduped(self):
        self.session.start()
        text = self.session.commit_utterance("он сказал сказала это вслух")
        self.assertIn("сказал", text.lower())
        self.assertNotIn("сказала", text.lower())

    def test_exact_repeat_is_kept(self):
        self.session.start()
        text = self.session.commit_utterance("Салют! Салют! Салют!")
        self.assertEqual(text.lower().count("салют"), 3)

    def test_long_clip_with_tiny_text_is_sparse(self):
        self.assertTrue(too_sparse_for_duration("Салют! Угу.", 59.8))
        self.assertTrue(too_sparse_for_duration("Аа, ааа.", 21.9))
        self.assertFalse(too_sparse_for_duration("Салют", 1.0))
        self.assertFalse(too_sparse_for_duration("Салют!", 4.4))
        self.assertFalse(
            too_sparse_for_duration("я отправил длинное письмо коллеге сегодня утром", 20.0)
        )


if __name__ == "__main__":
    unittest.main()
