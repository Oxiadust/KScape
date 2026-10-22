"""Unit tests for the media information screens' pure parts: cast rows, details rows, extras
detection, scraper art parsing, provider answers and the string table.
Run: python3 -m unittest discover -s tests"""
import os
import re
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from resources.lib import artchoice, extras, people  # noqa: E402
from resources.lib import s as S  # noqa: E402

PO = os.path.join(os.path.dirname(__file__), '..', 'resources', 'language', 'resource.language.en_gb', 'strings.po')


def tr(n):
    return S.TEXT.get(n) or f'#{n}'


def _metadata():
    """metadata.py needs Kodi's modules; its shaping functions are pure."""
    for name in ('xbmc', 'xbmcaddon', 'xbmcvfs'):
        sys.modules.setdefault(name, types.ModuleType(name))
    sys.modules['xbmcaddon'].Addon = lambda *a: types.SimpleNamespace(getSettingString=lambda k: '')
    sys.modules['xbmcvfs'].translatePath = lambda p: '/tmp/x'
    sys.modules['xbmc'].LOGINFO = 1
    sys.modules['xbmc'].log = lambda *a: None
    from resources.lib import metadata
    return metadata


class StringTable(unittest.TestCase):
    def test_every_id_is_in_the_po_with_the_same_english(self):
        with open(PO, encoding='utf-8') as f:
            text = f.read()
        found = dict(re.findall(r'msgctxt "#(\d+)"\nmsgid "(.*)"', text))
        for n, english in S.TEXT.items():
            self.assertIn(str(n), found, n)
            self.assertEqual(found[str(n)].replace('\\"', '"').replace('\\\\', '\\'), english, n)

    def test_ids_are_unique(self):
        ids = [v for k, v in vars(S).items() if k.isupper() and isinstance(v, int)]
        self.assertEqual(len(ids), len(set(ids)))


class CastRows(unittest.TestCase):
    D = {'director': ['Ann Dir', 'Zed Both'], 'writer': ['Wes Writer', 'Zed Both'],
         'cast': [{'name': 'Zed Both', 'role': 'Cop', 'order': 1, 'thumbnail': 'z.jpg'},
                  {'name': 'Cy Actor', 'role': 'Villain', 'order': 0, 'thumbnail': 'c.jpg'}]}

    def test_order_and_merging(self):
        rows = people.cast_rows(self.D, tr)
        self.assertEqual([r['name'] for r in rows], ['Ann Dir', 'Zed Both', 'Wes Writer', 'Cy Actor'])
        zed = rows[1]
        self.assertEqual(zed['thumb'], 'z.jpg')
        self.assertEqual(zed['department'], 'Acting')
        self.assertIn('Cop', zed['role'])
        self.assertIn(tr(S.P_DIRECTOR), zed['role'])

    def test_summary(self):
        rows = {r['name']: r for r in people.cast_rows(self.D, tr)}
        self.assertEqual(people.person_summary(rows['Cy Actor'], tr), 'as Villain')
        self.assertEqual(people.person_summary(rows['Ann Dir'], tr), tr(S.P_DIRECTOR))
        self.assertTrue(people.person_summary(rows['Zed Both'], tr).startswith('as Cop'))

    def test_empty(self):
        self.assertEqual(people.cast_rows({}, tr), [])
        self.assertEqual(people.cast_rows(None, tr), [])

    def test_life_line(self):
        self.assertEqual(people.life_line({'birthday': '1964-09-02', 'place': 'Beirut'}, tr), 'Born 1964-09-02 in Beirut')
        self.assertEqual(people.life_line({}, tr), '')


