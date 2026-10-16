"""List view rows, columns, sorting and Up/Down stepping (pure Python).

Every column sorts. The first Up/Down after focusing a column re-sorts the list by it, keeping
the movie under the band. Genre, Cast and Director hold several values per movie: sorted by
one of them, the list shows a movie once under each of its values (the row's `group`), and
Up/Down first step through the focused movie's own values - the list regrouping around it each
time - before moving on to the next movie.
"""
from collections import namedtuple

Column = namedtuple('Column', 'key label width')

# Title is fixed on the left; the others scroll horizontally (widths in 1080p pixels).
TITLE = Column('title', 32050, 0)
COLUMNS = [
    Column('genre', 32051, 280),
    Column('cast', 32052, 400),
    Column('director', 32053, 380),
    Column('year', 32054, 150),
    Column('time', 32055, 150),
    Column('rating', 32056, 170),
    Column('quality', 32057, 210),
]
ALL_COLUMNS = [TITLE] + COLUMNS
SCROLL_W = 1060                    # visible width right of the title column

AMBER = 'FFF5A01A'
FULL_LINES = 4                     # values shown in the focused row's band

# Kodi's default sort tokens: titles sort as if these leading words were absent.
SORT_TOKENS = ('the ', 'the.', 'the_')

Row = namedtuple('Row', 'movie group')

MPAA_ORDER = ['G', 'PG', 'PG-13', 'R', 'NC-17']
QUALITY_ORDER = {'HDR': 0, 'UHD': 1, '': 2}


def values_of(movie, key):
    """The values a multi-valued column lists for `movie`, in display order."""
    if key == 'genre':
        return sorted(movie.genres)
    if key == 'cast':
        return list(movie.cast[:FULL_LINES])      # the names the band shows
    if key == 'director':
        return sorted(movie.directors)
    return None


MULTI = ('genre', 'cast', 'director')


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


def sort_letter(title):
    """Index of the character a title is sorted by ('The Lion King' -> 4), or None."""
    low = title.lower()
    start = next((len(t) for t in SORT_TOKENS if low.startswith(t)), 0)
    return next((i for i in range(start, len(title)) if title[i].isalnum()), None)


def title_markup(title):
    """Title with its sort letter in amber, as the list shows it in title order."""
    i = sort_letter(title)
    if i is None:
        return title
    return f'{title[:i]}[COLOR {AMBER}]{title[i]}[/COLOR]{title[i + 1:]}'


def _rating_key(movie):
    r = rating_short(movie.mpaa)
    if r in MPAA_ORDER:
        return (0, MPAA_ORDER.index(r), '')
    return (1 if r else 2, 0, r.casefold())


def sort_rows(movies, key):
    """Rows for `movies` (given in title order) sorted by column `key`.

    Ties keep title order and movies without a value go last. Multi-valued columns list a
    movie once per value, grouped by value.
    """
    order = {m.movieid: i for i, m in enumerate(movies)}
    if key in MULTI:
        rows, empty = [], []
        for m in movies:
            vals = values_of(m, key)
            rows += [Row(m, v) for v in vals]
            if not vals:
                empty.append(Row(m, ''))
        rows.sort(key=lambda r: (r.group.casefold(), order[r.movie.movieid]))
        return rows + empty
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


def step(movies, rows, sort, col, index, direction):
    """Up (-1) or Down (+1) with column `col` focused, from row `index` sorted by `sort`.

    Returns (sort, rows, index). A column that is not the current sort re-sorts the list and
    stays on the same movie, selecting its first value (Down) or last value (Up). In a
    multi-valued sort, the move steps through the movie's values before leaving it.
    """
    row = rows[index]
    if col != sort:
        new_rows = sort_rows(movies, col)
        vals = values_of(row.movie, col)
        group = (vals[0] if direction > 0 else vals[-1]) if vals else ('' if col in MULTI else None)
        return col, new_rows, find_row(new_rows, row.movie.movieid, group)
    if sort in MULTI and row.group:
        vals = values_of(row.movie, sort)
        j = vals.index(row.group) + direction if row.group in vals else -1
        if 0 <= j < len(vals):
            return sort, rows, find_row(rows, row.movie.movieid, vals[j])
    return sort, rows, max(0, min(len(rows) - 1, index + direction))


def _cell(row, key, sort):
    """(short, full, marker line) for a multi-valued cell."""
    vals = values_of(row.movie, key)
    if not vals:
        return '', '', ''
    if sort != key or row.group not in vals:
        return vals[0], '[CR]'.join(vals[:FULL_LINES]), ''
    i = vals.index(row.group)
    start = max(0, i - FULL_LINES + 1)
    shown = vals[start:start + FULL_LINES]
    full = '[CR]'.join(f'[COLOR {AMBER}]{v}[/COLOR]' if v == row.group else v for v in shown)
    return row.group, full, str(i - start)


def row_values(row, sort):
    """{property: text} for one list item: short values for plain rows, full ones for the band,
    and `<column>_mark` = line of the selected value (the ▶ marker) in a multi-valued sort."""
    m = row.movie
    out = {
        'label': title_markup(m.title) if sort == 'title' else m.title,
        'year': str(m.year) if m.year > 0 else '',
        'time': runtime_clock(m.runtime),
        'rating': rating_short(m.mpaa),
        'quality': m.badge,
    }
    for key in MULTI:
        out[key], out[f'{key}_full'], out[f'{key}_mark'] = _cell(row, key, sort)
    return out
