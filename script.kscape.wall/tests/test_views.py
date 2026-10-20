"""Unit tests for the info screen text and the list view model. Run: python3 -m unittest discover -s tests"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from resources.lib import info, listmodel as L  # noqa: E402
from resources.lib.model import Movie  # noqa: E402

STRINGS = {32040: '{} hour', 32041: '{} hours', 32042: '{} minute', 32043: '{} minutes',
           32044: '{} aspect ratio'}
tr = STRINGS.get


def movie(i, title, year=2000, genres=(), directors=(), cast=(), runtime=6000, mpaa='', badge='', resolution='',
          stereo=False):
    return Movie(i, title, title.lower(), year, frozenset(genres), frozenset(directors),
                 tuple(cast), 0, frozenset(), '', '', runtime, 0.0, badge, mpaa, resolution=resolution,
                 stereo=stereo)


class InfoTest(unittest.TestCase):
    def test_summary_line_matches_reference_shape(self):
        d = {'mpaa': 'Rated PG', 'runtime': 7380, 'year': 2012, 'country': ['USA'],
             'streamdetails': {'video': [{'width': 3840, 'height': 2076, 'aspect': 1.85,
                                          'hdrtype': 'hdr10'}]}}
        self.assertEqual(info.summary_line(d, tr),
                         'Rated PG; 2 hours 3 minutes, 4K HDR10, 1.85 aspect ratio, USA, 2012')

    def test_missing_facts_are_left_out(self):
        self.assertEqual(info.summary_line({'year': 1999}, tr), '1999')
        self.assertEqual(info.summary_line({'mpaa': 'Rated R'}, tr), 'Rated R')
        self.assertEqual(info.summary_line({}, tr), '')

    def test_runtime_words(self):
        self.assertEqual(info.runtime_words(3600, tr), '1 hour')
        self.assertEqual(info.runtime_words(60 * 61, tr), '1 hour 1 minute')
        self.assertEqual(info.runtime_words(0, tr), '')

    def test_quality(self):
        self.assertEqual(info.video_quality({'video': [{'width': 1920, 'height': 800}]}), 'HD')
        self.assertEqual(info.video_quality({'video': [{'width': 3840, 'hdrtype': 'dolbyvision'}]}),
                         '4K Dolby Vision')
        self.assertEqual(info.video_quality({}), '')

    def test_clock(self):
        self.assertEqual(info.clock(3735), '1:02:15')
        self.assertEqual(info.clock(427), '7:07')

    def test_estimate_lines(self):
        self.assertEqual(info.estimate_lines('', 1000, 29), 1)
        self.assertEqual(info.estimate_lines('short', 1000, 29), 1)
        long = ' '.join(['word'] * 100)                       # 499 chars, ~66 per line
        self.assertGreaterEqual(info.estimate_lines(long, 1000, 29), 7)
        self.assertEqual(info.estimate_lines('a\nb', 1000, 29), 2)


A = movie(1, 'Alien', 1979, ['Horror', 'Science Fiction'], ['Ridley Scott'], ['Sigourney Weaver'],
          runtime=7020, mpaa='Rated R', badge='UHD', resolution='1080p', stereo=True)
B = movie(2, 'Babe', 1995, ['Family'], runtime=5460, mpaa='Rated G', resolution='SD')
C = movie(3, 'Cars', 2006, ['Animation', 'Family'], mpaa='Rated G', badge='HDR', resolution='4K')
D = movie(4, 'Dune', 0, [], runtime=0)
MOVIES = [A, B, C, D]


class ListModelTest(unittest.TestCase):
    def ids(self, rows):
        return [(r.movie.movieid, r.group) for r in rows]

    def test_title_order_is_kept(self):
        self.assertEqual(self.ids(L.sort_rows(MOVIES, 'title')), [(1, ''), (2, ''), (3, ''), (4, '')])

    def test_genre_groups_list_a_movie_once_per_genre(self):
        self.assertEqual(self.ids(L.sort_rows(MOVIES, 'genre')), [
            (3, 'Animation'), (2, 'Family'), (3, 'Family'), (1, 'Horror'),
            (1, 'Science Fiction'), (4, '')])

    def test_value_sorts_put_missing_last(self):
        self.assertEqual([r.movie.movieid for r in L.sort_rows(MOVIES, 'year')], [1, 2, 3, 4])
        self.assertEqual([r.movie.movieid for r in L.sort_rows(MOVIES, 'time')], [2, 3, 1, 4])
        self.assertEqual([r.movie.movieid for r in L.sort_rows(MOVIES, 'rating')], [2, 3, 1, 4])
        self.assertEqual([r.movie.movieid for r in L.sort_rows(MOVIES, 'quality')], [3, 1, 2, 4])

    def test_find_row_prefers_group(self):
        rows = L.sort_rows(MOVIES, 'genre')
        self.assertEqual(L.find_row(rows, 3), 0)
        self.assertEqual(L.find_row(rows, 3, 'Family'), 2)
        self.assertEqual(L.find_row(rows, 3, 'Drama'), 0)
        self.assertIsNone(L.find_row(rows, 99))

    def test_sort_letter_skips_the(self):
        self.assertEqual(L.sort_letter('The Lion King'), 4)
        self.assertEqual(L.sort_letter('Life of Pi'), 0)
        self.assertEqual(L.sort_letter('A Clockwork Orange'), 0)      # Kodi only ignores "The"
        self.assertEqual(L.sort_letter('(500) Days of Summer'), 1)
        self.assertIsNone(L.sort_letter('...'))
        self.assertEqual(L.title_markup('The Lion King'),
                         f'The [COLOR {L.AMBER}]L[/COLOR]ion King')

    def test_row_values_mark_the_selected_value(self):
        v = L.row_values(L.Row(C, 'Family'), 'genre')
        self.assertEqual(v['genre'], 'Family')
        self.assertEqual(v['genre_full'], f'Animation[CR][COLOR {L.AMBER}]Family[/COLOR]')
        self.assertEqual(v['genre_mark'], '1')
        self.assertEqual(v['label'], 'Cars')
        v = L.row_values(L.Row(A, ''), 'title')
        self.assertEqual(v['genre_mark'], '')
        self.assertEqual(v['label'], f'[COLOR {L.AMBER}]A[/COLOR]lien')
        self.assertEqual((v['year'], v['time'], v['rating'], v['quality']), ('1979', '1:57', 'R', '1080p · 3D'))
        self.assertEqual(L.row_values(L.Row(D, ''), 'title')['year'], '')

    def test_first_press_sorts_and_stays_on_the_movie(self):
        rows = L.sort_rows(MOVIES, 'title')
        sort, rows2, i = L.step(MOVIES, rows, 'title', 'genre', 2, +1)       # Cars, Down
        self.assertEqual((sort, rows2[i]), ('genre', L.Row(C, 'Animation')))
        sort, rows2, i = L.step(MOVIES, rows, 'title', 'genre', 2, -1)       # Cars, Up
        self.assertEqual(rows2[i], L.Row(C, 'Family'))
        sort, rows2, i = L.step(MOVIES, rows, 'title', 'year', 2, +1)
        self.assertEqual((sort, rows2[i].movie), ('year', C))

    def test_steps_through_values_then_moves_on(self):
        rows = L.sort_rows(MOVIES, 'genre')
        i = L.find_row(rows, 3, 'Animation')
        _, _, i = L.step(MOVIES, rows, 'genre', 'genre', i, +1)
        self.assertEqual(rows[i], L.Row(C, 'Family'))                        # next value
        _, _, i = L.step(MOVIES, rows, 'genre', 'genre', i, +1)
        self.assertEqual(rows[i], L.Row(A, 'Horror'))                        # next row
        _, _, i = L.step(MOVIES, rows, 'genre', 'genre', i, -1)
        self.assertEqual(rows[i], L.Row(C, 'Family'))                        # previous row
        _, _, i = L.step(MOVIES, rows, 'genre', 'genre', 0, -1)
        self.assertEqual(i, 0)                                               # top edge

    def test_scroll_keeps_last_columns_on_screen(self):
        self.assertEqual(L.scroll_for('title'), 0)
        self.assertEqual(L.scroll_for('genre'), 0)
        self.assertEqual(L.scroll_for('cast'), 280)
        total = sum(c.width for c in L.COLUMNS)
        self.assertEqual(L.scroll_for('quality'), total - L.SCROLL_W)
        self.assertEqual(L.scroll_stops(), [0, 280, 680, total - L.SCROLL_W])


if __name__ == '__main__':
    unittest.main()