class DetailRows(unittest.TestCase):
    def labels(self, rows):
        return {label: value for label, value in rows}

    def test_movie_rows_leave_out_what_is_missing(self):
        d = {'title': 'Heat', 'originaltitle': 'Heat', 'tagline': 'A story', 'premiered': '1995-12-15',
             'runtime': 10200, 'genre': ['Crime', 'Drama'], 'director': ['Michael Mann'], 'studio': [],
             'country': ['USA'], 'mpaa': 'Rated R', 'top250': 0, 'ratings': {'themoviedb': {'rating': 8.2}},
             'streamdetails': {'audio': [{'language': 'eng', 'codec': 'dts', 'channels': 6}],
                               'subtitle': [], 'video': [{'width': 3840, 'height': 2160, 'codec': 'hevc'}]},
             'uniqueid': {'imdb': 'tt0113277'}}
        rows = self.labels(people.movie_rows(d, {}, tr, lambda c: {'eng': 'English'}.get(c, c)))
        self.assertNotIn(S.D_ORIGINAL_TITLE, rows)               # same as the title
        self.assertNotIn(S.D_STUDIOS, rows)
        self.assertNotIn(S.D_TOP250, rows)
        self.assertNotIn(S.D_SUBTITLES, rows)
        self.assertEqual(rows[S.D_TAGLINE], 'A story')
        self.assertEqual(rows[S.D_AUDIO_LANGS], 'English')
        self.assertIn('3840×2160', rows[S.D_VIDEO])
        self.assertIn('TMDB 8.2', rows[S.D_RATINGS])
        self.assertEqual(rows[S.D_IDS], 'IMDB tt0113277')

    def test_provider_fields(self):
        rows = self.labels(people.movie_rows({'title': 'X'}, {'budget': '$60,000,000', 'revenue': '$187,436,818',
                                                               'companies': ['Regency', 'Forward Pass'],
                                                               'original_language': 'en', 'awards': 'Won 1 Oscar'},
                                             tr, lambda c: 'English'))
        self.assertEqual(rows[S.D_BUDGET], '$60,000,000')
        self.assertEqual(rows[S.D_COMPANIES], 'Regency, Forward Pass')
        self.assertEqual(rows[S.D_LANGUAGE], 'English')
        self.assertEqual(rows[S.D_AWARDS], 'Won 1 Oscar')

    def test_empty_details(self):
        self.assertEqual(people.movie_rows({}, {}, tr), [])
        self.assertEqual(people.show_rows({}, [], tr), [])
        self.assertEqual(people.album_rows({}, [], tr), [])

    def test_album_and_song(self):
        songs = [{'duration': 200, 'contributors': [{'name': 'A', 'role': 'Composer'}, {'name': 'B', 'role': 'composer'}]},
                 {'duration': 100, 'contributors': [{'name': 'B', 'role': 'Composer'}, {'name': 'Z', 'role': 'Producer'}]}]
        rows = self.labels(people.album_rows({'artist': ['X'], 'year': 1999, 'albumlabel': 'Sub Pop'}, songs, tr))
        self.assertEqual(rows[S.D_LABEL], 'Sub Pop')
        self.assertEqual(rows[S.D_TRACKS], '2')
        self.assertEqual(rows[S.D_DURATION], '5:00')
        self.assertEqual(rows[S.D_COMPOSER], 'A, B')
        song = self.labels(people.song_rows({'title': 't', 'track': 3, 'disc': 2, 'bitrate': 320000,
                                             'samplerate': 44100, 'file': '/m/a.flac',
                                             'contributors': [{'name': 'P', 'role': 'Producer'}]}, tr))
        self.assertEqual(song[S.D_CREDITS], 'Producer: P')
        song = self.labels(people.song_rows({'title': 't', 'track': 3, 'disc': 2, 'bitrate': 320000,
                                             'samplerate': 44100, 'file': '/m/a.flac'}, tr))
        self.assertEqual(song[S.D_TRACK], '2-3')
        self.assertEqual(song[S.D_BITRATE], '320 kbps')
        self.assertEqual(song[S.D_SAMPLE_RATE], '44.1 kHz')
        self.assertEqual(song[S.D_CODEC], 'FLAC')

    def test_artist(self):
        d = {'artist': 'Band', 'formed': '1991', 'disbanded': '2004', 'genre': ['Rock'], 'yearsactive': ['1991 - 2004']}
        rows = self.labels(people.artist_rows(d, tr))
        self.assertEqual(rows[S.D_FORMED], '1991')
        self.assertEqual(rows[S.D_YEARS_ACTIVE], '1991 - 2004')
        self.assertIn('Formed 1991', people.artist_summary(d, tr))


class Extras(unittest.TestCase):
    def test_folders_and_suffixes(self):
        entries = [
            ('Heat.mkv', '/m/Heat/Heat.mkv', False, None),
            ('Heat-trailer.mkv', '/m/Heat/Heat-trailer.mkv', False, None),
            ('Making Of-featurette.mp4', '/m/Heat/mo.mp4', False, None),
            ('notes.txt', '/m/Heat/notes.txt', False, None),
            ('Deleted Scenes', '/m/Heat/Deleted Scenes/', True, [('Cut 1.mkv', '/d/1.mkv'), ('x.nfo', '/d/x.nfo')]),
            ('Subs', '/m/Heat/Subs/', True, [('a.mkv', '/s/a.mkv')]),
        ]
        found = extras.classify(entries, '/m/Heat/Heat.mkv')
        self.assertEqual([(e['category'], e['label']) for e in found],
                         [(S.X_TRAILER, 'Heat'), (S.X_FEATURETTE, 'Making Of'), (S.X_DELETED, 'Cut 1')])

    def test_names(self):
        self.assertEqual(extras.folder_category('Behind The Scenes'), S.X_BEHIND)
        self.assertIsNone(extras.folder_category('Season 1'))
        self.assertEqual(extras.suffix_category('Film (1999)-interview.mkv'), S.X_INTERVIEW)
        self.assertIsNone(extras.suffix_category('Film (1999).mkv'))
        self.assertEqual(extras.title_of('Gag_Reel-other.mkv'), 'Gag Reel')


