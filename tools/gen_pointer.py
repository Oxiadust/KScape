"""Generates the skin's mouse pointer (skin.kscape/media/pointer.png): an arrow cursor, white with
a dark outline and a soft shadow, its tip at the image's top-left corner (Kodi draws the pointer
image with its top-left at the mouse position). Needs Pillow.

Usage: python3 tools/gen_pointer.py
"""
import os

from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.join(os.path.dirname(__file__), '..')
OUT = os.path.join(ROOT, 'skin.kscape', 'media', 'pointer.png')

SIZE = 96          # the texture (Pointer.xml draws it at 40 x 40 skin pixels)
SS = 4             # supersampling for smooth edges

# The arrow, in a 24-unit box, tip at (1, 1): the usual desktop cursor shape.
ARROW = [(1, 1), (1, 18.5), (5.3, 14.6), (8.2, 21.4), (11.0, 20.2), (8.2, 13.6), (14.0, 13.6)]


def shape(scale, dx=0.0, dy=0.0):
    return [((x + dx) * scale, (y + dy) * scale) for x, y in ARROW]


def main():
    big = SIZE * SS
    unit = big / 24.0
    img = Image.new('RGBA', (big, big), (0, 0, 0, 0))

    shadow = Image.new('RGBA', (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).polygon(shape(unit, 0.7, 1.0), fill=(0, 0, 0, 150))
    shadow = shadow.filter(ImageFilter.GaussianBlur(unit * 0.9))
    img.alpha_composite(shadow)

    d = ImageDraw.Draw(img)
    # Dark outline: the arrow's edge stroked, then the white inside laid over its inner half.
    pts = shape(unit)
    d.polygon(pts, fill=(18, 18, 22, 255))
    d.line(pts + [pts[0]], fill=(18, 18, 22, 255), width=int(unit * 1.15), joint='curve')
    inner = Image.new('L', (big, big), 0)
    ImageDraw.Draw(inner).polygon(shape(unit), fill=255)
    inner = inner.filter(ImageFilter.MinFilter(int(unit * 1.1) | 1))
    img.paste((255, 255, 255, 255), mask=inner)

    img = img.resize((SIZE, SIZE), Image.LANCZOS)
    img.save(OUT)
    print('wrote', os.path.normpath(OUT))


if __name__ == '__main__':
    main()
