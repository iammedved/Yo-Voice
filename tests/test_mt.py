import unittest

from yo.mt import english_from_russian_asr, split_mt_chunks


class SplitMtChunksTests(unittest.TestCase):
    def test_short_text_stays_one_chunk(self):
        self.assertEqual(split_mt_chunks("Привет, мир."), ["Привет, мир."])

    def test_empty_is_no_chunks(self):
        self.assertEqual(split_mt_chunks(""), [])
        self.assertEqual(split_mt_chunks("   "), [])

    def test_long_text_splits_on_sentences(self):
        first = "А" * 200 + "."
        second = "Б" * 200 + "."
        chunks = split_mt_chunks(f"{first} {second}", max_chars=250)
        self.assertEqual(chunks, [first, second])

    def test_oversized_sentence_is_hard_split(self):
        blob = "а" * 900
        chunks = split_mt_chunks(blob, max_chars=400)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) <= 400 for c in chunks))
        self.assertEqual("".join(chunks), blob)


class EnglishFromRussianAsrTests(unittest.TestCase):
    def test_polishes_russian_then_translates(self):
        seen = []

        def fake_mt(text: str) -> str:
            seen.append(text)
            return "I sent the letter"

        out = english_from_russian_asr("я отправил письмо", fake_mt)
        self.assertEqual(out, "I sent the letter")
        self.assertEqual(len(seen), 1)
        self.assertTrue(seen[0].startswith("Я отправил письмо"))

    def test_hallucination_does_not_call_translator(self):
        calls = []
        out = english_from_russian_asr(
            "продолжение следует",
            lambda text: calls.append(text) or "nope",
        )
        self.assertEqual(out, "")
        self.assertEqual(calls, [])

    def test_empty_translator_result_stays_empty(self):
        self.assertEqual(english_from_russian_asr("проверка связи", lambda _text: "  "), "")
