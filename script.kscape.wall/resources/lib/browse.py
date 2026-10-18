"""Album and TV show screens: the info-screen panel, with the album's tracks or the show's seasons
and episodes listed on the right (WindowXMLDialog, script-kscape-browse.xml).

  album:   cover, artist / year / genres, review; Return / Play Album; the track list
  TV show: poster, year / network / rating, plot; Return / Play next episode; seasons, then a
           season's episodes (Back steps up from episodes to seasons). Shows with a single season
           open straight on its episodes.

Like the movie info screen, the dialog only reports what was chosen; the caller closes it and
starts playback, so nothing plays underneath an open dialog. The C menu offers Add to / Remove
from Favourites (for the album or show) and Search.
"""
import xbmcaddon
import xbmcgui

from . import info, menu, modal
from . import library as lib

ADDON = xbmcaddon.Addon('script.kscape.wall')
tr = ADDON.getLocalizedString
BACK = (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU)
CONTEXT = (xbmcgui.ACTION_CONTEXT_MENU,)
PLAY = (xbmcgui.ACTION_PLAYER_PLAY,)

MENU, ENTRIES = 100, 300
SUMMARY, PLOT, HEADING = 210, 221, 230
ART_TOP = 88
ART_W = 420
ART_H = {'square': 420, 'poster': 630}
MENU_GAP = 16
# Right-hand column (panel pixels), see the XML.
RIGHT_TOP, RIGHT_BOTTOM = 88, 954
TEXT_W, BODY_PX, LINE_H = 1150, 29, 38
GAP = 22
HEADING_H = 48


def _duration(seconds):
    return info.clock(seconds) if seconds else ''


def _minutes(seconds):
    m = int(round((seconds or 0) / 60.0))
    return tr(32043).format(m) if m > 1 else (tr(32042).format(m) if m == 1 else '')


class BrowseDialog(xbmcgui.WindowXMLDialog):

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self.item = kwargs['item']
        self.favs = kwargs.get('favs')
        self.choice = None

    # ---- shared layout -------------------------------------------------------------------------

    def onInit(self):
        self.menu = self.getControl(MENU)
        self.entries = self.getControl(ENTRIES)
        self._mark_favourite()
        self.start()

    def _mark_favourite(self):
        fav = self.favs is not None and self.favs.contains(self.item)
        self.setProperty('favourite', '1' if fav else '')

    def _header(self, title, art, shape, summary, plot, heading):
        """Fill the panel; the right column is laid out from estimated line counts (as on the
        movie info screen), and the menu sits under the artwork whatever its shape."""
        self.setProperty('title', title)
        self.setProperty('art', art or '')
        self.setProperty('shape', shape)
        self.menu.setPosition(self.menu.getX(), ART_TOP + ART_H[shape] + MENU_GAP)
        y = RIGHT_TOP
        box = self.getControl(SUMMARY)
        if summary:
            lines = min(2, info.estimate_lines(summary, TEXT_W, BODY_PX))
            box.setPosition(box.getX(), y)
            box.setHeight(lines * LINE_H)
            box.setText(summary)
            y += lines * LINE_H + GAP
        box.setVisible(bool(summary))
        box = self.getControl(PLOT)
        if plot:
            lines = min(4, info.estimate_lines(plot, TEXT_W, BODY_PX))
            box.setPosition(box.getX(), y)
            box.setHeight(lines * LINE_H)
            box.setText(plot)
            y += lines * LINE_H + GAP
        box.setVisible(bool(plot))
        head = self.getControl(HEADING)
        head.setLabel(heading)
        head.setPosition(head.getX(), y)
        y += HEADING_H
        self.entries.setPosition(self.entries.getX(), y)
        self.entries.setHeight(RIGHT_BOTTOM - y)

    def _fill_menu(self, items, select):
        self.menu.reset()
        lis = []
        for key, label, label2 in items:
            li = xbmcgui.ListItem(label, label2)
            li.setProperty('action', key)
            lis.append(li)
        self.menu.addItems(lis)
        keys = [k for k, _, _ in items]
        self.menu.selectItem(keys.index(select) if select in keys else 0)

    def _fill_entries(self, rows, select=0):
        """rows: (label, label2, thumb, {property: value})."""
        self.entries.reset()
        lis = []
        for label, label2, thumb, props in rows:
            li = xbmcgui.ListItem(label, label2)
            if thumb:
                li.setArt({'thumb': thumb})
            li.setProperties({k: v for k, v in props.items() if v})
            lis.append(li)
        self.entries.addItems(lis)
        if lis:
            self.entries.selectItem(max(0, min(select, len(lis) - 1)))

    # ---- input ---------------------------------------------------------------------------------

    def onClick(self, control_id):
        if control_id == MENU:
            item = self.menu.getSelectedItem()
            self.on_menu(item.getProperty('action') if item else 'return')
        elif control_id == ENTRIES:
            self.on_entry(self.entries.getSelectedPosition())

    def onAction(self, action):
        aid = action.getId()
        if aid in BACK:
            if not self.back():
                self.choice = None
                self.close()
        elif aid in PLAY:
            self.on_play()
        elif aid in CONTEXT:
            choice = menu.show(self.item, self.favs, [])
            if choice == 'favourite':
                self.favs.toggle(self.item)
                self._mark_favourite()
            elif choice == 'search':
                self.finish(('search',))

    def finish(self, choice):
        self.choice = choice
        self.close()

    # Overridden per screen.
    def start(self):
        pass

    def on_menu(self, key):
        if key == 'return':
            self.finish(None)

    def on_entry(self, index):
        pass

    def on_play(self):
        pass

    def back(self):
        """Step up a level; False when already at the top (the dialog then closes)."""
        return False


