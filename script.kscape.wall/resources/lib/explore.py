"""Explore and movie filters (pure Python): what a filter matches, which values are on offer,
Related Movies, and the filter state a cover wall and its list view share.

A filter is one (category, value) pair; several filters combine (a movie must match them all).
They only ever narrow what the views show - the library itself is never touched. Every value
offered comes from the movies' own metadata, so a category Kodi has nothing for is not offered.

Related Movies keeps movies of the library related to one movie: the same collection (movie set)
first, then shared genres, directors, cast and tags, most related first.
"""
from collections import Counter, namedtuple

from . import streaminfo as SI
from .ranking import score

Filter = namedtuple('Filter', 'cat value')

# In the order the filter menu offers them.
CATEGORIES = ('genre', 'actor', 'director', 'year', 'decade', 'country', 'resolution', 'hdr',
              'audio', 'tmdb', 'rt', 'duration', 'watched', 'set', 'related')
TMDB_STEPS = (8.0, 7.0, 6.0, 5.0)        # "TMDB 7+" and so on
RT_STEPS = (90, 75, 60)                  # Tomatometer: 60% is "fresh"
WATCHED = ('unwatched', 'inprogress', 'watched')
RELATED_WEIGHTS = {'set': 100.0, 'genre': 15.0, 'director': 12.0, 'actor': 8.0, 'tag': 3.0,
                   'decade': 2.0, 'year': 1.0}
RELATED_MIN = 15.0                       # at least one genre, or a stronger link
RELATED_LIMIT = 60


def watched_state(m):
    if m.playcount > 0:
        return 'watched'
    return 'inprogress' if m.resume_position > 0 else 'unwatched'


def matches(f, m, resolved=None):
    """Whether movie `m` matches filter `f` (related is handled by apply()). `resolved` maps a
    filter to the movie ids Kodi's own library filter returned for it (all of a person's
    movies, not only those where they are among the top-billed names a movie record keeps)."""
    if resolved and f in resolved:
        return m.key in resolved[f]
    cat, v = f
    if cat == 'genre':
        return v in m.genres
    if cat == 'actor':
        return v in m.cast
    if cat == 'director':
        return v in m.directors
    if cat == 'year':
        lo, hi = v if isinstance(v, (tuple, list)) else (v, v)
        return bool(m.year) and lo <= m.year <= hi
    if cat == 'decade':
        return bool(m.year) and SI.decade(m.year) == v
    if cat == 'country':
        return v in m.country
    if cat == 'resolution':
        return m.resolution == v
    if cat == 'hdr':
        return m.hdr == v
    if cat == 'audio':
        return v in m.audio
    if cat == 'tmdb':
        return m.tmdb >= v
    if cat == 'rt':
        return m.rt >= v
    if cat == 'duration':
        return SI.duration_class(m.runtime) == v
    if cat == 'watched':
        return watched_state(m) == v
    if cat == 'set':
        return bool(m.setid) and m.setid == v
    return True


def related(anchor, items, limit=RELATED_LIMIT):
    """The anchor (if among `items`), then the items related to it, most related first."""
    ranked = []
    for i, m in enumerate(items):
        if m.key == anchor.key:
            continue
        s = score(anchor, m, RELATED_WEIGHTS)
        if s >= RELATED_MIN:
            ranked.append((-round(s, 6), abs((m.year or 0) - (anchor.year or 0)), i, m))
    ranked.sort(key=lambda t: t[:3])
    head = [m for m in items if m.key == anchor.key][:1]
    return head + [t[3] for t in ranked[:limit]]


def apply(filters, items, library=None, resolved=None):
    """The items matching every filter, in their order (Related Movies: most related first).
    `library` is where a Related Movies anchor is looked up when it is not among `items`;
    `resolved` as for matches()."""
    plain = [f for f in filters if f.cat != 'related']
    out = [m for m in items if all(matches(f, m, resolved) for f in plain)] if plain else list(items)
    for f in filters:
        if f.cat == 'related':
            anchor = next((m for m in list(items) + list(library or ()) if m.key == f.value), None)
            out = related(anchor, out) if anchor else []
    return out


