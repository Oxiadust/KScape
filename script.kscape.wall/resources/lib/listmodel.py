"""List view rows, columns, sorting and Up/Down stepping (pure Python).

Every column sorts. The first Up/Down after focusing a column re-sorts the list by it, keeping
the movie under the band. Genre, Cast and Director hold several values per movie: sorted by
one of them, the list shows a movie once under each of its values (the row's `group`), and
Up/Down first step through the focused movie's own values - the list regrouping around it each
time - before moving on to the next movie.

The same table serves albums (Artist, Album, Genre, Year) and TV shows; each media kind is a
ListSpec (MOVIES, MUSIC, TV at the end of this module). Functions default to MOVIES.
"""
from collections import namedtuple

Column = namedtuple('Column', 'key label width')

SCROLL_W = 1060                    # visible width right of the title column
AMBER = 'FFF5A01A'
FULL_LINES = 4                     # values shown in the focused row's band

# Kodi's default sort tokens: titles sort as if these leading words were absent.
SORT_TOKENS = ('the ', 'the.', 'the_')

Row = namedtuple('Row', 'movie group')     # `movie` is the row's item: a movie, album or show

MPAA_ORDER = ['G', 'PG', 'PG-13', 'R', 'NC-17']
QUALITY_ORDER = {'HDR': 0, 'UHD': 1, '': 2}


class ListSpec:
    """One media kind's table: the fixed left column, the scrolling columns and how each column
    reads and sorts its items.

    multi:  {key: item -> [values]}  columns listing several values (one row per value when sorted)
    single: {key: item -> text}      one-value columns
    sorts:  {key: item -> sort key}  single columns that sort by something other than list order
    """

    def __init__(self, name, title, columns, multi, single, sorts, title_text, xml, square=False):
        self.name = name
        self.title = title
        self.columns = columns
        self.all_columns = [title] + columns
        self.multi = multi
        self.single = single
        self.sorts = sorts
        self.title_text = title_text
        self.xml = xml
        self.square = square                     # square artwork in the band (album covers)

    def keys(self):
        return [c.key for c in self.all_columns]


def values_of(movie, key, spec=None):
    """The values a multi-valued column lists for an item, in display order (None otherwise)."""
    fn = (spec or MOVIES).multi.get(key)
    return fn(movie) if fn else None


def column_offsets(spec=None):
    """x of each scrolling column inside the scrolling strip."""
    spec = spec or MOVIES
    out, x = {}, 0
    for col in spec.columns:
        out[col.key] = x
        x += col.width
    return out


def scroll_for(key, spec=None):
    """Horizontal scroll that puts the focused column first, without running past the end."""
    spec = spec or MOVIES
    offsets = column_offsets(spec)
    total = sum(c.width for c in spec.columns)
    return max(0, min(offsets.get(key, 0), total - SCROLL_W))


def scroll_stops(spec=None):
    spec = spec or MOVIES
    return sorted({scroll_for(c.key, spec) for c in spec.all_columns})


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


def sort_rows(movies, key, spec=None):
    """Rows for `movies` (given in title order) sorted by column `key`.

    Ties keep title order and items without a value go last. Multi-valued columns list an
    item once per value, grouped by value.
    """
    spec = spec or MOVIES
    order = {m.key: i for i, m in enumerate(movies)}
    if key in spec.multi:
        rows, empty = [], []
        for m in movies:
            vals = spec.multi[key](m)
            rows += [Row(m, v) for v in vals]
            if not vals:
                empty.append(Row(m, ''))
        rows.sort(key=lambda r: (r.group.casefold(), order[r.movie.key]))
        return rows + empty
    rows = [Row(m, '') for m in movies]
    if key in spec.sorts:
        k = spec.sorts[key]
        rows.sort(key=lambda r: (k(r.movie), order[r.movie.key]))
    return rows


def find_row(rows, key, group=None):
    """Index of the item's row (under `group` when listed several times), or None."""
    first = None
    for i, r in enumerate(rows):
        if r.movie.key == key:
            if group is None or r.group == group:
                return i
            if first is None:
                first = i
    return first


def step(movies, rows, sort, col, index, direction, spec=None):
    """Up (-1) or Down (+1) with column `col` focused, from row `index` sorted by `sort`.

    Returns (sort, rows, index). A column that is not the current sort re-sorts the list and
    stays on the same movie, selecting its first value (Down) or last value (Up). In a
    multi-valued sort, the move steps through the movie's values before leaving it.
    """
    spec = spec or MOVIES
    row = rows[index]
    if col != sort:
        new_rows = sort_rows(movies, col, spec)
        vals = values_of(row.movie, col, spec)
        group = (vals[0] if direction > 0 else vals[-1]) if vals else ('' if col in spec.multi else None)
        return col, new_rows, find_row(new_rows, row.movie.key, group)
    if sort in spec.multi and row.group:
        vals = values_of(row.movie, sort, spec)
        j = vals.index(row.group) + direction if row.group in vals else -1
        if 0 <= j < len(vals):
            return sort, rows, find_row(rows, row.movie.key, vals[j])
    return sort, rows, max(0, min(len(rows) - 1, index + direction))


