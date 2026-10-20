"""Explore and movie filters in the views: labels, the Filter menu, and Kodi's library filter.

The menu is Kodi's select dialog, like the rest of KScape's menus. Each value it offers comes
with how many of the movies shown now have it, so adding a filter always leaves some; the
filters themselves are explore.py's.
"""
import xbmcaddon
import xbmcgui

from . import explore as E
from . import streaminfo as SI
from .library import rpc

ADDON = xbmcaddon.Addon('script.kscape.wall')

S_CATEGORY = {'genre': 32320, 'actor': 32321, 'director': 32322, 'year': 32323, 'decade': 32324,
              'country': 32325, 'resolution': 32326, 'hdr': 32327, 'audio': 32328, 'tmdb': 32329,
              'rt': 32330, 'duration': 32331, 'watched': 32332, 'set': 32333, 'related': 32334}
S_SECTION = {'related': 32302, 'set': 32303, 'director': 32304, 'actor': 32305, 'genre': 32306,
             'year': 32307, 'country': 32308}
S_RELATED_MOVIES = 32309
S_DURATION = {'short': 32340, 'medium': 32341, 'long': 32342}
S_WATCHED = {'watched': 32343, 'unwatched': 32344, 'inprogress': 32345}
S_DECADE, S_TMDB_MIN, S_RT_MIN = 32346, 32347, 32348
S_YEAR_RANGE, S_FROM_YEAR, S_TO_YEAR = 32349, 32350, 32351
S_FILTERS, S_ADD, S_REMOVE, S_CLEAR, S_FILTER_MENU = 32352, 32353, 32354, 32355, 32356
S_NONE_MATCH, S_NONE_HINT = 32357, 32358
S_COUNT, S_COUNT_ONE = 32154, 32155


def tr(string_id):
    return ADDON.getLocalizedString(string_id)


def count_text(n):
    return tr(S_COUNT_ONE) if n == 1 else tr(S_COUNT).format(n)


def value_label(f, library=()):
    """How a filter's value reads: 'Sci-Fi', '1990s', 'TMDB 7+', 'Dolby Atmos'..."""
    cat, v = f
    if cat == 'year':
        return f'{v[0]}–{v[1]}' if isinstance(v, (tuple, list)) else str(v)
    if cat == 'decade':
        return tr(S_DECADE).format(v)
    if cat == 'hdr':
        return SI.HDR_LABELS.get(v, v)
    if cat == 'audio':
        return SI.AUDIO_LABELS.get(v, v)
    if cat == 'tmdb':
        return tr(S_TMDB_MIN).format(f'{v:g}')
    if cat == 'rt':
        return tr(S_RT_MIN).format(v)
    if cat == 'duration':
        return tr(S_DURATION[v])
    if cat == 'watched':
        return tr(S_WATCHED[v])
    if cat == 'set':
        return next((m.setname for m in library if m.setid == v and m.setname), str(v))
    if cat == 'related':
        return next((m.title for m in library if m.key == v), '')
    return str(v)


def filter_label(f, library=()):
    """'Genre: Sci-Fi'; 'Related to Heat'."""
    if f.cat == 'related':
        return tr(32335).format(value_label(f, library))
    return f'{tr(S_CATEGORY[f.cat])}: {value_label(f, library)}'


def describe(filters, count, library=()):
    """'Genre: Sci-Fi + Resolution: 4K · 12 movies'."""
    return f'{"  +  ".join(filter_label(f, library) for f in filters)}  ·  {count_text(count)}'


def empty_text():
    return f'{tr(S_NONE_MATCH)}[CR][COLOR FF9AA3B5]{tr(S_NONE_HINT)}[/COLOR]'


class Resolver:
    """Movie ids of an actor's films from Kodi's own library filter, cached: a movie record
    keeps only its top-billed names, while Kodi knows the whole cast."""

    def __init__(self):
        self.known = {}

    def resolve(self, filters):
        out = {}
        for f in filters:
            if f.cat != 'actor':
                continue
            if f not in self.known:
                result = rpc('VideoLibrary.GetMovies', {'filter': {'actor': f.value}})
                self.known[f] = {int(m['movieid']) for m in result.get('movies', [])}
            out[f] = self.known[f]
        return out


def _ask_year(heading, default):
    text = xbmcgui.Dialog().numeric(0, tr(heading), str(default))
    return int(text) if text and text.isdigit() and 1800 <= int(text) <= 2200 else None


def _choose_value(cat, shown, library):
    """Pick one value of `cat` among the movies shown. None if cancelled."""
    options = [(E.Filter(cat, v), n) for v, n in E.values(cat, shown)]
    labels = [f'{value_label(f, library)}  ({n})' for f, n in options]
    if cat == 'year' and options:
        years = [f.value for f, _ in options]
        labels.insert(0, tr(S_YEAR_RANGE))
        options.insert(0, (None, 0))
    if not options:
        return None
    i = xbmcgui.Dialog().select(tr(S_CATEGORY[cat]), labels)
    if i < 0:
        return None
    f = options[i][0]
    if f is None:                                    # Year range…
        lo = _ask_year(S_FROM_YEAR, min(years))
        hi = _ask_year(S_TO_YEAR, max(years)) if lo is not None else None
        if lo is None or hi is None:
            return None
        return E.Filter('year', (min(lo, hi), max(lo, hi)))
    return f


def edit(session, library, apply_fn):
    """The Filter menu: add a filter, remove one, or clear them all, until closed. `apply_fn`
    returns the movies the current filters leave. Returns True if the filters changed."""
    start = session.version
    preselect = 0
    while True:
        shown = apply_fn()
        rows = [('add', None, tr(S_ADD))]
        rows += [('remove', f, tr(S_REMOVE).format(filter_label(f, library))) for f in session.filters]
        if session.filters:
            rows.append(('clear', None, tr(S_CLEAR)))
        heading = f'{tr(S_FILTERS)}  ·  {count_text(len(shown))}'
        i = xbmcgui.Dialog().select(heading, [label for _, _, label in rows], preselect=min(preselect, len(rows) - 1))
        if i < 0:
            break
        action, f, _ = rows[i]
        preselect = i
        if action == 'clear':
            session.clear()
            break
        if action == 'remove':
            session.remove(f)
            continue
        cats = E.categories(shown)
        j = xbmcgui.Dialog().select(tr(S_ADD), [tr(S_CATEGORY[c]) for c in cats])
        if j < 0:
            continue
        f = _choose_value(cats[j], shown, library)
        if f is not None:
            session.add(f)
    return session.version != start
