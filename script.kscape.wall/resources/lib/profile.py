"""Profile screens: a person, an artist, an episode, a song, a title's cast and crew, a Details list.

All of them are the album / TV show screen's panel (script-kscape-browse.xml): artwork and a menu
on the left, a few facts and a text on the right, and a list under them. A `Profile` says what to
put in it and what each menu entry and row does; ProfileDialog shows it. Like the other info
screens the dialog only reports what was chosen - ('movie', id), ('album', id), ('explore',
filter), ('episode', id, resume)... - and whoever opened it acts on that once it is closed.
"""
import xbmcaddon
import xbmcgui

from . import actions as A
from . import explore as E
from . import library as lib
from . import kodidb
from . import metadata as MD
from . import modal, people
from . import s as S
from .browse import ENTRIES, BrowseDialog

ADDON = xbmcaddon.Addon('script.kscape.wall')
tr = ADDON.getLocalizedString
BIO_LINES = 5


class Profile:
    """What a profile screen shows. `rows` are (label, label2, thumb, properties); `targets` has
    one entry per row (None: the row does nothing). on_menu(dialog, key) and on_row(dialog,
    target) return None to stay, 'refill' to redraw, or a choice to close with."""

    def __init__(self, title, art='', shape='poster', summary='', plot='', heading='', menu=None,
                 rows=None, targets=None, on_menu=None, on_row=None, focus_rows=True):
        self.title, self.art, self.shape = title, art, shape
        self.summary, self.plot, self.heading = summary, plot, heading
        self.menu = menu or [('return', tr(32066), '')]
        self.rows = rows or []
        self.targets = targets or [None] * len(self.rows)
        self.on_menu = on_menu or (lambda dialog, key: None)
        self.on_row = on_row or (lambda dialog, target: None)
        self.focus_rows = focus_rows
        self.dialog = None
        self.select = 'return'
        self.plot_lines = 4


class ProfileDialog(BrowseDialog):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, item=None, favs=None)
        self.profile = kwargs['profile']
        self.closed = False

    def start(self):
        self.profile.dialog = self
        self.refill(first=True)

    def refill(self, first=False):
        p = self.profile
        if self.closed:
            return
        self._header(p.title, p.art, p.shape, p.summary, p.plot, p.heading, plot_lines=p.plot_lines,
                     menu_rows=len(p.menu))
        keep = self.menu.getSelectedPosition() if not first else 0
        self._fill_menu(p.menu, p.select if first else p.menu[max(0, min(keep, len(p.menu) - 1))][0])
        row = 0 if first else max(0, self.entries.getSelectedPosition())
        self._fill_entries(p.rows, row)
        if first:
            self.setFocusId(ENTRIES if p.rows and p.focus_rows and any(p.targets) else 100)

    def _handle(self, result):
        if result == 'refill':
            self.refill()
        elif result is not None:
            self.finish(result)

    def on_menu(self, key):
        if key == 'return':
            self.finish(None)
        else:
            self._handle(self.profile.on_menu(self, key))

    def on_entry(self, index):
        targets = self.profile.targets
        if 0 <= index < len(targets) and targets[index] is not None:
            self._handle(self.profile.on_row(self, targets[index]))

    def onAction(self, action):
        aid = action.getId()
        if aid in (xbmcgui.ACTION_CONTEXT_MENU,):
            return                                   # nothing to add to favourites here
        super().onAction(action)

    def finish(self, choice):
        self.closed = True
        super().finish(choice)

    def back(self):
        self.closed = True
        return False


def run(profile):
    """Show a profile; returns what the user chose (see the module text), or None."""
    dialog = ProfileDialog('script-kscape-browse.xml', ADDON.getAddonInfo('path'), 'Default', '1080i',
                           profile=profile)
    modal.run(dialog)
    choice = dialog.choice
    dialog.closed = True
    del dialog
    return choice


# ---- Details and Cast & Crew ------------------------------------------------------------------

