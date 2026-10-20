"""Unit tests for stream facts and ratings (streaminfo.py), Explore and filters (explore.py), and
embedded chapters (chapters.py). Run: python3 -m unittest discover -s tests"""
import os
import struct
import sys
import tempfile
import unittest
from dataclasses import replace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from resources.lib import chapters as CH  # noqa: E402
from resources.lib import explore as E  # noqa: E402
from resources.lib import scenemodel as SM  # noqa: E402
from resources.lib import streaminfo as SI  # noqa: E402
from resources.lib.model import Movie  # noqa: E402

F = E.Filter


def movie(i, title, year=2000, genres=(), directors=(), cast=(), runtime=6000, setid=0, **kw):
    return replace(Movie(i, title, title.lower(), year, frozenset(genres), frozenset(directors),
                         tuple(cast), setid, frozenset(), '', '', runtime, 0.0), **kw)


def sd(w=0, h=0, hdr='', aspect=0, audio=()):
    return {'video': [{'width': w, 'height': h, 'hdrtype': hdr, 'aspect': aspect}] if (w or h) else [],
            'audio': [{'codec': c} for c in audio]}


class StreamInfoTest(unittest.TestCase):
    def test_resolution_counts_width_for_scope_films(self):
        self.assertEqual(SI.resolution(sd(3840, 1606)), '4K')
        self.assertEqual(SI.resolution(sd(1920, 800)), '1080p')
        self.assertEqual(SI.resolution(sd(1280, 536)), '720p')
        self.assertEqual(SI.resolution(sd(720, 480)), 'SD')
        self.assertEqual(SI.resolution({}), '')

    def test_hdr(self):
        self.assertEqual(SI.hdr(sd(3840, 2160, 'dolbyvision')), 'dolbyvision')
        self.assertEqual(SI.hdr(sd(3840, 2160, 'hdr10plus')), 'hdr10plus')
        self.assertEqual(SI.hdr(sd(1920, 1080)), 'sdr')
        self.assertEqual(SI.hdr({}), '')                    # no stream details: unknown, not SDR

    def test_audio_formats_best_first(self):
        self.assertEqual(SI.audio_formats(sd(audio=['ac3', 'truehd', 'aac'])), ('truehd', 'dd', 'aac'))
        self.assertEqual(SI.audio_formats(sd(audio=['dtshd_ma', 'dca'])), ('dtshdma', 'dts'))
        self.assertEqual(SI.audio_formats(sd(audio=['eac3'])), ('ddplus',))
        self.assertEqual(SI.audio_formats(sd(audio=['truehd_atmos'])), ('atmos',))
        self.assertEqual(SI.audio_formats(sd(audio=['dtshd_ma_x_imax'])), ('dtsx',))
        self.assertEqual(SI.audio_formats(sd(audio=['pcm_s24le', 'flac', 'opus'])), ('pcm', 'flac'))
        self.assertEqual(SI.audio_formats({}), ())

    def test_ratings(self):
        r = {'themoviedb': {'rating': 7.26, 'votes': 100, 'default': True},
             'tomatometerallcritics': {'rating': 8.3, 'votes': 300}}
        self.assertEqual(SI.tmdb_rating(r), 7.3)
        self.assertEqual(SI.rt_percent(r), 83)
        self.assertEqual(SI.rt_percent({'rottentomatoes': {'rating': 91}}), 91)   # stored as a percent
        self.assertEqual(SI.tmdb_rating({'imdb': {'rating': 8.0}}), 0.0)
        self.assertEqual(SI.rt_percent(None), 0)

    def test_facts_line(self):
        self.assertEqual(SI.facts_line(9780, 2.39, ['United States of America'], 2021), '2h 43m · 2.39:1 · USA · 2021')
        self.assertEqual(SI.facts_line(0, 0, [], 1999), '1999')
        self.assertEqual(SI.runtime_short(45 * 60), '45m')
        self.assertEqual(SI.runtime_short(7200), '2h')

    def test_movie_record_reads_facts(self):
        m = Movie.from_jsonrpc({'movieid': 3, 'title': 'X', 'country': ['France'],
                                'streamdetails': sd(3840, 2160, 'hdr10', 1.78, ['truehd']),
                                'ratings': {'themoviedb': {'rating': 6.5}}, 'uniqueid': {'imdb': 'tt1'}})
        self.assertEqual((m.resolution, m.hdr, m.audio, m.aspect, m.tmdb, m.rt, m.imdb, m.country),
                         ('4K', 'hdr10', ('truehd',), 1.78, 6.5, 0, 'tt1', ('France',)))
        self.assertEqual(Movie.from_cache(m.to_cache()), m)

    def test_old_cache_entries_still_load(self):
        d = movie(1, 'A').to_cache()
        for k in ('country', 'resolution', 'hdr', 'audio', 'aspect', 'tmdb', 'rt', 'imdb', 'setname'):
            d.pop(k)
        self.assertEqual(Movie.from_cache(d).resolution, '')


