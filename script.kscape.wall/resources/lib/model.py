"""Movie record built from Kodi JSON-RPC VideoLibrary.GetMovies results (pure Python)."""
from dataclasses import asdict, dataclass
from typing import FrozenSet, Tuple

import re

from . import streaminfo as SI
from . import versions as V

MAX_CAST = 8

JSONRPC_PROPERTIES = [
    'title', 'sorttitle', 'year', 'genre', 'director', 'cast', 'set', 'setid', 'tag',
    'art', 'plot', 'runtime', 'file', 'resume', 'playcount', 'streamdetails', 'mpaa',
    'dateadded', 'lastplayed', 'country', 'ratings', 'uniqueid',
]
# Cast is ~70% of the cost of listing a large library (28 of 41 s for 5,000 movies on the
# development Mac) and only the shuffle ranking needs it, so it is fetched separately.
LIGHT_PROPERTIES = [p for p in JSONRPC_PROPERTIES if p != 'cast']


def badge_for(streamdetails):
    """Cover badge from the first video stream: 'HDR' for any HDR type, else 'UHD' for 4K."""
    video = (streamdetails or {}).get('video') or []
    if not video:
        return ''
    v = video[0]
    if v.get('hdrtype'):
        return 'HDR'
    if (v.get('width') or 0) >= 3200 or (v.get('height') or 0) >= 1800:
        return 'UHD'
    return ''


@dataclass(frozen=True)
class Movie:
    movieid: int
    title: str
    sorttitle: str
    year: int
    genres: FrozenSet[str]
    directors: FrozenSet[str]
    cast: Tuple[str, ...]          # billing order, top MAX_CAST
    setid: int
    tags: FrozenSet[str]
    poster: str
    plot: str
    runtime: int                   # seconds
    resume_position: float
    badge: str = ''
    mpaa: str = ''                 # as scraped, e.g. 'Rated PG-13'
    file: str = ''                 # what Kodi's favourites store for a library movie
    dateadded: str = ''            # 'YYYY-MM-DD HH:MM:SS', as Kodi reports them (collections)
    lastplayed: str = ''
    playcount: int = 0
    # From the stream details and ratings Kodi recorded ('' / 0 / () when it has none).
    country: Tuple[str, ...] = ()
    resolution: str = ''           # streaminfo.RESOLUTIONS
    hdr: str = ''                  # streaminfo.HDR_TYPES
    audio: Tuple[str, ...] = ()    # streaminfo.AUDIO_FORMATS, best first
    aspect: float = 0.0
    tmdb: float = 0.0              # out of 10
    rt: int = 0                    # Rotten Tomatoes Tomatometer, percent
    imdb: str = ''                 # IMDb id, for an optional ratings lookup (ratings.py)
    setname: str = ''
    stereo: bool = False           # the file is 3D
    uid: str = ''                  # 'tmdb:603' / 'imdb:tt0133093': what makes copies one film
    versions: Tuple[V.Version, ...] = ()   # Kodi's versions of this movie (two or more)

    @property
    def formats(self):
        """'4K', '1080p', '720p', '3D', 'SD' / 'DVD' this movie is available in (every version)."""
        return V.formats(self.versions, self.resolution, self.stereo, self.file)

    @property
    def key(self):
        return self.movieid

    @classmethod
    def from_jsonrpc(cls, m):
        art = m.get('art') or {}
        cast = sorted(m.get('cast') or [], key=lambda c: c.get('order', 0))
        return cls(
            movieid=int(m['movieid']),
            title=m.get('title') or m.get('label') or '',
            sorttitle=(m.get('sorttitle') or m.get('title') or '').lower(),
            year=int(m.get('year') or 0),
            genres=frozenset(m.get('genre') or ()),
            directors=frozenset(m.get('director') or ()),
            cast=tuple(c['name'] for c in cast[:MAX_CAST] if c.get('name')),
            setid=int(m.get('setid') or 0),
            tags=frozenset(m.get('tag') or ()),
            poster=art.get('poster') or art.get('thumb') or '',
            plot=m.get('plot') or '',
            runtime=int(m.get('runtime') or 0),
            resume_position=float((m.get('resume') or {}).get('position') or 0),
            badge=badge_for(m.get('streamdetails')),
            mpaa=m.get('mpaa') or '',
            file=m.get('file') or '',
            dateadded=m.get('dateadded') or '',
            lastplayed=m.get('lastplayed') or '',
            playcount=int(m.get('playcount') or 0),
            country=tuple(m.get('country') or ()),
            resolution=SI.resolution(m.get('streamdetails')),
            hdr=SI.hdr(m.get('streamdetails')),
            audio=SI.audio_formats(m.get('streamdetails')),
            aspect=SI.aspect(m.get('streamdetails')),
            tmdb=SI.tmdb_rating(m.get('ratings')),
            rt=SI.rt_percent(m.get('ratings')),
            imdb=(m.get('uniqueid') or {}).get('imdb') or '',
            setname=m.get('set') or '',
            stereo=SI.stereo(m.get('streamdetails')),
            uid=uid_of(m.get('uniqueid')),
        )

    def to_cache(self):
        d = asdict(self)
        for key in ('genres', 'directors', 'tags'):
            d[key] = sorted(d[key])
        for key in ('cast', 'country', 'audio'):
            d[key] = list(d[key])
        d['versions'] = [v.to_cache() for v in self.versions]
        return d

    @classmethod
    def from_cache(cls, d):
        return cls(**dict(d, genres=frozenset(d['genres']), directors=frozenset(d['directors']),
                          tags=frozenset(d['tags']), cast=tuple(d['cast']),
                          country=tuple(d.get('country') or ()), audio=tuple(d.get('audio') or ()),
                          versions=tuple(V.Version.from_cache(v) for v in d.get('versions') or ())))

    def looks_same(self, other):
        """True when the cover would render identically (cast-only changes are invisible)."""
        return (self.poster, self.badge, self.formats, self.title, self.year) == \
               (other.poster, other.badge, other.formats, other.title, other.year)


def uid_of(uniqueid):
    """The film's stable id: TMDB, else IMDb ('' without either)."""
    u = uniqueid or {}
    if u.get('tmdb'):
        return f'tmdb:{u["tmdb"]}'
    if u.get('imdb'):
        return f'imdb:{u["imdb"]}'
    return ''


EDITION = re.compile(r"(director'?s[ ._-]?cut|extended|unrated|uncut|theatrical|remastered|imax|"
                     r"final[ ._-]?cut|special[ ._-]?edition|ultimate|criterion|redux|open[ ._-]?matte)",
                     re.IGNORECASE)


def edition_of(movie):
    """Edition named in the title or file name ('directors cut', 'extended'...), '' if none: two
    copies of one film in different editions stay apart."""
    found = EDITION.findall(f'{movie.title} {movie.file}')
    return ' '.join(sorted({re.sub(r'[^a-z]', '', f.lower()) for f in found}))


def _film_key(movie):
    """The cheap part of _title_key: TMDB / IMDb id, title and year (no edition)."""
    uid = getattr(movie, 'uid', '')
    if not uid:
        return ('item', movie.key)
    return (uid, ' '.join(movie.title.casefold().split()), movie.year)


def _title_key(movie):
    """What separate library entries of one film share: the same TMDB / IMDb id, title, year and
    edition. Entries without such an id never match another (titles alone are not enough)."""
    k = _film_key(movie)
    return k if k[0] == 'item' else k + (edition_of(movie),)
