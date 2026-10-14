import unittest

from yo.cassette import (
    BUSY,
    EQ_BARS,
    REC,
    STOPPED,
    WAIT,
    CassetteAnim,
    Equalizer,
    mode_for,
)


def _run(anim: CassetteAnim, mode: str, loud: float, seconds: float) -> None:
    for _ in range(int(seconds * 30)):
        anim.update(1 / 30, mode, loud)


class CassetteTests(unittest.TestCase):
    def test_reels_spin_faster_with_voice(self):
        quiet, loud = CassetteAnim(), CassetteAnim()
        _run(quiet, REC, 0.0, 1.0)
        _run(loud, REC, 1.0, 1.0)
        self.assertGreater(quiet.reel_speed, 0.3)
        self.assertGreater(loud.reel_speed, quiet.reel_speed * 3)

    def test_stopped_cassette_sleeps(self):
        anim = CassetteAnim()
        _run(anim, STOPPED, 1.0, 1.0)
        self.assertLess(abs(anim.reel_speed), 0.05)
        self.assertGreater(anim.eyelid, 0.9)
        self.assertFalse(anim.rec_lit())

    def test_tape_side_ends_with_rewind_and_loops(self):
        anim = CassetteAnim()
        anim.tape = 0.999
        _run(anim, REC, 0.5, 0.5)
        self.assertTrue(anim.rewinding)
        self.assertLess(anim.reel_speed, 0)
        _run(anim, REC, 0.0, 3.0)
        self.assertFalse(anim.rewinding)
        self.assertGreater(anim.reel_speed, 0)

    def test_notes_fly_only_while_speaking(self):
        anim = CassetteAnim()
        _run(anim, REC, 0.9, 1.5)
        self.assertTrue(anim.notes)
        _run(anim, WAIT, 0.0, 2.5)
        self.assertFalse(anim.notes)

    def test_shapes_stay_inside_overlay_and_avoid_chroma(self):
        anim = CassetteAnim()
        for mode, loud in ((REC, 1.0), (REC, 0.0), (BUSY, 0.0), (STOPPED, 0.0)):
            _run(anim, mode, loud, 0.7)
            for shape in anim.shapes(100, 4, 118):
                self.assertNotEqual(shape.fill.lower(), "#00ff01")
                xs = shape.points[0::2]
                self.assertGreaterEqual(min(xs), 0)
                self.assertLessEqual(max(xs), 200)

    def test_mode_follows_overlay_state(self):
        self.assertEqual(mode_for(visible_live=True, status="", hint="", mic_missing=False), REC)
        self.assertEqual(mode_for(visible_live=False, status="", hint="", mic_missing=False), WAIT)
        self.assertEqual(mode_for(visible_live=True, status="загрузка перевода", hint="", mic_missing=False), BUSY)
        self.assertEqual(mode_for(visible_live=True, status="", hint="", mic_missing=True), STOPPED)


class EqualizerTests(unittest.TestCase):
    def test_bars_rise_with_voice_and_fall_in_silence(self):
        eq = Equalizer()
        bands = [1.0, 0.8, 0.5, 0.3, 0.2, 0.1, 0.1, 0.05, 0.05, 0.02, 0.02, 0.01]
        for _ in range(10):
            eq.update(1 / 30, 0.9, bands, active=True)
        loud_peak = max(eq.bars)
        self.assertGreater(loud_peak, 0.5)
        # Середина (низкие частоты голоса) выше краёв.
        self.assertGreater(eq.bars[EQ_BARS // 2], eq.bars[0] * 2)
        for _ in range(60):
            eq.update(1 / 30, 0.0, bands, active=True)
        self.assertLess(max(eq.bars), 0.12)

    def test_tone_changes_shape(self):
        low, high = Equalizer(), Equalizer()
        for _ in range(10):
            low.update(1 / 30, 0.8, [1.0] + [0.05] * 11, active=True)
            high.update(1 / 30, 0.8, [0.05] * 11 + [1.0], active=True)
        self.assertGreater(low.bars[EQ_BARS // 2], high.bars[EQ_BARS // 2])
        self.assertGreater(high.bars[0], low.bars[0])


if __name__ == "__main__":
    unittest.main()
