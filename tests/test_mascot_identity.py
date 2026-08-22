import unittest
from pathlib import Path

from PIL import Image

from yo.paths import orb_path


class MascotIdentityTests(unittest.TestCase):
    def test_overlay_logo_is_grey_white_cat_png(self):
        path = orb_path()
        self.assertEqual(path.name, "logo.png")
        self.assertTrue(path.exists())
        im = Image.open(path)
        self.assertEqual(im.mode, "RGBA")
        extrema = im.getextrema()
        self.assertEqual(extrema[3][0], 0)
        n = dark = 0
        rs = gs = bs = 0
        for r, g, b, a in im.getdata():
            if a < 200:
                continue
            n += 1
            rs += r
            gs += g
            bs += b
            if r < 50 and g < 50 and b < 50:
                dark += 1
        self.assertGreater(n, 10_000)
        mean_r, mean_g, mean_b = rs / n, gs / n, bs / n
        self.assertLess(mean_r - mean_b, 40)
        self.assertLess(abs(mean_g - mean_b), 25)
        self.assertGreater(dark, 1_000)
        self.assertGreater(Path(path).stat().st_size, 10_000)