def values(cat, items):
    """[(value, count)] on offer for a category among `items`, in menu order: most common first
    for people and countries, newest first for years, best first for formats and ratings."""
    if cat == 'related' or cat == 'set':
        return []
    count = Counter()
    for m in items:
        if cat == 'genre':
            count.update(m.genres)
        elif cat == 'actor':
            count.update(set(m.cast))
        elif cat == 'director':
            count.update(m.directors)
        elif cat == 'year' and m.year:
            count[m.year] += 1
        elif cat == 'decade' and m.year:
            count[SI.decade(m.year)] += 1
        elif cat == 'country':
            count.update(set(m.country))
        elif cat == 'resolution' and m.resolution:
            count[m.resolution] += 1
        elif cat == 'hdr' and m.hdr:
            count[m.hdr] += 1
        elif cat == 'audio':
            count.update(m.audio)
        elif cat == 'tmdb' and m.tmdb:
            count.update(s for s in TMDB_STEPS if m.tmdb >= s)
        elif cat == 'rt' and m.rt:
            count.update(s for s in RT_STEPS if m.rt >= s)
        elif cat == 'duration' and m.runtime:
            count[SI.duration_class(m.runtime)] += 1
        elif cat == 'watched':
            count[watched_state(m)] += 1
    order = {
        'genre': lambda v: (str(v).casefold(),),
        'actor': lambda v: (-count[v], v.casefold()),
        'director': lambda v: (-count[v], v.casefold()),
        'country': lambda v: (-count[v], v.casefold()),
        'year': lambda v: (-v,),
        'decade': lambda v: (-v,),
        'resolution': lambda v: (SI.RESOLUTIONS.index(v),),
        'hdr': lambda v: (SI.HDR_TYPES.index(v),),
        'audio': lambda v: (SI.AUDIO_FORMATS.index(v),),
        'tmdb': lambda v: (-v,),
        'rt': lambda v: (-v,),
        'duration': lambda v: ([d[0] for d in SI.DURATIONS].index(v),),
        'watched': lambda v: (WATCHED.index(v),),
    }[cat]
    return [(v, count[v]) for v in sorted(count, key=order)]


def categories(items, exclude=()):
    """Categories with at least one value among `items` (not counting Related Movies and
    collections, which are explored from a movie)."""
    return [c for c in CATEGORIES if c not in ('related', 'set') and c not in exclude and values(c, items)]


def explore_sections(movie, details, cast_limit=10):
    """What a movie's Explore panel offers: [(section, [Filter, ...])], empty sections left out.

    `details` is the GetMovieDetails dict (full cast in billing order, countries); the movie
    record fills in when it is missing."""
    d = details or {}
    cast = [c['name'] for c in sorted(d.get('cast') or [], key=lambda c: c.get('order', 0)) if c.get('name')]
    cast = list(dict.fromkeys(cast or movie.cast))[:cast_limit]
    sections = [
        ('related', [Filter('related', movie.key)]),
        ('set', [Filter('set', movie.setid)] if movie.setid else []),
        ('director', [Filter('director', n) for n in (d.get('director') or sorted(movie.directors))]),
        ('actor', [Filter('actor', n) for n in cast]),
        ('genre', [Filter('genre', g) for g in (d.get('genre') or sorted(movie.genres))]),
        ('year', [Filter('year', int(d.get('year') or movie.year))] if (d.get('year') or movie.year) else []),
        ('country', [Filter('country', c) for c in (d.get('country') or movie.country)]),
    ]
    return [(name, fs) for name, fs in sections if fs]


class Session:
    """The filters a wall and its list view show, and the trail Back retraces.

    Exploring from a movie replaces the filters and remembers what they were and which movie it
    came from, so Back returns to that movie's Explore panel with the earlier filters. Back with
    filters but no trail clears them (the full library); with neither, there is nothing to undo.
    """

    def __init__(self):
        self.filters = ()
        self.trail = []                    # [(filters before, movie key explored from)]
        self.version = 0

    def __bool__(self):
        return bool(self.filters)

    def explore(self, f, origin):
        self.trail.append((self.filters, origin))
        self.filters = (f,)
        self.version += 1

    def set(self, filters):
        filters = tuple(dict.fromkeys(filters))
        if filters != self.filters:
            self.filters = filters
            self.version += 1
        if not filters:
            self.trail = []

    def add(self, f):
        self.set(self.filters + (f,))

    def remove(self, f):
        self.set(tuple(x for x in self.filters if x != f))

    def clear(self):
        self.set(())

    def back(self):
        """Undo one step: ('explore', movie key) back to a movie's Explore panel, ('cleared',
        None) after clearing the filters, or None when there was nothing to undo."""
        if self.trail:
            self.filters, origin = self.trail.pop()
            self.version += 1
            return 'explore', origin
        if self.filters:
            self.clear()
            return 'cleared', None
        return None