class Art(unittest.TestCase):
    THUMBS = ('<thumb aspect="poster" preview="p1">u1</thumb><thumb aspect="banner">u2</thumb>'
              '<thumb aspect="poster">u1</thumb><thumb type="season" season="2" aspect="poster">u3</thumb>')
    FANART = '<fanart url="http://x/"><thumb preview="t/a.jpg">o/a.jpg</thumb></fanart>'

    def test_candidates(self):
        self.assertEqual(artchoice.candidates('poster', self.THUMBS), [('u1', 'p1')])
        self.assertEqual(artchoice.candidates('banner', self.THUMBS), [('u2', 'u2')])
        self.assertEqual(artchoice.candidates('poster', self.THUMBS, season=2), [('u3', 'u3')])
        self.assertEqual(artchoice.candidates('fanart', '', self.FANART), [('http://x/o/a.jpg', 'http://x/t/a.jpg')])

    def test_garbage(self):
        self.assertEqual(artchoice.candidates('poster', '<thumb', ''), [])
        self.assertEqual(artchoice.candidates('poster', None, None), [])


class Wikipedia(unittest.TestCase):
    def test_titles_follow_the_department(self):
        md = _metadata()
        self.assertEqual(md.wiki_titles('Sam Liu', 'Directing')[:2], ['Sam Liu (director)', 'Sam Liu (film director)'])
        self.assertEqual(md.wiki_titles('Ann Lee', 'Acting')[0], 'Ann Lee')
        self.assertEqual(len(md.wiki_titles('X', 'Acting')), len(set(md.wiki_titles('X', 'Acting'))))

    def test_person_pages(self):
        md = _metadata()
        self.assertTrue(md.is_person_page({'type': 'standard', 'description': 'American actor (born 1978)', 'extract': 'x'}))
        self.assertFalse(md.is_person_page({'type': 'disambiguation', 'description': 'actor', 'extract': ''}))
        self.assertFalse(md.is_person_page({'type': 'standard', 'description': 'Village in Peru', 'extract': 'A village.'}))
        self.assertFalse(md.is_person_page(None))

    def test_dates_keep_their_precision(self):
        md = _metadata()
        claim = lambda t, p: {'P569': [{'mainsnak': {'datavalue': {'value': {'time': t, 'precision': p}}}}]}
        self.assertEqual(md._wiki_time(claim('+1978-09-12T00:00:00Z', 11), 'P569'), '1978-09-12')
        self.assertEqual(md._wiki_time(claim('+1978-09-00T00:00:00Z', 10), 'P569'), '1978-09')
        self.assertEqual(md._wiki_time(claim('+2000-00-00T00:00:00Z', 9), 'P569'), '2000')
        self.assertEqual(md._wiki_time({}, 'P569'), '')

    def test_shape(self):
        md = _metadata()
        out = md.shape_wiki({'title': 'Al', 'description': 'American actor', 'extract': 'Short.',
                             'thumbnail': {'source': 't.jpg'}}, 'Long intro.', born='1940-04-25', place='New York')
        self.assertEqual(out['biography'], 'Long intro.')
        self.assertEqual(out['image'], 't.jpg')
        self.assertEqual(out['source'], 'Wikipedia')
        self.assertNotIn('deathday', out)


class Providers(unittest.TestCase):
    def test_movie_shape(self):
        md = _metadata()
        out = md.shape_movie({'budget': 60000000, 'revenue': 0, 'original_title': 'Heat', 'original_language': 'en',
                              'production_companies': [{'name': 'Regency'}], 'tagline': ''},
                             {'Awards': 'N/A', 'BoxOffice': '$67,436,818'})
        self.assertEqual(out['budget'], '$60,000,000')
        self.assertEqual(out['revenue'], '$67,436,818')       # TMDB had none: OMDb's
        self.assertNotIn('awards', out)
        self.assertNotIn('tagline', out)

    def test_person_shape_and_pick(self):
        md = _metadata()
        data = {'name': 'Al', 'biography': ' Bio ', 'birthday': '1940-04-25', 'profile_path': '/a.jpg',
                'combined_credits': {'cast': [{'title': 'B', 'release_date': '1990-01-01', 'popularity': 1, 'character': 'x'},
                                              {'title': 'A', 'release_date': '1983-01-01', 'popularity': 9}],
                                     'crew': [{'title': 'C', 'release_date': '1996-01-01', 'job': 'Director'},
                                              {'title': 'D', 'job': 'Gaffer'}]}}
        out = md.shape_person(data)
        self.assertEqual(out['biography'], 'Bio')
        self.assertTrue(out['image'].endswith('/a.jpg'))
        self.assertEqual([f['title'] for f in out['filmography']], ['A', 'B', 'C'])
        hits = [{'id': 1, 'name': 'Al Pacino', 'popularity': 5, 'known_for_department': 'Acting'},
                {'id': 2, 'name': 'Al Pacino', 'popularity': 9, 'known_for_department': 'Directing'},
                {'id': 3, 'name': 'Alan', 'popularity': 99}]
        self.assertEqual(md.pick_person(hits, 'al pacino', 'Acting')['id'], 1)
        self.assertEqual(md.pick_person(hits, 'al pacino')['id'], 2)
        self.assertIsNone(md.pick_person([], 'x'))
        self.assertEqual(md.money(0), '')


if __name__ == '__main__':
    unittest.main()