class FilterTest(unittest.TestCase):
    def setUp(self):
        self.a = movie(1, 'Alien', 1979, {'Sci-Fi', 'Horror'}, {'Ridley Scott'}, ('Sigourney Weaver',),
                       runtime=7020, setid=5, resolution='4K', hdr='hdr10', audio=('dtshdma',), tmdb=8.2,
                       rt=93, country=('United Kingdom',))
        self.b = movie(2, 'Aliens', 1986, {'Sci-Fi', 'Action'}, {'James Cameron'}, ('Sigourney Weaver',),
                       runtime=8220, setid=5, resolution='1080p', hdr='sdr', audio=('dts',), tmdb=7.9,
                       playcount=1)
        self.c = movie(3, 'Heat', 1995, {'Crime'}, {'Michael Mann'}, ('Al Pacino',), runtime=10200,
                       resolution='4K', hdr='dolbyvision', audio=('atmos', 'truehd'), tmdb=7.9,
                       resume_position=60.0)
        self.d = movie(4, 'Blade Runner', 1982, {'Sci-Fi'}, {'Ridley Scott'}, ('Harrison Ford',), runtime=7020,
                       resolution='4K', hdr='dolbyvision')
        self.lib = [self.a, self.b, self.c, self.d]

    def keys(self, filters, items=None):
        return [m.key for m in E.apply(filters, items or self.lib, self.lib)]

    def test_single_filters(self):
        self.assertEqual(self.keys([F('genre', 'Sci-Fi')]), [1, 2, 4])
        self.assertEqual(self.keys([F('director', 'Ridley Scott')]), [1, 4])
        self.assertEqual(self.keys([F('actor', 'Sigourney Weaver')]), [1, 2])
        self.assertEqual(self.keys([F('decade', 1980)]), [2, 4])
        self.assertEqual(self.keys([F('year', (1980, 1995))]), [2, 3, 4])
        self.assertEqual(self.keys([F('audio', 'truehd')]), [3])
        self.assertEqual(self.keys([F('tmdb', 8.0)]), [1])
        self.assertEqual(self.keys([F('rt', 90)]), [1])
        self.assertEqual(self.keys([F('duration', 'long')]), [2, 3])       # Aliens: 2h 17m
        self.assertEqual(self.keys([F('watched', 'inprogress')]), [3])
        self.assertEqual(self.keys([F('watched', 'unwatched')]), [1, 4])
        self.assertEqual(self.keys([F('country', 'United Kingdom')]), [1])
        self.assertEqual(self.keys([F('set', 5)]), [1, 2])

    def test_filters_combine(self):
        self.assertEqual(self.keys([F('genre', 'Sci-Fi'), F('resolution', '4K'), F('hdr', 'dolbyvision')]), [4])
        self.assertEqual(self.keys([F('genre', 'Crime'), F('genre', 'Sci-Fi')]), [])

    def test_resolved_ids_win(self):
        """Kodi's own actor filter knows the whole cast, not only the top-billed names kept."""
        f = F('actor', 'Bill Paxton')
        self.assertEqual([m.key for m in E.apply([f], self.lib, resolved={f: {2}})], [2])

    def test_related_keeps_the_franchise_first(self):
        self.assertEqual(self.keys([F('related', 1)]), [1, 2, 4])           # Heat shares nothing
        self.assertEqual(self.keys([F('related', 1), F('resolution', '4K')]), [1, 4])

    def test_values_offer_only_what_is_there(self):
        self.assertEqual(E.values('resolution', self.lib), [('4K', 3), ('1080p', 1)])
        self.assertEqual(E.values('genre', self.lib)[0], ('Action', 1))
        self.assertEqual(E.values('tmdb', self.lib), [(8.0, 1), (7.0, 3), (6.0, 3), (5.0, 3)])
        self.assertNotIn('rt', E.categories([self.b, self.c]))
        self.assertIn('audio', E.categories(self.lib))

    def test_explore_sections(self):
        details = {'director': ['Ridley Scott'], 'cast': [{'name': 'Tom Skerritt', 'order': 1},
                                                          {'name': 'Sigourney Weaver', 'order': 0}],
                   'genre': ['Horror', 'Sci-Fi'], 'year': 1979, 'country': ['United Kingdom']}
        sections = dict(E.explore_sections(self.a, details))
        self.assertEqual([f.value for f in sections['actor']], ['Sigourney Weaver', 'Tom Skerritt'])
        self.assertEqual(list(sections), ['related', 'set', 'director', 'actor', 'genre', 'year', 'country'])
        self.assertNotIn('set', dict(E.explore_sections(self.c, {})))


