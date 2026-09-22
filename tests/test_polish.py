import unittest

from yo.polish import polish_ru


class PolishRuTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(polish_ru("", finalize=True), "")
        self.assertEqual(polish_ru("   "), "")

    def test_keeps_spoken_thanks_and_please(self):
        self.assertEqual(polish_ru("спасибо", finalize=True), "Спасибо.")
        self.assertEqual(polish_ru("пожалуйста", finalize=True), "Пожалуйста.")

    def test_statement_gets_capital_and_period(self):
        self.assertEqual(
            polish_ru("я отправил письмо", finalize=True),
            "Я отправил письмо.",
        )

    def test_short_question(self):
        self.assertEqual(polish_ru("как дела", finalize=True), "Как дела?")
        self.assertEqual(polish_ru("что ты сказал", finalize=True), "Что ты сказал?")
        self.assertEqual(polish_ru("где находится офис", finalize=True), "Где находится офис?")

    def test_li_particle_is_question(self):
        self.assertEqual(
            polish_ru("можем ли мы начать", finalize=True),
            "Можем ли мы начать?",
        )

    def test_keeps_existing_punctuation(self):
        self.assertEqual(polish_ru("Привет, мир.", finalize=True), "Привет, мир.")
        self.assertEqual(polish_ru("Как дела?", finalize=True), "Как дела?")

    def test_collapses_spaces_and_fixes_comma(self):
        self.assertEqual(
            polish_ru("привет  ,   мир", finalize=True),
            "Привет, мир.",
        )

    def test_does_not_force_question_on_long_kak(self):
        text = polish_ru(
            "как только я пришёл домой я сразу сел работать над проектом",
            finalize=True,
        )
        self.assertTrue(text.startswith("Как только"))
        self.assertTrue(text.endswith("."))
        self.assertFalse(text.endswith("?"))

    def test_partial_does_not_add_terminal_punct(self):
        self.assertEqual(polish_ru("я отправил письмо", finalize=False), "Я отправил письмо")

    def test_nepravilnye_okonchaniya_normalized(self):
        self.assertEqual(
            polish_ru("неправильный окончания у слов", finalize=True),
            "Неправильные окончания у слов.",
        )
        self.assertEqual(
            polish_ru("неправильное окончание у слов", finalize=True),
            "Неправильные окончания у слов.",
        )

    def test_latest_four_dump(self):
        text = polish_ru(
            "стоит у монитора и слушая тихий голос у сорта "
            "окончания включение услуг нельзя проглатывать даже если речь её "
            "через букву ё ее находится выходится у рта волна на полчет",
            finalize=True,
        ).lower()
        self.assertIn("и слушая", text)
        self.assertNotIn("и слушает", text)
        self.assertIn("у сорта", text)
        self.assertIn("у рта", text)
        self.assertIn("включение услуг", text)
        self.assertNotIn("у слов", text)
        self.assertIn("речь её", text)
        self.assertNotIn("речь быстрая", text)
        self.assertNotIn("выходится", text)
        self.assertIn("ползёт", text)
        self.assertNotIn("ё ее", text)

    def test_hotword_leak_and_dups(self):
        text = polish_ru(
            "стоит у шёпотом и слушать тихие и слушать тихий голос и голос "
            "даже если речь сеть находится в заходится у рта",
            finalize=True,
        ).lower()
        self.assertIn("у монитора", text)
        self.assertNotIn("шёпотом", text)
        self.assertIn("речь сеть", text)
        self.assertNotIn("речь быстрая", text)
        self.assertNotIn("заходится", text)
        self.assertNotIn("голос и голос", text)

    def test_pack_dump_lyzhera_and_yo(self):
        text = polish_ru(
            "веселые у лыжера стоит монитора неправильные на окончание у слов "
            "через букву звуку громко четко ёлка, ёж ешь буква йо "
            "ползет садится завтра в да",
            finalize=True,
        ).lower()
        self.assertIn("жираф", text)
        self.assertIn("стоит у монитора", text)
        self.assertIn("неправильные окончания", text)
        self.assertIn("через букву ё", text)
        self.assertIn("буква ё", text)
        self.assertNotIn("ешь", text)
        self.assertIn("ползёт и садится", text)
        self.assertIn("завтра среда", text)

    def test_latest_pack_glues(self):
        text = polish_ru(
            "неправильные окончание у слов нельзя оплатывать "
            "ёхо пишется через букву по ее громко и ёлка-ёшь "
            "волна ползет и садиться завтра в среда",
            finalize=True,
        ).lower()
        self.assertIn("оплатывать", text)
        self.assertNotIn("проглатывать", text)
        self.assertIn("окончания", text)
        self.assertIn("через букву ё", text)
        self.assertIn("ёж", text)
        self.assertIn("садится", text)
        self.assertIn("завтра среда", text)
        self.assertTrue(text.startswith("ёхо") or "ёхо пишется" in text)

    def test_calibration_glues_from_58(self):
        self.assertIn("у слов", polish_ru("нельзя услух проглатывать", finalize=True).lower())
        tora = polish_ru("стоит у тора", finalize=True).lower()
        self.assertIn("у тора", tora)
        self.assertNotIn("монитора", tora)
        tonko = polish_ru("говорю громко и тонко", finalize=True).lower()
        self.assertIn("тонко", tonko)
        self.assertNotIn("чётко", tonko)
        self.assertIn("громко и чётко", polish_ru("говорю громко четко", finalize=True).lower())
        self.assertIn("стоит у монитора", polish_ru("кот стоит монитора", finalize=True).lower())
        self.assertIn("ёж", polish_ru("ёлка, ёш и ещё", finalize=True).lower())
        self.assertIn("садится", polish_ru("ползёт и садиться", finalize=True).lower())
        allowed = polish_ru("это допустимо в начале", finalize=True).lower()
        self.assertIn("допустимо", allowed)
        self.assertNotIn("допустим.", allowed)
        self.assertIn("среда", polish_ru("завтра расцвета", finalize=True).lower())
        self.assertIn("полсекунды", polish_ru("не пол полсекунды", finalize=True).lower())
        self.assertIn("у рта", polish_ru("микрофон находятся сорта", finalize=True).lower())

    def test_yoho_and_fused_bez_ruchnogo(self):
        text = polish_ru("йоха снова слушает безручного стопа", finalize=True)
        self.assertIn("Ёхо", text)
        self.assertIn("без ручного", text.lower())
        heard = polish_ru("стоит и слушай тихий голос", finalize=True).lower()
        self.assertIn("слушай", heard)
        self.assertNotIn("слушает", heard)

    def test_fused_u_slov_is_split(self):
        self.assertEqual(
            polish_ru("неправильная окончание услов", finalize=True),
            "Неправильные окончания у слов.",
        )
        self.assertEqual(
            polish_ru("не неправильная окончание услов", finalize=True),
            "Неправильные окончания у слов.",
        )
        self.assertIn("условно", polish_ru("это условно верно", finalize=True).lower())

    def test_continuation_does_not_capitalize_first_word(self):
        self.assertEqual(
            polish_ru("молоко и масло", continuation=True),
            "молоко и масло",
        )
        self.assertEqual(
            polish_ru("Молоко и масло", continuation=True),
            "молоко и масло",
        )

    def test_drops_whisper_hallucination(self):
        self.assertEqual(polish_ru("Продолжение следует", finalize=True), "")
        self.assertEqual(
            polish_ru("субтитры создавал DimaTorzok", finalize=True),
            "",
        )
        self.assertEqual(polish_ru("ссылка в описании", finalize=True), "")

    def test_keeps_real_sentence_with_spasibo(self):
        text = polish_ru("спасибо за письмо", finalize=True)
        self.assertIn("письмо", text.lower())
        two = polish_ru("спасибо большое", finalize=True)
        self.assertIn("спасибо", two.lower())
        self.assertIn("большое", two.lower())

    def test_hallucination_does_not_eat_real_sentence(self):
        text = polish_ru(
            "я отправил письмо. Продолжение следует",
            finalize=True,
        )
        self.assertIn("отправил", text.lower())
        self.assertNotIn("продолжение", text.lower())

    def test_exact_aah_and_laugh_are_dropped(self):
        self.assertEqual(polish_ru("Аа.", finalize=True), "")
        self.assertEqual(polish_ru("Ха-ха!", finalize=True), "")
        self.assertEqual(polish_ru("Ха-ха-ха.", finalize=True), "")
        self.assertEqual(polish_ru("Аа, ааа.", finalize=True), "")
        self.assertIn("Салют", polish_ru("Салют", finalize=True))
        self.assertIn("Угу", polish_ru("Угу", finalize=True))
        sentence = polish_ru("я сказал а потом ушёл", finalize=True)
        self.assertIn("сказал", sentence.lower())
        mixed = polish_ru("Привет. Ха-ха!", finalize=True)
        self.assertIn("Привет", mixed)
        self.assertNotIn("ха", mixed.lower())

    def test_capitalizes_after_sentence(self):
        self.assertEqual(
            polish_ru("привет. как тебя зовут", finalize=True),
            "Привет. Как тебя зовут?",
        )


if __name__ == "__main__":
    unittest.main()