def details(title, art, shape, rows, heading=None):
    """A page of facts: [(label id, value)] as rows of a label and its value."""
    items = [(tr(label), '', '', {'detail': value}) for label, value in rows]
    if not items:
        items = [(tr(S.P_NO_DETAILS), '', '', {})]
    return Profile(title, art, shape, heading=heading or tr(S.H_DETAILS), rows=items, focus_rows=False)


def cast(title, art, shape, d, on_person):
    """Directors, writers and cast with portraits; Select opens the person's profile.
    `on_person(row)` shows it and returns what it chose."""
    persons = people.cast_rows(d, tr)
    rows = [(r['name'], '', r['thumb'], {'detail': people.person_summary(r, tr)}) for r in persons]
    if not rows:
        rows = [(tr(S.P_NO_CAST), '', '', {})]
    p = Profile(title, art, shape, heading=tr(S.CAST), rows=rows, targets=persons or [None],
                on_row=lambda dialog, row: on_person(row))
    return p


# ---- a person ---------------------------------------------------------------------------------

def person(row, wall=True):
    """The profile of one cast or crew member (a row of people.cast_rows): portrait, role,
    biography, the movies of theirs in the library (Select opens one) and, with a TMDB key, their
    filmography. Menu: show them on the wall (Explore by that person)."""
    name = row['name']
    p = Profile(name, row.get('thumb') or '', 'poster', summary=people.person_summary(row, tr),
                heading=tr(S.H_IN_LIBRARY))
    p.plot_lines = BIO_LINES
    movies = lib.movies_of(name)
    cat = 'director' if row.get('department') == 'Directing' else 'actor'
    count = (tr(S.P_MOVIES_ONE) if len(movies) == 1 else tr(S.P_MOVIES_N).format(len(movies))) if movies else ''

    def build(meta=None):
        meta = meta or {}
        life = people.life_line(meta, tr)
        facts = [f for f in (people.person_summary(row, tr), count, life) if f]
        p.summary = ' · '.join(facts[:2]) + (f'\n{facts[2]}' if len(facts) > 2 else '')
        if meta.get('image') and not p.art:
            p.art = meta['image']
        if meta.get('biography'):
            p.plot = meta['biography']
        elif not MD.tmdb_key():
            p.plot = tr(S.P_NO_BIO)
        rows, targets = [], []
        for m in movies:
            art = m.get('art') or {}
            rows.append((m.get('title') or '', str(m['year']) if m.get('year') else '',
                         art.get('poster') or art.get('thumb') or '',
                         {'unwatched': '' if m.get('playcount') else '1'}))
            targets.append(('movie', int(m['movieid'])))
        if not movies:
            rows.append((tr(S.P_NONE_IN_LIBRARY), '', '', {}))
            targets.append(None)
        owned = {(m.get('title') or '').casefold() for m in movies}
        extra = [f for f in meta.get('filmography') or [] if f['title'].casefold() not in owned]
        if extra:
            rows.append((tr(S.H_FILMOGRAPHY), '', '', {}))
            targets.append(None)
            for f in extra[:40]:
                rows.append((f['title'], f['year'], '', {'detail': f['role']}))
                targets.append(None)
        p.rows, p.targets = rows, targets
        p.menu = [('return', tr(32066), '')]
        if movies and wall:
            p.menu.append(('wall', tr(S.SHOW_WALL), str(len(movies))))

    build()
    if MD.tmdb_key():
        p.plot = tr(S.P_LOOKING_UP)

    def found(meta):
        build(meta)
        if p.dialog:
            p.dialog.refill()

    def on_menu(dialog, key):
        if key == 'wall':
            return ('explore', E.Filter(cat, name))
        return None

    def on_row(dialog, target):
        return target

    p.on_menu, p.on_row = on_menu, on_row
    MD.person(name, row.get('department') or '', found)
    return p


def show_person(row, wall=True):
    """Open a person's profile; returns ('movie', id), ('explore', filter) or None. `wall` offers
    to show the person on the movie wall (only where a movie wall can follow)."""
    return run(person(row, wall))


