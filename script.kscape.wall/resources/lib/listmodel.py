"""List view rows, columns and sorting (pure Python).

The list shows one row per movie in library title order. Some columns also sort: moving up or
down while one of them is focused re-orders the list by it, keeping the movie under the band.
Sorting by genre lists a movie once under each of its genres (Kaleidescape-style grouping);
the genre a row is listed under is its `group`.
"""
from collections import namedtuple

Column = namedtuple('Column', 'key label width sortable')

# Title is fixed on the left; the others scroll horizontally (widths in 1080p pixels).
TITLE = Column('title', 32050, 0, True)
COLUMNS = [
    Column('genre', 32051, 280, True),
    Column('cast', 32052, 400, False),
    Column('director', 32053, 380, False),
    Column('year', 32054, 150, True),
    Column('time', 32055, 150, True),
    Column('rating', 32056, 170, True),
    Column('quality', 32057, 210, True),
]
ALL_COLUMNS = [TITLE] + COLUMNS
SCROLL_W = 1060                    # visible width right of the title column

AMBER = 'FFF5A01A'
FULL_LINES = 4                     # values shown in the focused row's band

Row = namedtuple('Row', 'movie group')

MPAA_ORDER = ['G', 'PG', 'PG-13', 'R', 'NC-17']
QUALITY_ORDER = {'HDR': 0, 'UHD': 1, '': 2}


def column_offsets():
    """x of each scrolling column inside the scrolling strip."""
    out, x = {}, 0
    for col in COLUMNS:
        out[col.key] = x
        x += col.width
    return out


def scroll_for(key):
    """Horizontal scroll that puts the focused column first, without running past the end."""
    offsets = column_offsets()
    total = sum(c.width for c in COLUMNS)
    return max(0, min(offsets.get(key, 0), total - SCROLL_W))


def scroll_stops():
    return sorted({scroll_for(c.key) for c in ALL_COLUMNS})


def rating_short(mpaa):
    """'Rated PG-13' -> 'PG-13'; other rating systems are kept as written."""
    mpaa = (mpaa or '').strip()
    return mpaa[6:].strip() if mpaa.lower().startswith('rated ') else mpaa


def runtime_clock(seconds):
    minutes = int(round((seconds or 0) / 60.0))
    return f'{minutes // 60}:{minutes % 60:02d}' if minutes > 0 else ''


def _rating_key(movie):
    r = rating_short(movie.mpaa)
    if r in MPAA_ORDER:
        return (0, MPAA_ORDER.index(r), '')
    return (1 if r else 2, 0, r.casefold())


def sort_rows(movies, key):
    """Rows for `movies` (given in title order) sorted by column `key`.

    Ties keep title order. Movies without a value for the key go last. Columns that do not
    sort (cast, director) return title order.
    """
    order = {m.movieid: i for i, m in enumerate(movies)}
    if key == 'genre':
        rows = [Row(m, g) for m in movies for g in sorted(m.genres)]
        rows += [Row(m, '') for m in movies if not m.genres]
        rows.sort(key=lambda r: (r.group == '', r.group.casefold(), order[r.movie.movieid]))
        return rows
    keys = {
        'year': lambda m: (m.year <= 0, m.year),
        'time': lambda m: (m.runtime <= 0, m.runtime),
        'rating': _rating_key,
        'quality': lambda m: QUALITY_ORDER.get(m.badge, 2),
    }
    rows = [Row(m, '') for m in movies]
    if key in keys:
        k = keys[key]
        rows.sort(key=lambda r: (k(r.movie), order[r.movie.movieid]))
    return rows


def sort_key_for(column):
    """The sort a column asks for, or None to keep the current order."""
    for col in ALL_COLUMNS:
        if col.key == column:
            return col.key if col.sortable else None
    return None


def find_row(rows, movieid, group=None):
    """Index of the movie's row (under `group` when listed several times), or None."""
    first = None
    for i, r in enumerate(rows):
        if r.movie.movieid == movieid:
            if group is None or r.group == group:
                return i
            if first is None:
                first = i
    return first


def preferred_group(movie):
    """Genre a movie is listed under when the list is first grouped by genre."""
    return sorted(movie.genres)[0] if movie.genres else ''


def row_values(row):
    """{property: text} for one list item: short values for plain rows, full ones for the band."""
    m = row.movie
    genres = sorted(m.genres)
    if row.group:
        others = [g for g in genres if g != row.group]
        genre_full = '[CR]'.join([f'[COLOR {AMBER}]{row.group}[/COLOR]'] + others[:FULL_LINES - 1])
        genre_short = row.group
    else:
        genre_full = '[CR]'.join(genres[:FULL_LINES])
        genre_short = genres[0] if genres else ''
    directors = sorted(m.directors)
    return {
        'genre': genre_short,
        'genre_full': genre_full,
        'cast': m.cast[0] if m.cast else '',
        'cast_full': '[CR]'.join(m.cast[:FULL_LINES]),
        'director': directors[0] if directors else '',
        'director_full': '[CR]'.join(directors[:FULL_LINES]),
        'year': str(m.year) if m.year > 0 else '',
        'time': runtime_clock(m.runtime),
        'rating': rating_short(m.mpaa),
        'quality': m.badge,
    }
