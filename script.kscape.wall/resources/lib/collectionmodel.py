"""Collections of movies, albums or TV shows (pure Python): the built-in ones and the user's own.

Built-in collections are worked out from Kodi's library data every time they are shown, so they
follow Kodi without any bookkeeping of their own:

  New     added in the last `days` days (default 30), newest first; for a show, when its
          latest episode was added
  Paused  movies: a saved resume point and not watched; shows: an episode with a resume point
          (Kodi's in-progress shows). Most recently played first. Albums have none: Kodi keeps
          no resume point for music.
  Played  movies: watched (playcount > 0); albums: any song played (Kodi's last-played date;
          its album play count waits for every song); shows: any episode watched. Most
          recently played first.

Custom collections are named, ordered lists kept in a small JSON file per library in the
add-on's profile folder. Each item is stored by a key that survives a library rebuild that
renumbers ids (member_key): a movie or show by its file or folder, as Kodi's favourites store
movies; an album by artist and title. With duplicate movie copies shown once, any copy counts.
"""
import json
import os
import re
from datetime import datetime, timedelta

BUILTIN = ('new', 'paused', 'played')
SPECIAL = ('scenes', 'demos')        # built in too, but listing scenes and Demo Scripts (scenes.py)
BUILTINS = {'movies': BUILTIN + SPECIAL, 'music': ('new', 'played'), 'tv': BUILTIN + SPECIAL}


def is_builtin(cid):
    """Built-in collections cannot be renamed, deleted or filled by hand."""
    return cid in BUILTIN or cid in SPECIAL
DEFAULT_NEW_DAYS = 30
NEW_DAYS_CHOICES = (7, 14, 30, 60, 90, 180)
DATE_RE = re.compile(r'(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?')
MONTHS = ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
          'October', 'November', 'December')


def parse_date(text):
    """Kodi's 'YYYY-MM-DD HH:MM:SS' (or just the date) as a datetime, or None.

    Parsed by hand: datetime.strptime fails on background threads in Kodi's embedded Python
    (its lazy import of _strptime), which is where library changes are handled."""
    m = DATE_RE.match((text or '').strip())
    if not m:
        return None
    try:
        return datetime(*(int(g) for g in m.groups(default='0')))
    except ValueError:
        return None


def new_movies(movies, days=DEFAULT_NEW_DAYS, now=None):
    now = now or datetime.now()
    since = now - timedelta(days=days)
    dated = [(parse_date(m.dateadded), m) for m in movies]
    recent = [(d, m) for d, m in dated if d is not None and d >= since]
    recent.sort(key=lambda t: (t[0], t[1].key), reverse=True)
    return [m for _, m in recent]


def _by_last_played(movies):
    return sorted(movies, key=lambda m: (parse_date(m.lastplayed) or datetime.min, m.key), reverse=True)


def _paused(item):
    if hasattr(item, 'inprogress'):                    # TV show
        return item.inprogress
    return getattr(item, 'resume_position', 0) > 0 and item.playcount == 0


def _played(item):
    if hasattr(item, 'watched'):                       # TV show: any episode watched
        return item.watched > 0 or item.playcount > 0
    if hasattr(item, 'albumid'):                       # album: any song played (Kodi counts the
        return item.playcount > 0 or bool(item.lastplayed)   # album only once every song is)
    return item.playcount > 0


def paused_movies(movies):
    return _by_last_played(m for m in movies if _paused(m))


def played_movies(movies):
    return _by_last_played(m for m in movies if _played(m))


def builtin_movies(cid, movies, days=DEFAULT_NEW_DAYS, now=None):
    """The built-in collection `cid` of `movies` (movies, albums or shows)."""
    if cid == 'new':
        return new_movies(movies, days, now)
    if cid == 'paused':
        return paused_movies(movies)
    return played_movies(movies)


def _clock(d):
    h = d.hour % 12 or 12
    return f"{h}:{d.minute:02d} {'am' if d.hour < 12 else 'pm'}"


def _day(d, now):
    text = f'{MONTHS[d.month - 1]} {d.day}'
    return text if d.year == now.year else f'{text}, {d.year}'


