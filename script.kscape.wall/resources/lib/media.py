"""Album and TV show records built from Kodi JSON-RPC results (pure Python).

They share the attributes the wall, list and search use with model.Movie: key, title,
sorttitle, year, genres, poster, badge.
"""
from dataclasses import asdict, dataclass
from typing import FrozenSet, Tuple

ALBUM_PROPERTIES = ['title', 'displayartist', 'sortartist', 'artist', 'genre', 'style', 'year',
                    'art', 'description', 'albumlabel']
SHOW_PROPERTIES = ['title', 'sorttitle', 'year', 'genre', 'studio', 'cast', 'art', 'plot',
                   'season', 'episode', 'watchedepisodes', 'mpaa', 'file', 'premiered']
MAX_SHOW_CAST = 8

SORT_TOKENS = ('the ', 'the.', 'the_')       # Kodi's default: titles sort as if "The" were absent


def strip_article(text):
    low = (text or '').lower()
    for t in SORT_TOKENS:
        if low.startswith(t):
            return low[len(t):]
    return low


def _sets(d, keys):
    for key in keys:
        d[key] = sorted(d[key])
    return d


@dataclass(frozen=True)
class Album:
    albumid: int
    title: str
    artist: str                    # as Kodi displays it, e.g. 'Simon & Garfunkel'
    artistsort: str                # lower-case, leading "The" dropped
    artists: Tuple[str, ...]
    genres: FrozenSet[str]
    styles: FrozenSet[str]
    year: int
    poster: str                    # album cover (Kodi's 'thumb' art)
    plot: str = ''                 # album review, when scraped
    label: str = ''                # record label
    badge: str = ''

    @property
    def key(self):
        return self.albumid

    @property
    def sorttitle(self):
        """Albums list by artist, then year, then title (as the music reference does)."""
        return f'{self.artistsort}\x00{self.year:04d}\x00{self.title.lower()}'

    @classmethod
    def from_jsonrpc(cls, a):
        art = a.get('art') or {}
        artist = a.get('displayartist') or ' / '.join(a.get('artist') or ())
        return cls(
            albumid=int(a['albumid']),
            title=a.get('title') or a.get('label') or '',
            artist=artist,
            artistsort=strip_article(a.get('sortartist') or artist),
            artists=tuple(a.get('artist') or ()),
            genres=frozenset(a.get('genre') or ()),
            styles=frozenset(a.get('style') or ()),
            year=int(a.get('year') or 0),
            poster=art.get('thumb') or art.get('poster') or '',
            plot=a.get('description') or '',
            label=a.get('albumlabel') or '',
        )

    def to_cache(self):
        d = asdict(self)
        d['artists'] = list(d['artists'])
        return _sets(d, ('genres', 'styles'))

    @classmethod
    def from_cache(cls, d):
        return cls(**dict(d, artists=tuple(d['artists']), genres=frozenset(d['genres']),
                          styles=frozenset(d['styles'])))

    def looks_same(self, other):
        return (self.poster, self.title, self.artist, self.year) == \
               (other.poster, other.title, other.artist, other.year)


@dataclass(frozen=True)
class Show:
    tvshowid: int
    title: str
    sorttitle: str
    year: int
    genres: FrozenSet[str]
    studios: FrozenSet[str]
    cast: Tuple[str, ...]
    poster: str
    plot: str
    seasons: int
    episodes: int
    watched: int                   # watched episodes
    mpaa: str = ''
    file: str = ''                 # the show's folder
    badge: str = ''

    @property
    def key(self):
        return self.tvshowid

    @classmethod
    def from_jsonrpc(cls, t):
        art = t.get('art') or {}
        cast = sorted(t.get('cast') or [], key=lambda c: c.get('order', 0))
        title = t.get('title') or t.get('label') or ''
        year = int(t.get('year') or 0) or int((t.get('premiered') or '0')[:4] or 0)
        return cls(
            tvshowid=int(t['tvshowid']),
            title=title,
            sorttitle=strip_article(t.get('sorttitle') or title),
            year=year,
            genres=frozenset(t.get('genre') or ()),
            studios=frozenset(t.get('studio') or ()),
            cast=tuple(c['name'] for c in cast[:MAX_SHOW_CAST] if c.get('name')),
            poster=art.get('poster') or art.get('thumb') or '',
            plot=t.get('plot') or '',
            seasons=int(t.get('season') or 0),
            episodes=int(t.get('episode') or 0),
            watched=int(t.get('watchedepisodes') or 0),
            mpaa=t.get('mpaa') or '',
            file=t.get('file') or '',
        )

    def to_cache(self):
        d = asdict(self)
        d['cast'] = list(d['cast'])
        return _sets(d, ('genres', 'studios'))

    @classmethod
    def from_cache(cls, d):
        return cls(**dict(d, cast=tuple(d['cast']), genres=frozenset(d['genres']),
                          studios=frozenset(d['studios'])))

    def looks_same(self, other):
        return (self.poster, self.title, self.year) == (other.poster, other.title, other.year)
