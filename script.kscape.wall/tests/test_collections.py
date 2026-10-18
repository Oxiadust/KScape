"""Unit tests for the collections model. Run: python3 -m unittest discover -s tests"""
import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from resources.lib import collectionmodel as C  # noqa: E402
from resources.lib.media import Album, Show  # noqa: E402
from resources.lib.model import Movie, merge_duplicates  # noqa: E402

NOW = datetime(2026, 10, 18, 12, 0, 0)


def movie(i, title, year=2000, added='', played='', playcount=0, resume=0.0, file=None):
    return Movie(i, title, title.lower(), year, frozenset(), frozenset(), (), 0, frozenset(), f'p{i}', '', 6000,
                 resume, file=file if file is not None else f'/m/{i}.mkv', dateadded=added, lastplayed=played,
                 playcount=playcount)


class BuiltinTest(unittest.TestCase):
    def setUp(self):
        self.movies = [
            movie(1, 'Old', added='2025-01-01 10:00:00'),
            movie(2, 'Fresh', added='2026-10-17 20:00:00'),
            movie(3, 'Week', added='2026-10-11 09:00:00'),
            movie(4, 'Half', added='2026-01-01 00:00:00', played='2026-10-10 19:27:00', resume=1800.0),
            movie(5, 'Done', added='2026-01-01 00:00:00', played='2026-10-12 21:00:00', playcount=1),
            movie(6, 'Rewatch', played='2026-10-15 21:00:00', playcount=2, resume=600.0),
            movie(7, 'Undated'),
            movie(8, 'Half again', played='2026-10-16 08:05:00', resume=60.0),
        ]

    def keys(self, movies):
        return [m.movieid for m in movies]

    def test_new_is_recent_additions_newest_first(self):
        self.assertEqual(self.keys(C.new_movies(self.movies, 30, NOW)), [2, 3])
        self.assertEqual(self.keys(C.new_movies(self.movies, 3, NOW)), [2])
        self.assertEqual(self.keys(C.new_movies(self.movies, 365, NOW)), [2, 3, 5, 4])

    def test_paused_needs_resume_point_and_not_watched(self):
        self.assertEqual(self.keys(C.paused_movies(self.movies)), [8, 4])

    def test_played_is_playcount_most_recent_first(self):
        self.assertEqual(self.keys(C.played_movies(self.movies)), [6, 5])

    def test_builtin_dispatch(self):
        self.assertEqual(self.keys(C.builtin_movies('paused', self.movies)), [8, 4])
        self.assertEqual(self.keys(C.builtin_movies('new', self.movies, 30, NOW)), [2, 3])

    def test_describe(self):
        self.assertEqual(C.describe('paused', self.movies[3], now=NOW), 'Paused on October 10 at 7:27 pm')
        self.assertEqual(C.describe('paused', self.movies[7], now=NOW), 'Paused on October 16 at 8:05 am')
        self.assertEqual(C.describe('new', self.movies[0], now=NOW), 'Added on January 1, 2025')
        self.assertEqual(C.describe('played', self.movies[4], now=NOW), 'Played on October 12')
        self.assertEqual(C.describe('c1', self.movies[0], now=NOW), '2000')
        self.assertEqual(C.describe('new', self.movies[6], now=NOW), '')

    def test_bad_dates_are_ignored(self):
        self.assertIsNone(C.parse_date('garbage'))
        self.assertEqual(C.parse_date('2026-10-01'), datetime(2026, 10, 1))


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, 'sub', 'collections.json')

    def tearDown(self):
        self.dir.cleanup()

    def test_create_add_reorder_persist(self):
        st = C.Store(self.path)
        a = st.create('Watch Soon')
        b = st.create('Star Wars')
        self.assertNotEqual(a, b)
        for f in ('/m/1.mkv', '/m/2.mkv', '/m/3.mkv'):
            st.add(a, f)
        st.add(a, '/m/2.mkv')                       # already there: kept once
        st.add(b, '/m/2.mkv')                       # a movie may be in several collections
        st.reorder(a, ['/m/3.mkv', '/m/1.mkv', '/m/2.mkv'])
        again = C.Store(self.path)
        self.assertEqual([c['name'] for c in again.items], ['Watch Soon', 'Star Wars'])
        self.assertEqual(again.get(a)['members'], ['/m/3.mkv', '/m/1.mkv', '/m/2.mkv'])
        self.assertTrue(again.contains(b, ['/m/9.mkv', '/m/2.mkv']))
        self.assertEqual(again.create('Next'), 'c3')

    def test_rename_remove_delete(self):
        st = C.Store(self.path)
        a = st.create('A')
        st.add(a, '/m/1.mkv')
        st.add(a, '/m/2.mkv')
        st.rename(a, 'Renamed')
        st.remove(a, ['/m/1.mkv', '/m/1-copy.mkv'])
        self.assertEqual(st.get(a), {'id': a, 'name': 'Renamed', 'members': ['/m/2.mkv']})
        st.delete(a)
        self.assertEqual(C.Store(self.path).items, [])

    def test_reorder_keeps_files_not_on_screen(self):
        st = C.Store(self.path)
        a = st.create('A')
        for f in ('/m/1.mkv', '/gone.mkv', '/m/2.mkv'):
            st.add(a, f)
        st.reorder(a, ['/m/2.mkv', '/m/1.mkv'])
        self.assertEqual(st.get(a)['members'], ['/m/2.mkv', '/m/1.mkv', '/gone.mkv'])

    def test_poll_sees_other_writers(self):
        st = C.Store(self.path)
        other = C.Store(self.path)
        other.create('From elsewhere')
        self.assertTrue(st.poll())
        self.assertEqual([c['name'] for c in st.items], ['From elsewhere'])
        self.assertFalse(st.poll())

    def test_reads_files_from_earlier_format(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, 'w') as f:
            f.write('{"collections": [{"id": "c4", "name": "Old", "files": ["/m/1.mkv"]}]}')
        st = C.Store(self.path)
        self.assertEqual(st.get('c4')['members'], ['/m/1.mkv'])
        self.assertEqual(st.create('Next'), 'c5')

    def test_broken_file_is_empty(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, 'w') as f:
            f.write('{not json')
        self.assertEqual(C.Store(self.path).items, [])


