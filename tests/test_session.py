import unittest

from yo.session import DictationSession


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
        text = self.session.commit_utterance("неправильные неправильное окончания")
        self.assertIn("Неправильные окончания", text)


if __name__ == "__main__":
    unittest.main()
