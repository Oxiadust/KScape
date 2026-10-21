"""Unit tests for the wall's camera and frame glides (window.Glide). Run: python3 -m unittest discover -s tests"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from resources.lib.wallmodel import ease_out_back, ease_out_cubic  # noqa: E402

# window.py needs Kodi's modules; import it against mocks, then put sys.modules back as it was.
with mock.patch.dict(sys.modules, {n: mock.MagicMock() for n in ('xbmc', 'xbmcaddon', 'xbmcgui', 'xbmcvfs')}):
    from resources.lib.window import Glide, ease_out_sine  # noqa: E402


def parse(anim):
    kind, text = anim
    fields = dict(f.split('=', 1) for f in text.split(' '))
    return kind, fields


class GlideTest(unittest.TestCase):
    def setUp(self):
        self.control = mock.MagicMock()
        self.frame = Glide(self.control, 'kscape.motion.1', 0)
        self.cam = Glide(mock.MagicMock(), 'kscape.motion.1', 1)

    def test_first_placement_is_static(self):
        anims = self.frame.plan((100, 50), now=0.0, ms=420, tween='back', ease=ease_out_back)
        self.assertEqual(len(anims), 1)
        _, f = parse(anims[0])
        self.assertEqual((f['start'], f['end'], f['time']), ('100,50', '100,50', '0'))
        self.assertEqual(f['condition'], 'String.StartsWith(Window(Home).Property(kscape.motion.1),1.)')

    def test_glide_holds_where_drawn_then_moves_on_the_next_token(self):
        self.frame.plan((0, 0), now=0.0)
        hold, move = self.frame.plan((200, 0), now=10.0, ms=400, tween='cubic', ease=ease_out_cubic)
        _, h = parse(hold)
        _, m = parse(move)
        self.assertEqual((h['start'], h['end'], h['time']), ('0,0', '0,0', '0'))
        self.assertTrue(h['condition'].endswith(',1.)'))           # the token shown now
        self.assertEqual((m['start'], m['end'], m['time'], m['tween']), ('0,0', '200,0', '400', 'cubic'))
        self.assertTrue(m['condition'].endswith(',2.)'))           # the token the commit writes

    def test_interrupted_glide_restarts_from_its_visual_position(self):
        self.frame.plan((0, 0), now=0.0)
        self.frame.plan((200, 0), now=10.0, ms=400, ease=ease_out_cubic)
        halfway = round(200 * ease_out_cubic(0.5))
        hold, move = self.frame.plan((400, 0), now=10.2, ms=400, ease=ease_out_cubic)
        self.assertEqual(parse(hold)[1]['start'], f'{halfway},0')
        self.assertEqual(parse(move)[1]['start'], f'{halfway},0')
        self.assertEqual(parse(move)[1]['end'], '400,0')

    def test_camera_uses_the_second_token(self):
        self.cam.plan((0, 0), now=0.0)
        _, move = self.cam.plan((-210, 0), now=1.0, start=(-50, 0), ms=600, ease=ease_out_cubic)
        f = parse(move)[1]
        self.assertEqual(f['start'], '-50,0')
        self.assertEqual(f['condition'], 'String.EndsWith(Window(Home).Property(kscape.motion.1),.2)')

    def test_settle_after_the_glide_only(self):
        self.frame.plan((0, 0), now=0.0)
        self.frame.plan((200, 0), now=10.0, ms=400, ease=ease_out_cubic)
        self.frame.settle(10.2)
        self.control.setAnimations.assert_not_called()
        self.frame.settle(10.5)
        (anims,), _ = self.control.setAnimations.call_args
        f = parse(anims[0])[1]
        self.assertEqual((f['start'], f['end'], f['time']), ('200,0', '200,0', '0'))
        self.assertTrue(f['condition'].endswith(',2.)'))           # same token: no visible change
        self.frame.settle(11.0)
        self.assertEqual(self.control.setAnimations.call_count, 1)

    def test_sine_matches_endpoints(self):
        self.assertEqual(ease_out_sine(0), 0)
        self.assertAlmostEqual(ease_out_sine(1), 1)
        self.assertGreater(ease_out_sine(0.5), 0.5)


if __name__ == '__main__':
    unittest.main()
