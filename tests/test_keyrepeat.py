import unittest

from yo.keyrepeat import X11RepeatFilter, win_key_action


class X11RepeatFilterTests(unittest.TestCase):
    def test_tap_fires_once(self):
        f = X11RepeatFilter()
        self.assertTrue(f.press(49, 1000))
        f.release(49, 1080)
        self.assertTrue(f.press(49, 1500))

    def test_held_key_with_release_press_pairs_fires_once(self):
        f = X11RepeatFilter()
        fired = [f.press(49, 1000)]
        t = 1500
        for _ in range(60):  # 3 s of X11 auto-repeat
            f.release(49, t)
            fired.append(f.press(49, t))
            t += 40
        f.release(49, t)
        self.assertEqual(sum(fired), 1)
        self.assertTrue(f.press(49, t + 300))

    def test_detectable_repeat_fires_once(self):
        f = X11RepeatFilter()
        fired = [f.press(49, t) for t in range(1000, 4000, 33)]
        self.assertEqual(sum(fired), 1)

    def test_lost_release_does_not_lock_the_key(self):
        f = X11RepeatFilter()
        self.assertTrue(f.press(49, 1000))
        self.assertTrue(f.press(49, 5000))

    def test_server_clock_wrap(self):
        f = X11RepeatFilter()
        self.assertTrue(f.press(49, 0xFFFFFFF0))
        self.assertFalse(f.press(49, 0x10))


class WinKeyActionTests(unittest.TestCase):
    def test_plain_press_fires_and_release_is_eaten(self):
        self.assertEqual(win_key_action(down=True, up=False, bound=True, held=False, mods_down=False), "fire")
        self.assertEqual(win_key_action(down=False, up=True, bound=True, held=True, mods_down=False), "eat")

    def test_shift_press_types_the_letter(self):
        self.assertEqual(win_key_action(down=True, up=False, bound=True, held=False, mods_down=True), "pass")
        self.assertEqual(win_key_action(down=False, up=True, bound=True, held=False, mods_down=True), "pass")

    def test_release_with_shift_down_still_clears_the_held_mark(self):
        # ё down, Shift down, ё up: the release must be eaten and unmark ё,
        # or the next real press is taken for auto-repeat and lost.
        self.assertEqual(win_key_action(down=False, up=True, bound=True, held=True, mods_down=True), "eat")

    def test_auto_repeat_is_eaten(self):
        self.assertEqual(win_key_action(down=True, up=False, bound=True, held=True, mods_down=False), "eat")

    def test_other_keys_pass(self):
        self.assertEqual(win_key_action(down=True, up=False, bound=False, held=False, mods_down=False), "pass")


if __name__ == "__main__":
    unittest.main()
