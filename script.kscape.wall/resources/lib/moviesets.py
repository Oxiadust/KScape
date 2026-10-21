"""Group by Collection (movie cover wall only): the movies of one Kodi movie set share a cover.

Kodi's own set metadata decides what belongs together (Movie.setid), never titles. A set cover
stands where the set's name falls in title order; selecting it opens a wall of the set's
movies (window.py). A set with one movie on the wall shows that movie itself, as Kodi does by
default. Pure Python: no Kodi calls.
"""
import re
from dataclasses import replace

from .model import MAX_CAST

ARTICLES = re.compile(r'^(the|a|an)\s+', re.IGNORECASE)


def is_set(item):
    """True for a set cover (its key is minus the set id; movie ids are positive)."""
    return getattr(item, 'movieid', 0) < 0


def set_id(item):
    return -item.movieid


def sort_key(title):
    return ARTICLES.sub('', title.strip()).casefold()


def set_cover(setid, members, info, count_text):
    """The cover standing for `members` (in set order): set artwork, falling back to the first
    movie's poster; the set's synopsis, else how many movies and which years. The genres,
    people and tags of all its movies, so the related-cover shuffle still works."""
    first = members[0]
    years = sorted(m.year for m in members if m.year)
    span = '' if not years else (str(years[0]) if years[0] == years[-1] else f'{years[0]}–{years[-1]}')
    plot = info.get('plot') or ' · '.join(p for p in (count_text(len(members)), span) if p)
    cast = []
    for m in members:
        cast += [c for c in m.cast if c not in cast]
    title = info.get('title') or first.setname or first.title
    return replace(first, movieid=-setid, title=title, sorttitle=sort_key(title),
                   year=years[0] if years else 0,
                   genres=frozenset().union(*(m.genres for m in members)),
                   directors=frozenset().union(*(m.directors for m in members)),
                   cast=tuple(cast[:MAX_CAST]),
                   tags=frozenset().union(*(m.tags for m in members)),
                   poster=info.get('poster') or first.poster, plot=plot, resume_position=0.0,
                   badge='', file='', resolution='', hdr='', audio=(), aspect=0.0, tmdb=0.0, rt=0,
                   imdb='', stereo=False, uid='', versions=(), playcount=0, lastplayed='',
                   setname=title)


def members_of(movies, setid):
    """The set's movies, oldest first (as Kodi lists a set)."""
    return sorted((m for m in movies if m.setid == setid), key=lambda m: (m.year or 9999, m.sorttitle))


def group(movies, sets, count_text):
    """`movies` (in library order) with every set of two or more of them as one cover. Movies
    keep their order; a set cover goes in front of the first standalone movie whose title sorts
    after the set's name."""
    by_set = {}
    for m in movies:
        if m.setid:
            by_set.setdefault(m.setid, []).append(m)
    grouped = {sid for sid, ms in by_set.items() if len(ms) > 1}
    if not grouped:
        return list(movies)
    covers = sorted((set_cover(sid, members_of(by_set[sid], sid), sets.get(sid) or {}, count_text)
                     for sid in grouped), key=lambda c: c.sorttitle)
    out, i = [], 0
    for m in movies:
        if m.setid in grouped:
            continue
        key = sort_key(m.sorttitle or m.title)
        while i < len(covers) and covers[i].sorttitle <= key:
            out.append(covers[i])
            i += 1
        out.append(m)
    out += covers[i:]
    return out
