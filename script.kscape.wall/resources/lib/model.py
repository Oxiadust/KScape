"""Movie record built from Kodi JSON-RPC VideoLibrary.GetMovies results (pure Python)."""
from dataclasses import asdict, dataclass
from typing import FrozenSet, Tuple

MAX_CAST = 8

JSONRPC_PROPERTIES = [
    'title', 'sorttitle', 'year', 'genre', 'director', 'cast', 'set', 'setid', 'tag',
    'art', 'plot', 'runtime', 'file', 'resume', 'playcount', 'streamdetails', 'mpaa',
    'dateadded', 'lastplayed',
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
        )

    def to_cache(self):
        d = asdict(self)
        for key in ('genres', 'directors', 'tags'):
            d[key] = sorted(d[key])
        d['cast'] = list(d['cast'])
        return d

    @classmethod
    def from_cache(cls, d):
        return cls(**dict(d, genres=frozenset(d['genres']), directors=frozenset(d['directors']),
                          tags=frozenset(d['tags']), cast=tuple(d['cast'])))

    def looks_same(self, other):
        """True when the cover would render identically (cast-only changes are invisible)."""
        return (self.poster, self.badge, self.title, self.year) == \
               (other.poster, other.badge, other.title, other.year)


BADGE_RANK = {'HDR': 2, 'UHD': 1, '': 0}


def _title_key(movie):
    return (' '.join(movie.title.casefold().split()), movie.year)


def merge_duplicates(movies):
    """One movie per title and year, in the original order.

    The copy kept is the one with a resume point, then the best quality badge, then one with a
    poster, then the lowest movie id, so the choice is stable.
    """
    best = {}
    order = []
    for m in movies:
        key = _title_key(m)
        if key not in best:
            order.append(key)
            best[key] = m
            continue
        cur = best[key]
        rank = lambda x: (x.resume_position > 0, BADGE_RANK.get(x.badge, 0), bool(x.poster), -x.movieid)
        if rank(m) > rank(cur):
            best[key] = m
    return [best[k] for k in order]