class SessionTest(unittest.TestCase):
    def test_back_retraces_explore_then_clears(self):
        s = E.Session()
        s.add(F('genre', 'Sci-Fi'))
        s.explore(F('director', 'Ridley Scott'), origin=1)
        s.explore(F('actor', 'Harrison Ford'), origin=4)
        self.assertEqual(s.back(), ('explore', 4))
        self.assertEqual(s.filters, (F('director', 'Ridley Scott'),))
        self.assertEqual(s.back(), ('explore', 1))
        self.assertEqual(s.filters, (F('genre', 'Sci-Fi'),))
        self.assertEqual(s.back(), ('cleared', None))
        self.assertIsNone(s.back())

    def test_clear_forgets_the_trail(self):
        s = E.Session()
        s.explore(F('genre', 'Crime'), origin=3)
        v = s.version
        s.clear()
        self.assertFalse(s)
        self.assertGreater(s.version, v)
        self.assertIsNone(s.back())


# ---- chapters -------------------------------------------------------------------------------------

def ebml_id(i):
    return i.to_bytes((i.bit_length() + 7) // 8, 'big')


def ebml(i, payload):
    """An element with an 8-byte size (0x01 marker), as muxers write when they patch sizes."""
    return ebml_id(i) + (0x01 << 56 | len(payload)).to_bytes(8, 'big') + payload


def uint(i, v):
    return ebml(i, v.to_bytes(8, 'big'))


def atom(start_ns, name, end_ns=None, hidden=False):
    body = uint(CH.T_START, start_ns) + (uint(CH.T_END, end_ns) if end_ns else b'')
    body += uint(CH.HIDDEN, 1) if hidden else b''
    body += ebml(CH.DISPLAY, ebml(CH.STRING, name.encode()))
    return ebml(CH.ATOM, body)


def mkv(chapters_payload, seekhead=False):
    header = ebml(CH.EBML, b'\x42\x86\x81\x01')
    chapters = ebml(CH.CHAPTERS, chapters_payload)
    filler = ebml(0xEC, b'\x00' * 50)                 # Void
    if seekhead:
        # SeekHead first, a Cluster, then the chapters after it (found only through the SeekHead).
        cluster = ebml(CH.CLUSTER, b'\x00' * 20)
        pos_after = None
        for _ in range(2):
            seek = ebml(CH.SEEK, ebml(CH.SEEKID, ebml_id(CH.CHAPTERS)) + uint(CH.SEEKPOS, pos_after or 0))
            head = ebml(CH.SEEKHEAD, seek)
            pos_after = len(head) + len(cluster)
        body = head + cluster + chapters
    else:
        body = filler + chapters + ebml(CH.CLUSTER, b'\x00' * 20)
    return header + ebml(CH.SEGMENT, body)


def box(kind, payload):
    return struct.pack('>I4s', 8 + len(payload), kind.encode()) + payload


def reader(data):
    return (lambda off, n: data[off:off + n]), len(data)


class ChaptersTest(unittest.TestCase):
    def test_matroska(self):
        edition = ebml(CH.EDITION, atom(0, 'Opening') + atom(90 * 10 ** 9, 'Secret', hidden=True)
                       + atom(120 * 10 ** 9, 'The Dam', 300 * 10 ** 9))
        self.assertEqual(CH.read(*reader(mkv(edition))), [(0.0, None, 'Opening'), (120.0, 300.0, 'The Dam')])

    def test_matroska_through_seekhead(self):
        edition = ebml(CH.EDITION, atom(5 * 10 ** 9, 'Chapter 01'))
        self.assertEqual(CH.read(*reader(mkv(edition, seekhead=True))), [(5.0, None, 'Chapter 01')])

    def test_default_edition_wins(self):
        first = ebml(CH.EDITION, atom(0, 'Theatrical'))
        second = ebml(CH.EDITION, uint(CH.EDITION_DEFAULT, 1) + atom(0, 'Director'))
        self.assertEqual(CH.read(*reader(mkv(first + second)))[0][2], 'Director')

    def test_mp4_nero_chapters(self):
        entries = b''.join(struct.pack('>Q', int(t * 1e7)) + bytes([len(n)]) + n.encode()
                           for t, n in ((0, 'Start'), (63.5, 'Second')))
        chpl = box('chpl', b'\x01\x00\x00\x00' + b'\x00' * 4 + bytes([2]) + entries)
        data = box('ftyp', b'isom' + b'\x00' * 4) + box('moov', box('udta', chpl)) + box('mdat', b'\x00' * 16)
        self.assertEqual(CH.read(*reader(data)), [(0.0, None, 'Start'), (63.5, None, 'Second')])

    def test_mp4_quicktime_chapter_track(self):
        texts = [b'\x00\x05Intro', b'\x00\x04Main']
        head = box('ftyp', b'isom' + b'\x00' * 4)
        mdat_payload = b''.join(texts)

        def build(mdat_offset):
            tkhd = lambda tid: box('tkhd', b'\x00' * 4 + b'\x00' * 8 + struct.pack('>I', tid) + b'\x00' * 60)
            video = box('trak', tkhd(1) + box('tref', box('chap', struct.pack('>I', 2))))
            stbl = box('stbl', box('stts', struct.pack('>II', 0, 2) + struct.pack('>II', 1, 30000) + struct.pack('>II', 1, 10000))
                       + box('stsz', struct.pack('>III', 0, 0, 2) + struct.pack('>II', len(texts[0]), len(texts[1])))
                       + box('stsc', struct.pack('>II', 0, 1) + struct.pack('>III', 1, 2, 1))
                       + box('stco', struct.pack('>II', 0, 1) + struct.pack('>I', mdat_offset)))
            mdhd = box('mdhd', b'\x00' * 4 + b'\x00' * 8 + struct.pack('>I', 1000) + b'\x00' * 8)
            text = box('trak', tkhd(2) + box('mdia', mdhd + box('minf', stbl)))
            return box('moov', video + text)
        moov = build(0)
        offset = len(head) + len(moov) + 8
        data = head + build(offset) + box('mdat', mdat_payload)
        self.assertEqual(CH.read(*reader(data)), [(0.0, None, 'Intro'), (30.0, None, 'Main')])

    def test_not_a_video(self):
        self.assertEqual(CH.read(*reader(b'hello world, not a video')), [])
        self.assertEqual(CH.read(*reader(b'\x1a\x45\xdf\xa3\xff')), [])

    def test_scenes_from_chapters(self):
        chs = [(0.0, None, 'Chapter 1'), (95.0, None, 'The Farmhouse'), (95.4, None, '00:01:35.400'),
               (330.0, None, '')]
        # The 0.4 s chapter is dropped; numbered or timestamp names give way to "Chapter N".
        self.assertEqual(CH.scenes(chs, 400, 'Chapter {}'),
                         [('Chapter 1', 0.0, 95.0), ('Chapter 3', 95.4, 330.0), ('Chapter 4', 330.0, 400)])
        self.assertEqual(CH.scenes([(10.0, None, 'The Dam'), (40.0, None, 'Louvre')], 100, 'Chapter {}'),
                         [('The Dam', 10.0, 40.0), ('Louvre', 40.0, 100)])

    def test_player_percentages(self):
        self.assertEqual(CH.from_percentages('0.00,50.00,bad', 600), [(0.0, None, ''), (300.0, None, '')])


class SceneFavouriteTest(unittest.TestCase):
    def test_favourite_and_duplicates(self):
        with tempfile.TemporaryDirectory() as d:
            st = SM.Store(os.path.join(d, 'scenes.json'))
            sid = st.add_scene('movie', 7, '/m.mkv', 'M', 'The Dam', 100, 252)
            self.assertFalse(st.scene(sid)['favourite'])
            st.update_scene(sid, favourite=True)
            self.assertTrue(SM.Store(st.path).scene(sid)['favourite'])
            self.assertTrue(st.has_scene('movie', 7, 100.2, 252))
            self.assertFalse(st.has_scene('movie', 7, 120, 252))


if __name__ == '__main__':
    unittest.main()
