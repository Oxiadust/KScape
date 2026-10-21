"""Unit tests for Group by Collection (moviesets.py). Run: python3 -m unittest discover -s tests"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from resources.lib import moviesets as MS  # noqa: E402
from resources.lib.model import Movie  # noqa: E402

COUNT = lambda n: f'{n} movies'


def movie(i, title, year, setid=0, setname='', genres=(), poster=None):
    return Movie(i, title, title.lower(), year, frozenset(genres), frozenset(), (), setid, frozenset(),
                 f'p{i}' if poster is None else poster, f'plot {i}', 6000, 0.0, setname=setname,
                 resolution='4K', file=f'/m/{i}.mkv')


class GroupTest(unittest.TestCase):
    def setUp(self):
        self.alien = movie(1, 'Alien', 1979, 7, 'Alien Collection', ['Horror'])
        self.aliens = movie(2, 'Aliens', 1986, 7, 'Alien Collection', ['Action'])
        self.brazil = movie(3, 'Brazil', 1985)
        self.empire = movie(4, 'The Empire Strikes Back', 1980, 9, 'Star Wars Collection')
        self.heat = movie(5, 'Heat', 1995)
        self.star = movie(6, 'Star Wars', 1977, 9, 'Star Wars Collection')
        self.zodiac = movie(7, 'Zodiac', 2007)
        self.lonely = movie(8, 'Only One', 2001, 12, 'Lonely Set')
        self.library = [self.alien, self.aliens, self.brazil, self.empire, self.heat, self.lonely,
                        self.star, self.zodiac]
        self.sets = {7: {'title': 'Alien Collection', 'poster': 'setposter', 'plot': ''},
                     9: {'title': 'Star Wars Collection', 'poster': '', 'plot': 'A galaxy far away.'}}

    def test_sets_become_one_cover_in_title_order(self):
        out = MS.group(self.library, self.sets, COUNT)
        self.assertEqual([m.title for m in out],
                         ['Alien Collection', 'Brazil', 'Heat', 'Only One', 'Star Wars Collection', 'Zodiac'])

    def test_set_of_one_stays_a_movie(self):
        out = MS.group(self.library, self.sets, COUNT)
        self.assertIn(self.lonely, out)
        self.assertFalse(MS.is_set(self.lonely))

    def test_cover_artwork_text_and_identity(self):
        out = {m.title: m for m in MS.group(self.library, self.sets, COUNT)}
        alien, wars = out['Alien Collection'], out['Star Wars Collection']
        self.assertTrue(MS.is_set(alien))
        self.assertEqual((MS.set_id(alien), alien.key), (7, -7))
        self.assertEqual(alien.poster, 'setposter')
        self.assertEqual(alien.plot, '2 movies · 1979–1986')
        self.assertEqual(alien.genres, {'Horror', 'Action'})
        self.assertEqual((alien.resolution, alien.file, alien.formats), ('', '', ()))
        self.assertEqual(wars.poster, 'p6')                 # no set art: its first movie's poster
        self.assertEqual(wars.plot, 'A galaxy far away.')

    def test_members_oldest_first(self):
        self.assertEqual([m.movieid for m in MS.members_of(self.library, 9)], [6, 4])

    def test_nothing_to_group(self):
        plain = [self.brazil, self.heat]
        self.assertEqual(MS.group(plain, self.sets, COUNT), plain)

    def test_filtered_set_down_to_one_movie_is_not_grouped(self):
        out = MS.group([self.alien, self.brazil], self.sets, COUNT)
        self.assertEqual(out, [self.alien, self.brazil])


if __name__ == '__main__':
    unittest.main()
