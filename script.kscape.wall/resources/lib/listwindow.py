"""List view: the library as a table with a fixed blue band on the focused movie (WindowXML).

Up/Down move through movies (Kodi's fixedlist scrolls them under the band). Left/Right move
between columns. Moving up or down while a sortable column is focused re-sorts the list by it,
keeping the movie under the band; the genre column lists a movie under each of its genres.
Select opens the info screen; Back returns to the cover wall.

It is a full window, not a dialog, so playback started here takes over the screen and Kodi
returns to the list when it ends.
"""
import threading
import time

import xbmc
import xbmcaddon
import xbmcgui

from . import listmodel as L
from .details import show_details
from .library import play, play_trailer

ADDON = xbmcaddon.Addon('script.kscape.wall')
HOME = xbmcgui.Window(10000)
LIST = 9000
SETTLE_S = 0.45                  # rest before the band shows the poster and full values

VERTICAL = (xbmcgui.ACTION_MOVE_UP, xbmcgui.ACTION_MOVE_DOWN, xbmcgui.ACTION_PAGE_UP,
            xbmcgui.ACTION_PAGE_DOWN, xbmcgui.ACTION_FIRST_PAGE, xbmcgui.ACTION_LAST_PAGE)
BACK = (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU)
MENU = (xbmcgui.ACTION_CONTEXT_MENU, xbmcgui.ACTION_SHOW_INFO)
PLAY = (xbmcgui.ACTION_PLAYER_PLAY,)
KEYS = [c.key for c in L.ALL_COLUMNS]


def _set(name, value):
    HOME.setProperty(f'kscape.list.{name}', str(value))


class ListWindow(xbmcgui.WindowXML):
    ready = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self.movies = kwargs['movies']           # title order
        self.start_id = kwargs.get('focus')
        self.result = 'wall'                     # 'wall', 'exit' or 'skin' once closed
        self.focus_id = self.start_id            # movie under the band when closed

    def onInit(self):
        if self.ready:
            return                               # back from playback or the info screen
        self.lock = threading.RLock()
        self.closing = False
        self.list = self.getControl(LIST)
        self.col = 'title'
        self.sort = 'title'
        self.moved = 0.0
        self.settled = False
        _set('col', self.col)
        _set('off', 0)
        _set('settled', '')
        t0 = time.perf_counter()
        self.rows = L.sort_rows(self.movies, self.sort)
        start = L.find_row(self.rows, self.start_id) if self.start_id is not None else None
        self._fill(start or 0)
        xbmc.log(f'kscape.list: {len(self.rows)} rows in {1000 * (time.perf_counter() - t0):.0f} ms',
                 xbmc.LOGINFO)
        self.setFocusId(LIST)
        self.ready = True
        threading.Thread(target=self._settle_loop, daemon=True).start()

    def _fill(self, index):
        items = []
        for row in self.rows:
            li = xbmcgui.ListItem(row.movie.title, offscreen=True)
            li.setArt({'poster': row.movie.poster})
            li.setProperties(L.row_values(row))
            items.append(li)
        self.list.reset()
        self.list.addItems(items)
        self.list.selectItem(index)

    def _current(self):
        i = self.list.getSelectedPosition()
        return self.rows[i] if 0 <= i < len(self.rows) else None

    def _close(self, result):
        row = self._current()
        if row:
            self.focus_id = row.movie.movieid
        self.result = result
        self.closing = True
        self.close()

    # ---- input -----------------------------------------------------------------------------

    def onAction(self, action):
        aid = action.getId()
        if not self.ready:
            return
        with self.lock:
            if aid in VERTICAL:
                self._moved()
            elif aid in (xbmcgui.ACTION_MOVE_LEFT, xbmcgui.ACTION_MOVE_RIGHT):
                step = -1 if aid == xbmcgui.ACTION_MOVE_LEFT else 1
                i = max(0, min(len(KEYS) - 1, KEYS.index(self.col) + step))
                self.col = KEYS[i]
                _set('col', self.col)
                _set('off', L.scroll_for(self.col))
            elif aid in BACK:
                self._close('wall')
            elif aid in MENU:
                self._menu()
            elif aid in PLAY:
                row = self._current()
                if row:
                    play(row.movie)

    def _moved(self):
        """Kodi has already moved the list; re-sort if the focused column asks for it."""
        self.moved = time.time()
        if self.settled:
            self.settled = False
            _set('settled', '')
        wanted = L.sort_key_for(self.col)
        row = self._current()
        if wanted is None or wanted == self.sort or row is None:
            return
        self.sort = wanted
        self.rows = L.sort_rows(self.movies, wanted)
        group = L.preferred_group(row.movie) if wanted == 'genre' else None
        self._fill(L.find_row(self.rows, row.movie.movieid, group) or 0)

    def onClick(self, control_id):
        if control_id != LIST or not self.ready:
            return
        row = self._current()
        if not row:
            return
        choice, details = show_details(row.movie)
        if choice in ('play', 'resume'):
            play(row.movie, resume=choice == 'resume')
        elif choice == 'trailer' and details and details.get('trailer'):
            play_trailer(details['trailer'])

    def _menu(self):
        items = [('wall', ADDON.getLocalizedString(32070)),
                 ('skin', ADDON.getLocalizedString(32025)),
                 ('exit', ADDON.getLocalizedString(32026))]
        i = xbmcgui.Dialog().select(ADDON.getLocalizedString(32020), [label for _, label in items])
        if i >= 0:
            self._close(items[i][0])

    def _settle_loop(self):
        mon = xbmc.Monitor()
        while not self.closing and not mon.abortRequested():
            time.sleep(0.05)
            with self.lock:
                if not self.settled and time.time() - self.moved >= SETTLE_S:
                    self.settled = True
                    _set('settled', 1)


def show_list(movies, focus):
    """Run the list view. Returns (result, movieid under the band)."""
    window = ListWindow('script-kscape-list.xml', ADDON.getAddonInfo('path'), 'Default', '1080i',
                        movies=movies, focus=focus)
    window.doModal()
    result, focus_id = window.result, window.focus_id
    del window
    return result, focus_id
