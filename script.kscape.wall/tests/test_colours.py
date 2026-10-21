"""Colour themes: the add-on's choices match the skin's colour files. Run: python3 -m unittest discover -s tests"""
import os
import sys
import types
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'tools'))
for name in ('xbmc', 'xbmcaddon', 'xbmcgui'):          # colours.py only needs them inside Kodi
    sys.modules.setdefault(name, types.ModuleType(name))
sys.modules['xbmcaddon'].Addon = lambda *a, **k: None

import gen_colors  # noqa: E402
from resources.lib import colours  # noqa: E402

COLORS = os.path.join(HERE, '..', '..', 'skin.kscape', 'colors')


class ColoursTest(unittest.TestCase):
    def test_choices_match_the_generator(self):
        self.assertEqual(list(colours.MAINS), list(gen_colors.MAINS))
        self.assertEqual(list(colours.HIGHLIGHTS), list(gen_colors.HIGHLIGHTS))
        self.assertEqual(colours.DEFAULT, gen_colors.DEFAULT)

    def test_every_pair_has_a_file_with_every_colour(self):
        names = set(gen_colors.MAIN) | set(gen_colors.FIXED) | {'kscape_amber'}
        for m in colours.MAINS:
            for h in colours.HIGHLIGHTS:
                value = colours.value_of(m, h)
                path = os.path.join(COLORS, 'defaults.xml' if value == 'SKINDEFAULT' else value + '.xml')
                with open(path) as f:
                    text = f.read()
                for n in names:
                    self.assertIn(f'name="{n}"', text, path)
                self.assertEqual(colours.parse(value), (m, h))

    def test_unknown_values_are_the_default(self):
        self.assertEqual(colours.parse('SKINDEFAULT'), ('Graphite', 'Amber'))
        self.assertEqual(colours.parse('Neon - Pink'), ('Graphite', 'Amber'))

    def test_retint_keeps_lightness_and_alpha(self):
        out = gen_colors.retint('EE1F5BD3', gen_colors.MAINS['Crimson'])
        self.assertTrue(out.startswith('EE'))
        self.assertAlmostEqual(gen_colors.hls(out[2:])[1], gen_colors.hls('1F5BD3')[1], places=2)


if __name__ == '__main__':
    unittest.main()
