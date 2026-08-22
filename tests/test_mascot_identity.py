import unittest
from pathlib import Path

from PIL import Image

from yo.paths import orb_path, project_root

PAD = 8


def _open_logo(path: Path) -> Image.Image:
    im = Image.open(path)
    return im.convert("RGBA") if im.mode != "RGBA" else im


def _opaque_bbox(im: Image.Image):
    bbox = im.getbbox()
    if bbox is None:
        raise AssertionError("logo has no opaque pixels")
    return bbox


def _band(im: Image.Image, bbox, y0_frac: float, y1_frac: float):
    height = bbox[3] - bbox[1]
    y0 = bbox[1] + int(height * y0_frac)
    y1 = bbox[1] + int(height * y1_frac)
    dark = grey = pink = 0
    for y in range(y0, y1):
        for x in range(bbox[0], bbox[2]):
            r, g, b, a = im.getpixel((x, y))
            if a < 128:
                continue
            if r < 55 and g < 55 and b < 55:
                dark += 1
            elif r > 180 and g < 140 and (r - g) > 70 and b > 100:
                pink += 1
            elif abs(r - g) < 30 and abs(g - b) < 30 and 70 < r < 200:
                grey += 1
    return dark, grey, pink


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

    def test_logo_cat_fits_inside_canvas(self):
        path = orb_path()
        im = _open_logo(path)
        w, h = im.size
        left, top, right, bottom = _opaque_bbox(im)
        self.assertGreaterEqual(left, PAD)
        self.assertGreaterEqual(top, PAD)
        self.assertLessEqual(right, w - PAD)
        self.assertLessEqual(bottom, h - PAD)

    def test_logo_hind_paws_are_furry_not_reversed_black_boots(self):
        path = orb_path()
        im = _open_logo(path)
        dark, grey, _pink = _band(im, _opaque_bbox(im), 0.85, 1.0)
        self.assertGreater(grey, dark)

    def test_logo_belly_has_no_stray_third_paw(self):
        path = orb_path()
        im = _open_logo(path)
        _dark, _grey, pink = _band(im, _opaque_bbox(im), 0.50, 0.70)
        self.assertLess(pink, 8_000)

    def test_logo_has_no_studio_floor_plate(self):
        path = orb_path()
        im = _open_logo(path)
        bbox = _opaque_bbox(im)
        height = bbox[3] - bbox[1]
        y0 = bbox[1] + int(height * 0.88)
        leftover = 0
        for y in range(y0, bbox[3]):
            for x in range(bbox[0], bbox[2]):
                r, g, b, a = im.getpixel((x, y))
                if a < 128:
                    continue
                if g > 50 and g > r + 20 and g > b + 20:
                    leftover += 1
                elif r > 40 and r < 120 and g < 40 and b > 12 and b < 70 and r > g + 20:
                    leftover += 1
        self.assertLess(leftover, 400)

    def test_logo_corners_are_transparent(self):
        path = orb_path()
        im = _open_logo(path)
        w, h = im.size
        for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
            self.assertEqual(im.getpixel((x, y))[3], 0)

    def test_desktop_icon_has_the_same_complete_cat(self):
        logo = project_root() / "assets" / "logo.png"
        mascot = project_root() / "assets" / "mascot.png"
        self.assertTrue(mascot.exists())
        im = _open_logo(mascot)
        w, h = im.size
        bbox = _opaque_bbox(im)
        self.assertGreaterEqual(bbox[0], PAD)
        self.assertLessEqual(bbox[2], w - PAD)
        self.assertLessEqual(bbox[3], h - PAD)
        dark, grey, _pink = _band(im, bbox, 0.85, 1.0)
        self.assertGreater(grey, dark)
        self.assertEqual(logo.read_bytes(), mascot.read_bytes())