def describe(cid, movie, tr=None, now=None):
    """The line under an item's title in the collections view: when it was added, paused or
    played, from Kodi's dates; for custom collections the artist and year (albums) or the
    year. `tr` maps the format ids below to their (localised) text; English by default."""
    now = now or datetime.now()
    text = tr or {32161: 'Added on {}', 32162: 'Paused on {} at {}', 32163: 'Played on {}'}.get
    if cid == 'new':
        d = parse_date(movie.dateadded)
        return text(32161).format(_day(d, now)) if d else ''
    if cid == 'paused':
        d = parse_date(movie.lastplayed)
        return text(32162).format(_day(d, now), _clock(d)) if d else ''
    if cid == 'played':
        d = parse_date(movie.lastplayed)
        return text(32163).format(_day(d, now)) if d else ''
    parts = [getattr(movie, 'artist', ''), str(movie.year) if movie.year else '']
    return '  ·  '.join(p for p in parts if p)


def member_key(item):
    """What a custom collection stores for `item`: a movie's file, a show's folder (or title and
    year), an album's artist and title."""
    if hasattr(item, 'albumid'):
        return f'album://{item.artist}/{item.title}'
    if getattr(item, 'file', ''):
        return item.file
    return f'title://{item.title}/{item.year}'


def title_key(movie):
    """Duplicate copies of one film share this (model.merge_duplicates): the same TMDB / IMDb id,
    title, year and edition."""
    from .model import _title_key
    return _title_key(movie)


def resolve(keys, library, shown):
    """The items a custom collection holds, in its order, as (item, stored key) pairs: stored
    keys looked up in `library` (every copy), each mapped to the copy `shown` on screen (merged
    duplicate movies), once each."""
    by_file = {member_key(m): m for m in library}
    by_title = {}
    for m in shown:
        by_title.setdefault(title_key(m), m)
    shown_keys = {m.key for m in shown}
    out, seen = [], set()
    for f in keys:
        m = by_file.get(f)
        if m is None:
            continue
        rep = m if m.key in shown_keys else by_title.get(title_key(m))
        if rep is not None and rep.key not in seen:
            seen.add(rep.key)
            out.append((rep, f))
    return out


class Store:
    """The user's collections, saved to `path` after every change.

    {'version': 1, 'next': 3, 'collections': [{'id': 'c1', 'name': 'Watch Soon', 'members': [...]}]}
    """

    def __init__(self, path):
        self.path = path
        self.items = []
        self.next = 1
        self.stamp = None
        self.load()

    def _stamp(self):
        try:
            st = os.stat(self.path)
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def load(self):
        self.stamp = self._stamp()
        try:
            with open(self.path) as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        self.items = [{'id': str(c['id']), 'name': str(c.get('name') or ''),
                       'members': list(c.get('members') or c.get('files') or [])}
                      for c in data.get('collections') or [] if c.get('id')]
        self.next = max([int(data.get('next') or 1)] + [int(c['id'][1:]) + 1 for c in self.items
                                                         if c['id'][1:].isdigit()])

    def poll(self):
        """Re-read if another view saved changes. Returns True when it did."""
        if self._stamp() != self.stamp:
            self.load()
            return True
        return False

    def save(self):
        data = {'version': 1, 'next': self.next, 'collections': self.items}
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + '.tmp'
            with open(tmp, 'w') as f:
                json.dump(data, f, indent=1)
            os.replace(tmp, self.path)
        except OSError:
            pass
        self.stamp = self._stamp()

    def get(self, cid):
        return next((c for c in self.items if c['id'] == cid), None)

    def create(self, name):
        cid = f'c{self.next}'
        self.next += 1
        self.items.append({'id': cid, 'name': name, 'members': []})
        self.save()
        return cid

    def rename(self, cid, name):
        c = self.get(cid)
        if c is not None:
            c['name'] = name
            self.save()

    def delete(self, cid):
        self.items = [c for c in self.items if c['id'] != cid]
        self.save()

    def contains(self, cid, keys):
        """Whether the collection holds any of `keys` (member_key of each copy of one item)."""
        c = self.get(cid)
        return c is not None and any(k in c['members'] for k in keys)

    def add(self, cid, key):
        c = self.get(cid)
        if c is not None and key and key not in c['members']:
            c['members'].append(key)
            self.save()

    def remove(self, cid, keys):
        c = self.get(cid)
        if c is not None:
            c['members'] = [k for k in c['members'] if k not in keys]
            self.save()

    def reorder(self, cid, keys):
        """Put the collection in the order of `keys` (what is on screen); stored keys that are
        not on screen (an item missing from the library just now) keep their place at the end."""
        c = self.get(cid)
        if c is None:
            return
        shown = [k for k in keys if k in c['members']]
        c['members'] = shown + [k for k in c['members'] if k not in shown]
        self.save()