def show_person_here(row):
    return show_person(row, wall=False)


# ---- music: artist, album details, song -------------------------------------------------------

def _album_row(a):
    art = a.get('art') or {}
    return (a.get('title') or '', str(a['year']) if a.get('year') else '', art.get('thumb') or '', {})


def artist(artistid):
    """An artist's screen: portrait, biography, life facts, discography. Select an album to open
    it. Menu: Play, Details, Choose Art."""
    d = lib.fetch_artist(artistid)
    if not d:
        return None
    albums = lib.artist_albums(artistid)
    songs = lib.artist_songs(artistid)
    art = (d.get('art') or {}).get('thumb') or d.get('thumbnail') or ''
    count = (tr(S.P_ALBUMS_ONE) if len(albums) == 1 else tr(S.P_ALBUMS_N).format(len(albums))) if albums else ''
    songline = (tr(S.P_SONGS_ONE) if len(songs) == 1 else tr(S.P_SONGS_N).format(len(songs))) if songs else ''
    summary = ' · '.join(f for f in (people.artist_summary(d, tr), ' · '.join(x for x in (count, songline) if x)) if f)
    rows = [_album_row(a) for a in albums]
    targets = [('album', int(a['albumid'])) for a in albums]
    owned = {(a.get('title') or '').casefold() for a in albums}
    # What the artist's scraper listed beyond the library (Kodi keeps it with the artist).
    others = [(t, y) for t, y in kodidb.query('MyMusic', 'select strAlbum, strYear from discography '
                                                         'where idArtist = ? order by strYear', (artistid,))
              if (t or '').casefold() not in owned]
    for title, year in others:
        rows.append((title or '', year or '', '', {'detail': ''}))
        targets.append(None)
    p = Profile(d.get('artist') or d.get('label') or '', art, 'square', summary=summary,
                plot=(d.get('description') or '').strip(), heading=tr(S.H_DISCOGRAPHY),
                rows=rows, targets=targets)
    p.plot_lines = BIO_LINES
    p.focus_rows = bool(albums)
    p.menu = [('return', tr(32066), '')]
    if songs:
        p.menu += [('play', tr(S.PLAY_ALL), str(len(songs))), ('queue', tr(S.QUEUE), '')]
    p.menu += [('details', tr(S.DETAILS), ''), ('art', tr(S.CHOOSE_ART), '')]

    def on_menu(dialog, key):
        if key == 'play':
            return ('artist-play', artistid)
        if key == 'queue':
            lib.rpc('Playlist.Add', {'playlistid': lib.MUSIC_PLAYLIST, 'item': {'artistid': artistid}})
            return None
        if key == 'details':
            run(details(p.title, art, 'square', people.artist_rows(d, tr)))
            return None
        if key == 'art':
            if A.choose_art('artist', artistid, p.title):
                fresh = lib.fetch_artist(artistid)
                p.art = (fresh.get('art') or {}).get('thumb') or fresh.get('thumbnail') or ''
                return 'refill'
        return None

    p.on_menu = on_menu
    p.on_row = lambda dialog, target: target
    return p


def show_artist(artistid):
    """Returns ('album', albumid), ('artist-play', artistid) or None."""
    p = artist(artistid)
    return run(p) if p else None


def song(songid):
    """A song's screen: every credit and the file's audio facts. Menu: Play, queue, Play Next."""
    d = lib.fetch_song_details(songid)
    if not d:
        return None
    art = (d.get('art') or {}).get('thumb') or (d.get('art') or {}).get('album.thumb') or ''
    rows = people.song_rows(d, tr)
    items = [(tr(label), '', '', {'detail': value}) for label, value in rows]
    p = Profile(d.get('title') or d.get('label') or '', art, 'square',
                summary=' · '.join(x for x in (' / '.join(d.get('artist') or ()), d.get('album') or '') if x),
                heading=tr(S.INFO), rows=items, focus_rows=False)
    p.menu = [('return', tr(32066), ''), ('play', tr(S.PLAY), ''), ('queue', tr(S.QUEUE), ''),
              ('next', tr(S.PLAY_NEXT), ''), ('rate', tr(S.RATE), '')]
    artist_ids = d.get('artistid') or []
    if artist_ids:
        p.menu.append(('artist', tr(S.ARTIST), ''))

    def on_menu(dialog, key):
        if key == 'play':
            return ('song-play', songid)
        if key == 'queue':
            A.queue_songs([songid])
            return None
        if key == 'next':
            A.queue_songs([songid], play_next=True)
            return None
        if key == 'rate':
            A.rate('song', songid, d.get('userrating'), p.title)
            return None
        if key == 'artist':
            return show_artist(int(artist_ids[0]))
        return None

    p.on_menu = on_menu
    return p