def album(i, title, artist, added='', played='', playcount=0):
    return Album(i, title, artist, artist.lower(), (artist,), frozenset(), frozenset(), 2000, '',
                 dateadded=added, lastplayed=played, playcount=playcount)


def show(i, title, added='', played='', watched=0, inprogress=False, file=None):
    return Show(i, title, title.lower(), 2010, frozenset(), frozenset(), (), '', '', 2, 20, watched,
                file=file if file is not None else f'/tv/{title}/', dateadded=added, lastplayed=played,
                inprogress=inprogress)


class OtherKindsTest(unittest.TestCase):
    def test_albums(self):
        albums = [album(1, 'Blue', 'Joni Mitchell', added='2026-10-15 10:00:00'),
                  album(2, 'Kind of Blue', 'Miles Davis', added='2024-01-01 10:00:00', played='2026-10-17 22:00:00',
                        playcount=3),
                  album(3, 'Time Out', 'Dave Brubeck', played='2026-10-10 22:00:00'),   # one song played
                  album(4, 'Unplayed', 'Nobody')]
        self.assertEqual([a.albumid for a in C.new_movies(albums, 30, NOW)], [1])
        self.assertEqual([a.albumid for a in C.played_movies(albums)], [2, 3])
        self.assertEqual(C.BUILTINS['music'], ('new', 'played'))
        self.assertEqual(C.member_key(albums[0]), 'album://Joni Mitchell/Blue')
        self.assertEqual(C.describe('c1', albums[0], now=NOW), 'Joni Mitchell  ·  2000')

    def test_shows(self):
        shows = [show(1, 'Atlas', added='2026-10-17 23:00:00', played='2026-10-18 09:00:00', inprogress=True),
                 show(2, 'Bluey', played='2026-10-16 09:00:00', watched=4),
                 show(3, 'Cosmos', file='')]
        self.assertEqual([t.tvshowid for t in C.paused_movies(shows)], [1])
        self.assertEqual([t.tvshowid for t in C.played_movies(shows)], [2])
        self.assertEqual([t.tvshowid for t in C.new_movies(shows, 30, NOW)], [1])
        self.assertEqual(C.member_key(shows[0]), '/tv/Atlas/')
        self.assertEqual(C.member_key(shows[2]), 'title://Cosmos/2010')
        pairs = C.resolve(['title://Cosmos/2010', '/tv/Atlas/'], shows, shows)
        self.assertEqual([t.tvshowid for t, _ in pairs], [3, 1])


class ResolveTest(unittest.TestCase):
    def test_order_missing_and_merged_copies(self):
        a = movie(1, 'Alien', 1979, file='/a.mkv')
        a2 = movie(2, 'Alien', 1979, file='/a-4k.mkv', resume=5.0)    # kept when merged
        b = movie(3, 'Brazil', 1985, file='/b.mkv')
        library = [a, a2, b]
        shown = merge_duplicates(library)
        pairs = C.resolve(['/b.mkv', '/missing.mkv', '/a.mkv', '/a-4k.mkv'], library, shown)
        self.assertEqual([(m.movieid, f) for m, f in pairs], [(3, '/b.mkv'), (2, '/a.mkv')])
        unmerged = C.resolve(['/a.mkv', '/a-4k.mkv'], library, library)
        self.assertEqual([m.movieid for m, _ in unmerged], [1, 2])


if __name__ == '__main__':
    unittest.main()
