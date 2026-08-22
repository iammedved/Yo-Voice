import unittest
from pathlib import Path

from PIL import Image

from yo.paths import orb_path, project_root

PAD = 8
PAW_DARK = 2_000
PAW_PINK = 200
PAW_SPAN = 200


def _open_logo(path: Path) -> Image.Image:
    im = Image.open(path)
    return im.convert("RGBA") if im.mode != "RGBA" else im


def _opaque_bbox(im: Image.Image):
    bbox = im.getbbox()
    if bbox is None:
        raise AssertionError("logo has no opaque pixels")
    return bbox


def _hind_paw_band(im: Image.Image, bbox):
    y1 = bbox[3]
    y0 = max(bbox[1], y1 - 48)
    dark = pink = 0
    min_x = im.size[0]
    max_x = 0
    for y in range(y0, y1):
        for x in range(bbox[0], bbox[2]):
            r, g, b, a = im.getpixel((x, y))
            if a < 128:
                continue
            if r < 55 and g < 55 and b < 55:
                dark += 1
                min_x = min(min_x, x)
                max_x = max(max_x, x)
            elif r > 160 and 70 <= g < 190 and b > 90:
                pink += 1
    span = 0 if dark == 0 else max_x - min_x
    return dark, pink, span


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

    def test_logo_hind_paws_are_complete(self):
        path = orb_path()
        im = _open_logo(path)
        dark, pink, span = _hind_paw_band(im, _opaque_bbox(im))
        self.assertGreaterEqual(dark, PAW_DARK)
        self.assertGreaterEqual(pink, PAW_PINK)
        self.assertGreaterEqual(span, PAW_SPAN)

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
        dark, pink, span = _hind_paw_band(im, bbox)
        self.assertGreaterEqual(dark, PAW_DARK)
        self.assertGreaterEqual(pink, PAW_PINK)
        self.assertGreaterEqual(span, PAW_SPAN)
        self.assertEqual(logo.read_bytes(), mascot.read_bytes())