class AlbumDialog(BrowseDialog):

    def start(self):
        a = self.item
        self.songs = lib.fetch_songs(a.albumid)
        total = sum(s.get('duration') or 0 for s in self.songs)
        count = tr(32117 if len(self.songs) != 1 else 32118).format(len(self.songs))
        facts = [a.artist, str(a.year) if a.year else '', ', '.join(sorted(a.genres)),
                 f'{count}, {_duration(total)}' if total else count, a.label]
        self._header(a.title, a.poster, 'square', ' · '.join(f for f in facts if f), a.plot, tr(32111))
        self._fill_menu([('return', tr(32066), ''), ('play', tr(32110), '')], 'play')
        rows = []
        discs = len({s.get('disc') or 0 for s in self.songs}) > 1
        for s in self.songs:
            n = s.get('track') or 0
            number = (f'{s.get("disc")}-{n}' if discs else str(n)) if n else ''
            artist = ' / '.join(s.get('artist') or ())
            label = f'{number}.  {s.get("title") or s.get("label") or ""}' if number else (s.get('title') or '')
            props = {'detail': artist if artist and artist != a.artist else ''}
            rows.append((label, _duration(s.get('duration')), '', props))
        self._fill_entries(rows)
        self.setFocusId(MENU)

    def on_menu(self, key):
        if key == 'play' and self.songs:
            self.finish(('play', 0))
        elif key == 'return':
            self.finish(None)

    def on_entry(self, index):
        if 0 <= index < len(self.songs):
            self.finish(('play', index))

    def on_play(self):
        if self.songs:
            focused = self.getFocusId() == ENTRIES
            self.finish(('play', max(0, self.entries.getSelectedPosition()) if focused else 0))


