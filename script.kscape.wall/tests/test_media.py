"""Unit tests for albums, TV shows, favourites keys, search and the music/TV tables.
Run: python3 -m unittest discover -s tests"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from resources.lib import geometry as G, listmodel as L  # noqa: E402
from resources.lib.favourites import Favourites, add_params, entry_key, key_of  # noqa: E402
from resources.lib.media import Album, Show  # noqa: E402
from resources.lib.model import Movie  # noqa: E402
from resources.lib.ranking import album_score, rank_related, show_score  # noqa: E402
from resources.lib.search import fold, search  # noqa: E402
from resources.lib.wallmodel import Wall, grid_rows  # noqa: E402


def album(i, title, artist, year=1970, genres=(), styles=(), artists=None):
    return Album.from_jsonrpc({'albumid': i, 'title': title, 'displayartist': artist,
                               'artist': list(artists or [artist]), 'genre': list(genres),
                               'style': list(styles), 'year': year, 'art': {'thumb': f'a{i}.jpg'}})


def show(i, title, year=2010, genres=(), studios=(), cast=()):
    return Show.from_jsonrpc({'tvshowid': i, 'title': title, 'year': year, 'genre': list(genres),
                              'studio': list(studios), 'season': 2, 'episode': 20,
                              'cast': [{'name': n, 'order': k} for k, n in enumerate(cast)],
                              'art': {'poster': f'p{i}.jpg'}})


def movie(i, title, file='', cast=(), directors=()):
    return Movie(i, title, title.lower(), 2000, frozenset(), frozenset(directors), tuple(cast), 0,
                 frozenset(), '', '', 6000, 0.0, file=file)


ABBEY = album(1, 'Abbey Road', 'The Beatles', 1969, ['Rock', 'Pop'])
REVOLVER = album(2, 'Revolver', 'The Beatles', 1966, ['Rock', 'Psychedelic'])
KIND = album(3, 'Kind of Blue', 'Miles Davis', 1959, ['Jazz'])
THRILLER = album(4, 'Thriller', 'Michael Jackson', 1982, ['Pop'])
ALBUMS = sorted([ABBEY, REVOLVER, KIND, THRILLER], key=lambda a: a.sorttitle)


class AlbumTest(unittest.TestCase):
    def test_from_jsonrpc(self):
        self.assertEqual((ABBEY.key, ABBEY.artist, ABBEY.artistsort, ABBEY.poster),
                         (1, 'The Beatles', 'beatles', 'a1.jpg'))
        missing = Album.from_jsonrpc({'albumid': 9, 'label': 'Untitled'})
        self.assertEqual((missing.title, missing.artist, missing.year, missing.poster), ('Untitled', '', 0, ''))

    def test_library_order_is_artist_then_year(self):
        self.assertEqual([a.title for a in ALBUMS], ['Revolver', 'Abbey Road', 'Thriller', 'Kind of Blue'])

    def test_cache_round_trip(self):
        self.assertEqual(Album.from_cache(ABBEY.to_cache()), ABBEY)

    def test_same_artist_ranks_first(self):
        ranked = rank_related(ABBEY, ALBUMS, score_fn=album_score)
        self.assertEqual(ranked[0], REVOLVER)
        self.assertGreater(album_score(ABBEY, THRILLER), album_score(ABBEY, KIND))   # shares Pop


class ShowTest(unittest.TestCase):
    def test_from_jsonrpc_and_cache(self):
        s = show(5, 'The Wire', 2002, ['Crime'], ['HBO'], ['Dominic West'])
        self.assertEqual((s.key, s.sorttitle, s.seasons, s.episodes, s.cast), (5, 'wire', 2, 20, ('Dominic West',)))
        self.assertEqual(Show.from_cache(s.to_cache()), s)
        self.assertEqual(Show.from_jsonrpc({'tvshowid': 1, 'title': 'X', 'premiered': '1999-04-01'}).year, 1999)

    def test_ranking(self):
        a = show(1, 'A', 2010, ['Drama'], ['HBO'], ['X'])
        b = show(2, 'B', 2011, ['Drama'], ['HBO'], ['X'])
        c = show(3, 'C', 1980, ['Comedy'], ['NBC'])
        self.assertEqual(rank_related(a, [a, b, c], score_fn=show_score), [b, c])
        self.assertEqual(show_score(a, c), 0.0)


class FavouritesTest(unittest.TestCase):
    def test_keys_match_what_kodi_stores(self):
        m = movie(1, 'Alien', file='/movies/Alien.mkv')
        self.assertEqual(key_of(m), ('media', '/movies/Alien.mkv'))
        self.assertEqual(key_of(m), entry_key({'type': 'media', 'path': '/movies/Alien.mkv'}))
        self.assertIsNone(key_of(movie(2, 'No file')))
        self.assertEqual(key_of(ABBEY), entry_key({'type': 'window', 'window': 'music',
                                                   'windowparameter': 'musicdb://albums/1'}))
        self.assertEqual(key_of(show(7, 'S')), entry_key({'type': 'window', 'windowparameter':
                                                          'videodb://tvshows/titles/7/?x=1'}))
        self.assertIsNone(entry_key({'type': 'script', 'path': 'x'}))

    def test_add_params(self):
        self.assertEqual(add_params(ABBEY)['windowparameter'], 'musicdb://albums/1/')
        self.assertEqual(add_params(ABBEY)['title'], 'Abbey Road - The Beatles')
        self.assertEqual(add_params(show(7, 'S'))['window'], 'videos')

    def test_toggle_and_version(self):
        store = []

        def rpc(method, params):
            if method == 'Favourites.AddFavourite':          # Kodi 21 adds or removes
                if params in store:
                    store.remove(params)
                else:
                    store.append(params)
                return 'OK'
            return {'favourites': list(store) or None}

        favs = Favourites(rpc, '/nonexistent/favourites.xml')
        v0 = favs.version
        self.assertTrue(favs.toggle(ABBEY))
        self.assertTrue(favs.contains(ABBEY))
        self.assertFalse(favs.contains(REVOLVER))
        self.assertGreater(favs.version, v0)
        self.assertFalse(favs.toggle(ABBEY))
        self.assertFalse(favs.toggle(movie(2, 'No file')))     # unsupported: nothing happens
        self.assertEqual(store, [])


class SearchTest(unittest.TestCase):
    def test_fold(self):
        self.assertEqual(fold('Amélie: Le Fabuleux!'), 'amelie le fabuleux')

    def test_ranks_title_matches_before_people(self):
        films = [movie(1, 'The Batman'), movie(2, 'Batman Begins'), movie(3, 'Superman', cast=['Batman Fan']),
                 movie(4, 'Abatmania'), movie(5, 'Heat')]
        self.assertEqual([m.key for m in search(films, 'batman')], [2, 1, 4, 3])
        self.assertEqual(search(films, '  '), [])
        self.assertEqual(search(films, 'zzz'), [])

    def test_music_matches_artist(self):
        self.assertEqual([a.title for a in search(ALBUMS, 'beatles')], ['Revolver', 'Abbey Road'])
        self.assertEqual([a.title for a in search(ALBUMS, 'jazz')], ['Kind of Blue'])      # genre


class TablesTest(unittest.TestCase):
    def test_music_columns(self):
        rows = L.sort_rows(ALBUMS, 'title', L.MUSIC)
        v = L.row_values(rows[0], 'title', L.MUSIC)
        self.assertEqual(v['label'], f'The [COLOR {L.AMBER}]B[/COLOR]eatles')
        self.assertEqual((v['album'], v['year'], v['genre']), ('Revolver', '1966', 'Psychedelic'))
        self.assertEqual([r.movie.title for r in L.sort_rows(ALBUMS, 'year', L.MUSIC)],
                         ['Kind of Blue', 'Revolver', 'Abbey Road', 'Thriller'])
        self.assertEqual([r.group for r in L.sort_rows(ALBUMS, 'genre', L.MUSIC)][:2], ['Jazz', 'Pop'])
        self.assertEqual(L.scroll_stops(L.MUSIC), [0])                  # every column fits

    def test_tv_columns_and_steps(self):
        shows = [show(1, 'Atlas', 2023, ['Documentary'], ['Field']), show(2, 'Orbital', 2016, ['Drama', 'SF'])]
        v = L.row_values(L.Row(shows[1], ''), 'title', L.TV)
        self.assertEqual((v['network'], v['seasons'], v['episodes']), ('', '2', '20'))
        sort, rows, i = L.step(shows, L.sort_rows(shows, 'title', L.TV), 'title', 'year', 0, +1, L.TV)
        self.assertEqual((sort, rows[i].movie.title), ('year', 'Atlas'))
        self.assertEqual([r.movie.key for r in rows], [2, 1])


class SmallWallTest(unittest.TestCase):
    def test_a_few_items_sit_in_a_short_block(self):
        self.assertEqual(grid_rows(2), 1)
        self.assertEqual(grid_rows(8), 2)
        self.assertEqual(grid_rows(9), G.POSTER.min_rows)
        self.assertEqual(grid_rows(11, G.SQUARE), 2)
        self.assertEqual(grid_rows(30, G.SQUARE), G.SQUARE.min_rows)

    def test_square_wall_uses_its_layout(self):
        w = Wall.column_major(ALBUMS, layout=G.SQUARE)
        self.assertIs(w.layout, G.SQUARE)
        self.assertEqual(w.cell_of(ABBEY.key), (1, 0))


if __name__ == '__main__':
    unittest.main()
