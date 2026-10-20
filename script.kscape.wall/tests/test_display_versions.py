"""Unit tests for movie versions (versions.py) and display & aspect ratio (display.py, geometry.adapt).
Run: python3 -m unittest discover -s tests"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from resources.lib import display as D  # noqa: E402
from resources.lib import geometry as G  # noqa: E402
from resources.lib import streaminfo as SI  # noqa: E402
from resources.lib import versions as V  # noqa: E402
from resources.lib.wallmodel import Wall, camera_target  # noqa: E402

UHD = V.Version(1, '/m/Avatar 2160p.mkv', 'Standard Edition', '4K', 'hdr10', ('atmos',), resume=0.0, default=True)
FHD = V.Version(1, '/m/Avatar 1080p.mkv', 'Standard Edition', '1080p', 'sdr', ('dts',))
B3D = V.Version(1, '/m/Avatar 3D.mkv', '3D', '1080p', 'sdr', ('dtshdma',), stereo=True)
CUT = V.Version(1, '/m/Avatar Extended.mkv', 'Extended Edition', '1080p', 'sdr', (), resume=1200.0)


class VersionsTest(unittest.TestCase):
    def test_formats_cover_every_version(self):
        self.assertEqual(V.formats((FHD, B3D, UHD)), ('4K', '1080p', '3D'))
        self.assertEqual(V.formats((), '720p', False, '/m/x.mkv'), ('720p',))
        self.assertEqual(V.formats((), 'SD', False, '/m/DVD/VIDEO_TS/VIDEO_TS.IFO'), ('DVD',))
        self.assertEqual(V.formats((), '', False, '/m/x.iso'), ())                 # nothing known, nothing shown

    def test_play_order_prefers_resolution_and_never_3d_by_default(self):
        self.assertEqual(V.choose((B3D, FHD, UHD)), UHD)
        self.assertEqual(V.choose((B3D, FHD, UHD), '1080p'), FHD)
        self.assertEqual(V.choose((B3D, FHD), '4K'), FHD)                          # 2D before 3D
        self.assertEqual(V.choose((B3D, FHD), '4K', prefer_3d=True), B3D)
        self.assertEqual(V.choose((B3D,)), B3D)                                    # the only one
        self.assertEqual(V.choose((FHD, UHD), 'default'), UHD)                     # Kodi's default

    def test_resume_picks_the_version_with_a_resume_point(self):
        self.assertEqual(V.choose((UHD, CUT), resume=True), CUT)
        self.assertEqual(V.choose((UHD, FHD), resume=True), UHD)

    def test_labels(self):
        self.assertEqual(V.label(UHD), 'Standard Edition — 4K Ultra HD · 2160p · HDR10 · Dolby Atmos')
        self.assertEqual(V.label(B3D), '3D — Full HD · 1080p · 3D · SDR · DTS-HD MA')
        same = V.labels((UHD, FHD))
        self.assertTrue(same[0].startswith('Standard Edition (Avatar 2160p.mkv)'))

    def test_cache_round_trip(self):
        self.assertEqual(V.Version.from_cache(UHD.to_cache()), UHD)

    def test_stereo_from_stream_details(self):
        self.assertTrue(SI.stereo({'video': [{'stereomode': 'left_right'}]}))
        self.assertFalse(SI.stereo({'video': [{'stereomode': ''}]}))
        self.assertFalse(SI.stereo({}))


class DisplayTest(unittest.TestCase):
    def test_sixteen_nine_screens_are_untouched(self):
        for w, h in ((1920, 1080), (3840, 2160)):
            st = D.stage(w, h)
            self.assertEqual((round(st.sx, 3), st.banded, st.zoom, st.view, st.scale), (1.0, False, 100, (0, 0, 1920, 1080), 1.0))
            self.assertEqual(D.properties(st)['kscape.display.zoom'], '')
            self.assertEqual(D.detected(w, h), '16:9')

    def test_native_ultrawide_widens_without_a_band(self):
        for w, h in ((2560, 1080), (3440, 1440)):
            st = D.stage(w, h)
            self.assertFalse(st.banded)
            self.assertAlmostEqual(st.sx, (w / h) / (16 / 9), 3)
            self.assertEqual(st.zoom, 100)
            self.assertEqual(D.detected(w, h), 'ultrawide')

    def test_manual_cinemascope_on_a_sixteen_nine_signal(self):
        st = D.stage(3840, 2160, '2.39')
        self.assertTrue(st.banded)
        self.assertEqual(st.zoom, 74)                                  # 1.778 / 2.39
        self.assertEqual(st.view, (0, 138, 1920, 803))
        st = D.stage(1920, 1080, '2.35', rows='3', voffset=40)
        self.assertEqual((st.view[1], st.view[3]), (171, 817))         # band moved down 40 px
        self.assertAlmostEqual(st.scale, 817 / (3.35 * 303), 2)
        self.assertEqual(D.properties(st)['kscape.display.dy'], '40')

    def test_offsets_and_safe_area_are_quantised(self):
        st = D.stage(1920, 1080, '16:9', voffset=-37, hoffset=999, safe=5)
        self.assertEqual((st.dx, st.dy, st.zoom), (300, -40, 90))
        self.assertIn(st.zoom, D.ZOOMS)
        self.assertEqual(st.view, (396, 14, 1728, 972))

    def test_manual_ultrawide_on_a_native_ultrawide_screen_is_full_screen(self):
        self.assertFalse(D.stage(2560, 1080, '21:9').banded)

    def test_wall_layout_adapts(self):
        same = G.adapt(G.POSTER, D.stage(1920, 1080))
        self.assertIs(same, G.POSTER)
        wide = G.adapt(G.POSTER, D.stage(2560, 1080))
        self.assertAlmostEqual(wide.cover_w / G.POSTER.cover_w, 1 / 1.333, 2)     # covers keep 2:3 on screen
        self.assertEqual(wide.cover_h, G.POSTER.cover_h)
        self.assertGreater(wide.pool_cols, G.POSTER.pool_cols)
        cols, rows = G.MAX_POOL['poster']
        scope = G.adapt(G.POSTER, D.stage(1920, 1080, '2.40', rows='3'))
        self.assertLessEqual(scope.pool_cols * scope.pool_rows, cols * rows)
        self.assertLess(scope.cover_h, G.POSTER.cover_h)
        self.assertEqual(scope.view[3], 800)

    def test_camera_centres_inside_the_view(self):
        lay = G.adapt(G.POSTER, D.stage(1920, 1080, '2.39'))
        wall = Wall.column_major([type('M', (), {'key': i})() for i in range(200)], layout=lay)
        cam = camera_target(wall, (10, 2))
        x, y = 10 * lay.pitch_x, 2 * lay.pitch_y
        self.assertAlmostEqual(cam[0], x + lay.cover_w / 2 - lay.view[2] / 2, delta=1)


if __name__ == '__main__':
    unittest.main()