class ShowDialog(BrowseDialog):

    def start(self):
        self.seasons = lib.fetch_seasons(self.item.tvshowid)
        self.season = None                  # season number while its episodes are listed
        self.episodes = []
        self.season_pos = 0
        if len(self.seasons) == 1:
            self.single = True
            self._show_episodes(self.seasons[0])
        else:
            self.single = False
            self._show_seasons()

    def _summary(self):
        t = self.item
        counts = tr(32116).format(t.episodes) if t.episodes != 1 else tr(32119)
        if t.watched:
            counts += ' ' + tr(32120).format(t.watched)
        facts = [str(t.year) if t.year else '', ', '.join(sorted(t.studios)), t.mpaa,
                 ', '.join(sorted(t.genres)), counts]
        return ' · '.join(f for f in facts if f)

    def _next_episode(self):
        """(episode, label) Play should start: the first unwatched episode, or None if the
        show has no episodes."""
        episodes = [e for s in self.seasons for e in lib.fetch_episodes(self.item.tvshowid, s['season'])] \
            if self.season is None else self.episodes
        if not episodes:
            return None
        e = next((e for e in episodes if not e.get('playcount')), episodes[0])
        return e

    def _menu_items(self, nxt):
        items = [('return', tr(32066), '')]
        if nxt:
            resume = (nxt.get('resume') or {}).get('position') or 0
            code = f'S{nxt.get("season", 0):02d}E{nxt.get("episode", 0):02d}'
            items.append(('next', tr(32122 if resume else 32121), code))
        return items

    def _show_seasons(self):
        t = self.item
        self.season = None
        self._header(t.title, t.poster, 'poster', self._summary(), t.plot, tr(32112))
        self.next = self._next_episode()
        self._fill_menu(self._menu_items(self.next), 'return')
        rows = []
        for s in self.seasons:
            n = s.get('season') or 0
            label = s.get('title') or (tr(32114).format(n) if n else tr(32115))
            eps = s.get('episode') or 0
            art = s.get('art') or {}
            unwatched = (s.get('watchedepisodes') or 0) < eps
            rows.append((label, tr(32116).format(eps) if eps != 1 else tr(32119),
                         art.get('poster') or art.get('thumb') or '', {'unwatched': '1' if unwatched else ''}))
        self._fill_entries(rows, self.season_pos)
        self.setFocusId(ENTRIES)

    def _show_episodes(self, season):
        t = self.item
        self.season = season.get('season') or 0
        self.episodes = lib.fetch_episodes(t.tvshowid, self.season)
        art = season.get('art') or {}
        name = season.get('title') or (tr(32114).format(self.season) if self.season else tr(32115))
        self._header(f'{t.title} · {name}', art.get('poster') or t.poster, 'poster', self._summary(),
                     t.plot, tr(32113))
        self.next = self._next_episode()
        self._fill_menu(self._menu_items(self.next), 'return')
        rows = []
        for e in self.episodes:
            n = e.get('episode') or 0
            label = f'{n}.  {e.get("title") or ""}' if n else (e.get('title') or '')
            resume = (e.get('resume') or {}).get('position') or 0
            label2 = tr(32123).format(info.clock(resume)) if resume else _minutes(e.get('runtime'))
            thumb = (e.get('art') or {}).get('thumb') or ''
            rows.append((label, label2, thumb, {'unwatched': '' if e.get('playcount') else '1',
                                                'detail': e.get('firstaired') or ''}))
        first_new = next((i for i, e in enumerate(self.episodes) if not e.get('playcount')), 0)
        self._fill_entries(rows, first_new)
        self.setFocusId(ENTRIES)

    def _play(self, episode):
        resume = (episode.get('resume') or {}).get('position') or 0
        if resume:
            i = xbmcgui.Dialog().select(episode.get('title') or '', [
                tr(32123).format(info.clock(resume)), tr(32124)])
            if i < 0:
                return
            self.finish(('episode', episode['episodeid'], i == 0))
        else:
            self.finish(('episode', episode['episodeid'], False))

    def on_menu(self, key):
        if key == 'next' and self.next:
            self._play(self.next)
        elif key == 'return':
            self.finish(None)

    def on_entry(self, index):
        if self.season is None:
            if 0 <= index < len(self.seasons):
                self.season_pos = index
                self._show_episodes(self.seasons[index])
        elif 0 <= index < len(self.episodes):
            self._play(self.episodes[index])

    def on_play(self):
        if self.season is not None and self.getFocusId() == ENTRIES:
            i = self.entries.getSelectedPosition()
            if 0 <= i < len(self.episodes):
                self._play(self.episodes[i])
                return
        if self.next:
            self._play(self.next)

    def back(self):
        if self.season is not None and not self.single:
            self._show_seasons()
            return True
        return False


def _run(cls, item, favs):
    dialog = cls('script-kscape-browse.xml', ADDON.getAddonInfo('path'), 'Default', '1080i',
                 item=item, favs=favs)
    modal.run(dialog)
    choice = dialog.choice
    del dialog
    return choice


def show_album(album, favs=None):
    """Returns ('play', track index), ('search',) or None."""
    return _run(AlbumDialog, album, favs)


def show_tvshow(show, favs=None):
    """Returns ('episode', episodeid, resume), ('search',) or None."""
    return _run(ShowDialog, show, favs)
