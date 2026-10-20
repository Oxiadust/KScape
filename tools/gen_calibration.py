"""Generate the screen calibration marks for skin.kscape (1080i/SettingsScreenCalibration.xml).

Usage: python3 tools/gen_calibration.py   (needs Pillow)

White on transparent, tinted by the XML (the theme's highlight colour when focused):
  cal-tl.png / cal-br.png   corner marks for the top-left and bottom-right movers (128 x 128)
  cal-ratio.png             circle for the pixel-ratio resizer (it must look round when right)
  cal-sub.png               subtitle line: a bar with 40 px clear above and below (Kodi's rule)
  cal-reset.png             reset mark (a circular arrow)
"""
import math
import os

from PIL import Image, ImageDraw

MEDIA = os.path.join(os.path.dirname(__file__), '..', 'skin.kscape', 'media')
WHITE = (255, 255, 255, 255)
S = 2                                   # drawn at twice the size, then reduced (smooth edges)


def save(img, size, name):
    img.resize(size, Image.LANCZOS).save(os.path.join(MEDIA, name), optimize=True)


def corner(flip):
    n = 128 * S
    img = Image.new('RGBA', (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    t = 10 * S
    d.rectangle((0, 0, n - 1, t - 1), fill=WHITE)
    d.rectangle((0, 0, t - 1, n - 1), fill=WHITE)
    d.line((t, t, n * 0.6, n * 0.6), fill=WHITE, width=4 * S)
    if flip:
        img = img.transpose(Image.ROTATE_180)
    return img


def ratio():
    n = 500 * S
    img = Image.new('RGBA', (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = 8 * S
    d.ellipse((w, w, n - w, n - w), outline=WHITE, width=w)
    c = n // 2
    d.line((c - 30 * S, c, c + 30 * S, c), fill=WHITE, width=3 * S)
    d.line((c, c - 30 * S, c, c + 30 * S), fill=WHITE, width=3 * S)
    return img


def subtitle():
    img = Image.new('RGBA', (380 * S, 90 * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 40 * S, 380 * S - 1, 50 * S - 1), 4 * S, fill=WHITE)
    return img


def reset():
    n = 100 * S
    img = Image.new('RGBA', (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m, w = 16 * S, 8 * S
    d.arc((m, m, n - m, n - m), start=40, end=330, fill=WHITE, width=w)
    a = math.radians(40)
    r = (n - 2 * m) / 2
    x, y = n / 2 + r * math.cos(a), n / 2 + r * math.sin(a)
    d.polygon([(x - 16 * S, y - 2 * S), (x + 14 * S, y - 8 * S), (x + 2 * S, y + 20 * S)], fill=WHITE)
    return img


def main():
    save(corner(False), (128, 128), 'cal-tl.png')
    save(corner(True), (128, 128), 'cal-br.png')
    save(ratio(), (500, 500), 'cal-ratio.png')
    save(subtitle(), (380, 90), 'cal-sub.png')
    save(reset(), (100, 100), 'cal-reset.png')
    print('wrote calibration marks to', os.path.abspath(MEDIA))


if __name__ == '__main__':
    main()
