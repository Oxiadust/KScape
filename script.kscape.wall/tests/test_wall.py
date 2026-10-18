"""Unit tests for ranking and wall layout. Run: python3 -m unittest discover -s tests"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from resources.lib import geometry as G  # noqa: E402
from resources.lib.model import Movie, badge_for, merge_duplicates  # noqa: E402
from resources.lib.ranking import rank_related, score  # noqa: E402
from resources.lib.wallmodel import (Wall, _segment_hits_rect, camera_target, clip_outside,  # noqa: E402
                                     detour, ease_out_back, ease_out_cubic, grid_rows)


def movie(i, title, year=2000, genres=(), directors=(), cast=(), setid=0, tags=()):
    return Movie(i, title, title.lower(), year, frozenset(genres), frozenset(directors),
                 tuple(cast), setid, frozenset(tags), f'poster{i}.jpg', '', 6000, 0.0)


ANCHOR = movie(1, 'Toy Story', 1995, ['Animation', 'Family'], ['John Lasseter'],
               ['Tom Hanks', 'Tim Allen'], setid=7)
SEQUEL = movie(2, 'Toy Story 2', 1999, ['Animation', 'Family'], ['John Lasseter'],
               ['Tom Hanks', 'Tim Allen'], setid=7)
SAME_DIRECTOR = movie(3, 'A Bug\'s Life', 1998, ['Animation'], ['John Lasseter'])
SHARED_STAR = movie(4, 'Cast Away', 2000, ['Drama'], ['Robert Zemeckis'], ['Tom Hanks'])
GENRE_ONLY = movie(5, 'Shrek', 2001, ['Animation', 'Family'], ['Andrew Adamson'])
UNRELATED = movie(6, 'Heat', 1965, ['Crime'], ['Michael Mann'], ['Al Pacino'])
LIBRARY = [ANCHOR, SEQUEL, SAME_DIRECTOR, SHARED_STAR, GENRE_ONLY, UNRELATED]


class RankingTest(unittest.TestCase):
    def test_order_follows_metadata(self):
        # Franchise > director > shared lead actor (20) > two broad shared genres (16) > nothing.
        ranked = [m.title for m in rank_related(ANCHOR, LIBRARY)]
        self.assertEqual(ranked, ['Toy Story 2', 'A Bug\'s Life', 'Cast Away', 'Shrek', 'Heat'])

    def test_anchor_excluded_and_unrelated_scores_zero(self):
        self.assertNotIn(ANCHOR, rank_related(ANCHOR, LIBRARY))
        self.assertEqual(score(ANCHOR, UNRELATED), 0.0)

    def test_deterministic_ties(self):
        twins = [movie(10 + i, f'Film {c}', 1970, ['Crime']) for i, c in enumerate('dcba')]
        order1 = [m.movieid for m in rank_related(ANCHOR, twins)]
        order2 = [m.movieid for m in rank_related(ANCHOR, list(reversed(twins)))]
        self.assertEqual(order1, order2)
        self.assertEqual(order1, [13, 12, 11, 10])      # sort title a, b, c, d

    def test_billing_weights_leads_higher(self):
        lead = movie(20, 'Lead', 1980, cast=['Tom Hanks'])
        cameo = movie(21, 'Cameo', 1980, cast=['A', 'B', 'C', 'D', 'E', 'F', 'G', 'Tom Hanks'])
        self.assertGreater(score(ANCHOR, lead), score(ANCHOR, cameo))


class BadgeTest(unittest.TestCase):
    def test_badges(self):
        self.assertEqual(badge_for({'video': [{'width': 3840, 'height': 2160, 'hdrtype': 'hdr10'}]}), 'HDR')
        self.assertEqual(badge_for({'video': [{'width': 3840, 'height': 1600, 'hdrtype': ''}]}), 'UHD')
        self.assertEqual(badge_for({'video': [{'width': 1920, 'height': 1080, 'hdrtype': ''}]}), '')
        self.assertEqual(badge_for(None), '')

    def test_from_jsonrpc(self):
        m = Movie.from_jsonrpc({'movieid': 5, 'title': 'X', 'year': 2001, 'genre': ['Drama'],
                                'cast': [{'name': 'B', 'order': 1}, {'name': 'A', 'order': 0}],
                                'art': {'thumb': 't.jpg'}, 'resume': {'position': 12.5},
                                'streamdetails': {'video': [{'width': 3840, 'hdrtype': 'dolbyvision'}]}})
        self.assertEqual((m.cast, m.poster, m.resume_position, m.badge), (('A', 'B'), 't.jpg', 12.5, 'HDR'))


class DuplicatesTest(unittest.TestCase):
    def copy(self, i, title, year=2017, resume=0.0, badge='', poster=True):
        return Movie(i, title, title.lower(), year, frozenset(), frozenset(), (), 0, frozenset(),
                     f'p{i}' if poster else '', '', 6000, resume, badge)

    def test_keeps_one_per_title_and_year_in_order(self):
        a, b, c = self.copy(1, 'Alien'), self.copy(2, 'Wonder Woman'), self.copy(3, 'wonder  woman')
        d = self.copy(4, 'Wonder Woman', year=1974)
        self.assertEqual([m.movieid for m in merge_duplicates([a, b, c, d])], [1, 2, 4])

    def test_prefers_resume_then_quality_then_poster(self):
        plain, uhd, hdr = self.copy(1, 'X'), self.copy(2, 'X', badge='UHD'), self.copy(3, 'X', badge='HDR')
        self.assertEqual(merge_duplicates([plain, uhd, hdr])[0].movieid, 3)
        watched = self.copy(4, 'X', resume=600.0)
        self.assertEqual(merge_duplicates([hdr, watched])[0].movieid, 4)
        no_art = self.copy(5, 'Y', poster=False)
        self.assertEqual(merge_duplicates([no_art, self.copy(6, 'Y')])[0].movieid, 6)


class WallTest(unittest.TestCase):
    def make_wall(self, n=40, rows=4):
        return Wall.column_major([movie(100 + i, f'M{i:03d}') for i in range(n)], rows)

    def test_column_major_layout(self):
        w = self.make_wall(10, rows=4)
        self.assertEqual((w.rows, w.cols), (4, 3))
        self.assertEqual(w.at(0, 0).title, 'M000')
        self.assertEqual(w.at(0, 3).title, 'M003')
        self.assertEqual(w.at(1, 0).title, 'M004')
        self.assertIsNone(w.at(2, 3))                    # padding cell
        self.assertEqual(w.cell_of(104), (1, 0))

    def test_grid_rows_bounds(self):
        self.assertEqual(grid_rows(0), G.WALL_MIN_ROWS)
        self.assertEqual(grid_rows(384), 11 if G.WALL_MAX_ROWS >= 11 else G.WALL_MAX_ROWS)
        self.assertEqual(grid_rows(100000), G.WALL_MAX_ROWS)

    def test_arrangement_keeps_anchor_and_clusters_ranked(self):
        w = self.make_wall(40, rows=4)
        anchor_cell = (5, 1)
        anchor = w.at(*anchor_cell)
        ranked = [m for m in w.movies() if m is not anchor]
        new = w.arranged_around(anchor_cell, ranked)
        self.assertIs(new.at(*anchor_cell), anchor)
        self.assertCountEqual([m.movieid for m in new.movies()], [m.movieid for m in w.movies()])
        # The top-ranked movie lands in a cell adjacent to the anchor.
        c, r = new.cell_of(ranked[0].movieid)
        self.assertLessEqual(max(abs(c - 5), abs(r - 1)), 1)
        # Ranks are placed in non-decreasing distance from the anchor.
        dists = [math.hypot((new.cell_of(m.movieid)[0] - 5) * G.PITCH_X,
                            (new.cell_of(m.movieid)[1] - 1) * G.PITCH_Y) for m in ranked]
        self.assertEqual(dists, sorted(dists))

    def test_blocked_cells_receive_lower_ranks(self):
        w = self.make_wall(40, rows=4)
        anchor = w.at(5, 1)
        ranked = [m for m in w.movies() if m is not anchor]
        blocked = [(4, 1), (3, 1), (2, 1)]
        new = w.arranged_around((5, 1), ranked, blocked=blocked)
        self.assertNotIn(new.cell_of(ranked[0].movieid), blocked)

    def test_camera_centres_and_clamps(self):
        w = self.make_wall(400, rows=8)
        cx, cy = camera_target(w, (20, 4))
        self.assertAlmostEqual(cx + G.SCREEN_W / 2, 20 * G.PITCH_X + G.COVER_W / 2, delta=1)
        lx, ly = camera_target(w, (0, 0))
        self.assertEqual((lx, ly), (round(-G.PITCH_X * 0.5), round(-G.PITCH_Y * 0.25)))

    def test_small_wall_is_centred(self):
        w = self.make_wall(3, rows=3)
        cx, _ = camera_target(w, (0, 0))
        self.assertLess(cx, 0)

    def test_clip_outside(self):
        rect = (0, 0, 1920, 1080)
        self.assertEqual(clip_outside((100, 100), (500, 500), rect, 50), (500, 500))
        x, y = clip_outside((960, 540), (9000, 540), rect, 100)
        self.assertAlmostEqual(x, 2020)
        self.assertAlmostEqual(y, 540)

    def test_detour_steers_round_the_selected_cover(self):
        keep_out, size = (400, 400, 600, 700), (100, 150)
        grown = (300, 250, 600, 700)
        self.assertEqual(detour((0, 0), (1000, 0), keep_out, size, 20), [])           # clear already
        for start, end in (((0, 500), (1000, 500)), ((450, 0), (450, 1000)), ((0, 300), (700, 800))):
            route = [start] + detour(start, end, keep_out, size, 20) + [end]
            self.assertGreater(len(route), 2)
            for a, b in zip(route, route[1:]):
                self.assertFalse(_segment_hits_rect(a, b, grown), (start, end, route))

    def test_ease(self):
        self.assertEqual(ease_out_cubic(0), 0)
        self.assertEqual(ease_out_cubic(1), 1)
        self.assertGreater(ease_out_cubic(0.5), 0.5)
        self.assertAlmostEqual(ease_out_back(0), 0)
        self.assertAlmostEqual(ease_out_back(1), 1)
        self.assertGreater(max(ease_out_back(i / 100) for i in range(101)), 1.05)   # overshoots


if __name__ == '__main__':
    unittest.main()