def show_song(songid):
    p = song(songid)
    return run(p) if p else None


# ---- an episode -------------------------------------------------------------------------------

def episode(episodeid):
    """An episode's screen: still, plot, air date and runtime, director / writer / guest cast and
    technical details. Menu: Play, Cast & Crew, Details, Choose Art, Refresh, watched state."""
    d = lib.fetch_episode_details(episodeid)
    if not d:
        return None
    code = f'S{d.get("season", 0):02d}E{d.get("episode", 0):02d}'
    art = (d.get('art') or {}).get('thumb') or ''
    title = f'{d.get("showtitle") or ""} · {code} · {d.get("title") or ""}'.strip(' ·')
    facts = [d.get('firstaired') or '', info_runtime(d), ', '.join(d.get('director') or ())]
    p = Profile(title, art, 'square', summary=' · '.join(f for f in facts if f), plot=d.get('plot') or '',
                heading=tr(S.H_CAST))
    p.plot_lines = BIO_LINES
    people_rows = people.cast_rows(d, tr)
    p.rows = [(r['name'], '', r['thumb'], {'detail': people.person_summary(r, tr)}) for r in people_rows]
    p.targets = people_rows
    p.menu = [('return', tr(32066), ''), ('play', tr(S.PLAY), ''), ('details', tr(S.DETAILS), ''),
              ('watched', tr(S.MARK_UNWATCHED if d.get('playcount') else S.MARK_WATCHED), ''),
              ('rate', tr(S.RATE), ''), ('art', tr(S.CHOOSE_ART), ''), ('refresh', tr(S.REFRESH), '')]
    p.focus_rows = bool(people_rows)

    def on_menu(dialog, key):
        if key == 'play':
            resume = (d.get('resume') or {}).get('position') or 0
            return ('episode', episodeid, bool(resume))
        if key == 'details':
            run(details(title, art, 'square', people.episode_rows(d, tr, MD.language_name)))
        elif key == 'watched':
            A.set_watched('episode', episodeid, not d.get('playcount'))
            d['playcount'] = 0 if d.get('playcount') else 1
            p.menu[3] = ('watched', tr(S.MARK_UNWATCHED if d['playcount'] else S.MARK_WATCHED), '')
            return 'refill'
        elif key == 'rate':
            A.rate('episode', episodeid, d.get('userrating'), d.get('title') or '')
        elif key == 'art':
            if A.choose_art('episode', episodeid, d.get('title') or ''):
                p.art = (lib.fetch_episode_details(episodeid).get('art') or {}).get('thumb') or ''
                return 'refill'
        elif key == 'refresh':
            if A.refresh('episode', episodeid, d.get('title') or ''):
                fresh = lib.fetch_episode_details(episodeid)
                if fresh:
                    d.update(fresh)
                    p.plot = d.get('plot') or ''
                    return 'refill'
        return None

    p.on_menu = on_menu
    p.on_row = lambda dialog, row: show_person(row, wall=False)
    return p


def info_runtime(d):
    from . import info
    return info.runtime_words(d.get('runtime'), tr)


def show_episode(episodeid):
    """Returns ('episode', id, resume) to play, ('movie', id), ('explore', filter) or None."""
    p = episode(episodeid)
    return run(p) if p else None
