"""Unit tests for scenes and Demo Scripts (scenemodel.py). Run: python3 -m unittest discover -s tests"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from resources.lib import scenemodel as SM  # noqa: E402


class TimesTest(unittest.TestCase):
    def test_clock(self):
        self.assertEqual(SM.clock(6270), '1:44:30')
        self.assertEqual(SM.clock(125.4), '2:05')
        self.assertEqual(SM.clock(-3), '0:00')

    def test_parse_clock(self):
        self.assertEqual(SM.parse_clock('1:44:30'), 6270)
        self.assertEqual(SM.parse_clock('2:05'), 125)
        self.assertEqual(SM.parse_clock(' 95.5 '), 95.5)
        self.assertEqual(SM.parse_clock('0:00:01.25'), 1.25)
        for bad in ('', 'soon', '1:75', '1:02:99', '1::02'):
            self.assertIsNone(SM.parse_clock(bad), bad)

    def test_check_times(self):
        self.assertIsNone(SM.check_times(10, 20, runtime=100))
        self.assertEqual(SM.check_times(20, 10), 'order')
        self.assertEqual(SM.check_times(20, 20), 'order')
        self.assertEqual(SM.check_times(20, 20.5), 'short')
        self.assertEqual(SM.check_times(-1, 20), 'negative')
        self.assertEqual(SM.check_times(10, 200, runtime=100), 'runtime')
        self.assertIsNone(SM.check_times(10, 200, runtime=0))      # runtime unknown


class NextTest(unittest.TestCase):
    def test_next_index(self):
        self.assertEqual(SM.next_index(0, 3, 'once'), 1)
        self.assertIsNone(SM.next_index(2, 3, 'once'))
        self.assertEqual(SM.next_index(2, 3, 'script'), 0)
        self.assertEqual(SM.next_index(1, 3, 'scene', looping_scene=True), 1)
        self.assertEqual(SM.next_index(1, 3, 'scene', looping_scene=False), 2)
        self.assertIsNone(SM.next_index(0, 0, 'script'))


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, 'x', 'scenes.json')
        self.st = SM.Store(self.path)
        self.a = self.st.add_scene('movie', 125, '/m/heat.mkv', 'Heat', 'Lobby Shootout', 6270, 6460)
        self.b = self.st.add_scene('movie', 7, '/m/dune.mkv', 'Dune', 'Sandworm', 3600, 3780.5)
        self.c = self.st.add_scene('episode', 40, '/tv/s01e01.mkv', 'Show 1x01', 'Cold open', 0, 95)

    def tearDown(self):
        self.dir.cleanup()

    def test_scenes_persist_with_duration(self):
        again = SM.Store(self.path)
        s = again.scene(self.a)
        self.assertEqual((s['media'], s['dbid'], s['file'], s['name']), ('movie', 125, '/m/heat.mkv', 'Lobby Shootout'))
        self.assertEqual(SM.duration(s), 190)
        self.assertTrue(s['created'])

    def test_invalid_scene_is_refused(self):
        with self.assertRaises(ValueError):
            self.st.add_scene('movie', 1, '/m/x.mkv', 'X', 'Backwards', 50, 10)
        with self.assertRaises(ValueError):
            self.st.add_scene('song', 1, '/m/x.flac', 'X', 'Music', 0, 10)
        with self.assertRaises(ValueError):
            self.st.update_scene(self.a, end=100)
        self.assertEqual(self.st.scene(self.a)['end'], 6460)

    def test_by_media_groups_by_title_then_start(self):
        self.st.add_scene('movie', 125, '/m/heat.mkv', 'Heat', 'Bank', 5000, 5100)
        names = [s['name'] for s in SM.by_media(self.st.scenes, 'movie')]
        self.assertEqual(names, ['Sandworm', 'Bank', 'Lobby Shootout'])
        self.assertEqual([s['name'] for s in SM.by_media(self.st.scenes, 'episode')], ['Cold open'])
        self.assertEqual([s['name'] for s in self.st.scenes_of('movie', 125)], ['Bank', 'Lobby Shootout'])

    def test_scripts_refer_to_scenes_by_id(self):
        d = self.st.add_script('Atmos Showcase', [self.a, self.b])
        self.st.update_scene(self.a, name='Lobby')                 # renaming shows everywhere
        scenes = SM.script_scenes(self.st.script(d), self.st.by_id())
        self.assertEqual([s['name'] for s in scenes], ['Lobby', 'Sandworm'])
        self.assertEqual(SM.total_duration(self.st.script(d), self.st.by_id()), 190 + 180.5)

    def test_delete_scene_leaves_scripts_and_script_delete_leaves_scenes(self):
        d = self.st.add_script('Show', [self.a, self.b, self.a])
        self.st.update_script(d, loop='scene', loop_scene=self.a)
        self.st.delete_scene(self.a)
        self.assertEqual(self.st.script(d)['scenes'], [self.b])
        self.assertEqual(self.st.script(d)['loop_scene'], '')
        self.st.delete_script(d)
        self.assertIsNotNone(self.st.scene(self.b))

    def test_reorder_remove_duplicate(self):
        d = self.st.add_script('Show', [self.a, self.b, self.c])
        self.assertEqual(self.st.move_in_script(d, 2, -1), 1)
        self.assertEqual(self.st.script(d)['scenes'], [self.a, self.c, self.b])
        self.assertEqual(self.st.move_in_script(d, 0, -1), 0)       # already first
        copy = self.st.duplicate_script(d, 'Copy of Show')
        self.st.remove_from_script(d, 0)
        self.assertEqual(self.st.script(d)['scenes'], [self.c, self.b])
        self.assertEqual(self.st.script(copy)['scenes'], [self.a, self.c, self.b])   # copy untouched
        self.assertIsNotNone(self.st.scene(self.a))                                   # scene kept
        self.assertEqual(len(self.st.scripts_with(self.a)), 1)

    def test_options_are_checked(self):
        d = self.st.add_script('Show')
        self.st.update_script(d, transition='fade', transition_s=99, loop='script')
        self.assertEqual((self.st.script(d)['transition'], self.st.script(d)['transition_s']), ('fade', 10.0))
        with self.assertRaises(ValueError):
            self.st.update_script(d, transition='wipe')
        with self.assertRaises(ValueError):
            self.st.update_script(d, loop='forever')

    def test_ids_never_repeat_after_reload(self):
        d = self.st.add_script('Show')
        again = SM.Store(self.path)
        self.assertNotIn(again.add_script('Next'), {self.a, self.b, self.c, d})

    def test_poll_sees_other_writers(self):
        other = SM.Store(self.path)
        other.add_script('Elsewhere')
        self.assertTrue(self.st.poll())
        self.assertEqual([d['name'] for d in self.st.scripts], ['Elsewhere'])


if __name__ == '__main__':
    unittest.main()