def _cell(row, key, sort, spec):
    """(short, full, marker line) for a multi-valued cell."""
    vals = values_of(row.movie, key, spec)
    if not vals:
        return '', '', ''
    if sort != key or row.group not in vals:
        return vals[0], '[CR]'.join(vals[:FULL_LINES]), ''
    i = vals.index(row.group)
    start = max(0, i - FULL_LINES + 1)
    shown = vals[start:start + FULL_LINES]
    full = '[CR]'.join(f'[COLOR {AMBER}]{v}[/COLOR]' if v == row.group else v for v in shown)
    return row.group, full, str(i - start)


def row_values(row, sort, spec=None):
    """{property: text} for one list item: short values for plain rows, full ones for the band,
    and `<column>_mark` = line of the selected value (the ▶ marker) in a multi-valued sort."""
    spec = spec or MOVIES
    title = spec.title_text(row.movie)
    out = {'label': title_markup(title) if sort == 'title' else title}
    for key, text in spec.single.items():
        out[key] = text(row.movie)
    for key in spec.multi:
        out[key], out[f'{key}_full'], out[f'{key}_mark'] = _cell(row, key, sort, spec)
    return out


# ---- the three media kinds ------------------------------------------------------------------

def _first(values):
    return sorted(values)[0] if values else ''


def _number(n):
    return str(n) if n > 0 else ''


MOVIES = ListSpec(
    'movies',
    title=Column('title', 32050, 0),
    columns=[
        Column('genre', 32051, 280),
        Column('cast', 32052, 400),
        Column('director', 32053, 380),
        Column('year', 32054, 150),
        Column('time', 32055, 150),
        Column('rating', 32056, 170),
        Column('quality', 32057, 210),
    ],
    multi={'genre': lambda m: sorted(m.genres),
           'cast': lambda m: list(m.cast[:FULL_LINES]),      # the names the band shows
           'director': lambda m: sorted(m.directors)},
    single={'year': lambda m: _number(m.year), 'time': lambda m: runtime_clock(m.runtime),
            'rating': lambda m: rating_short(m.mpaa), 'quality': lambda m: m.badge},
    sorts={'year': lambda m: (m.year <= 0, m.year),
           'time': lambda m: (m.runtime <= 0, m.runtime),
           'rating': _rating_key,
           'quality': lambda m: QUALITY_ORDER.get(m.badge, 2)},
    title_text=lambda m: m.title,
    xml='script-kscape-list.xml',
)

MUSIC = ListSpec(
    'music',
    title=Column('title', 32080, 0),                     # Artist (albums list in artist order)
    columns=[
        Column('album', 32081, 560),
        Column('genre', 32051, 320),
        Column('year', 32054, 150),
    ],
    multi={'genre': lambda a: sorted(a.genres)},
    single={'album': lambda a: a.title, 'year': lambda a: _number(a.year)},
    sorts={'album': lambda a: (not a.title, a.title.casefold()),
           'year': lambda a: (a.year <= 0, a.year)},
    title_text=lambda a: a.artist,
    xml='script-kscape-list-music.xml',
    square=True,
)

TV = ListSpec(
    'tv',
    title=Column('title', 32050, 0),
    columns=[
        Column('genre', 32051, 280),
        Column('cast', 32052, 400),
        Column('network', 32082, 300),
        Column('year', 32054, 150),
        Column('seasons', 32083, 170),
        Column('episodes', 32084, 180),
        Column('rating', 32056, 170),
    ],
    multi={'genre': lambda t: sorted(t.genres), 'cast': lambda t: list(t.cast[:FULL_LINES])},
    single={'network': lambda t: _first(t.studios), 'year': lambda t: _number(t.year),
            'seasons': lambda t: _number(t.seasons), 'episodes': lambda t: _number(t.episodes),
            'rating': lambda t: rating_short(t.mpaa)},
    sorts={'network': lambda t: (not t.studios, _first(t.studios).casefold()),
           'year': lambda t: (t.year <= 0, t.year),
           'seasons': lambda t: (t.seasons <= 0, t.seasons),
           'episodes': lambda t: (t.episodes <= 0, t.episodes),
           'rating': _rating_key},
    title_text=lambda t: t.title,
    xml='script-kscape-list-tv.xml',
)

SPECS = {'movies': MOVIES, 'music': MUSIC, 'tv': TV}

# The movie table under its historical names.
TITLE = MOVIES.title
COLUMNS = MOVIES.columns
ALL_COLUMNS = MOVIES.all_columns
MULTI = tuple(MOVIES.multi)
