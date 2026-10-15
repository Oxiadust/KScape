"""List view: the library as a table with a fixed blue band on the focused movie (WindowXML).

Up/Down move through movies (Kodi's fixedlist scrolls them under the band). Left/Right move
between columns; the first Up/Down in a newly focused column re-sorts the list by it, and in
Genre, Cast or Director, Up/Down then step through the movie's values first (listmodel.step).
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

STEPS = {xbmcgui.ACTION_MOVE_UP: -1, xbmcgui.ACTION_MOVE_DOWN: 1}
PAGING = (xbmcgui.ACTION_PAGE_UP, xbmcgui.ACTION_PAGE_DOWN, xbmcgui.ACTION_FIRST_PAGE,
          xbmcgui.ACTION_LAST_PAGE)
KEEP_SORTS = 3                   # built item lists kept for instant re-sorting
JUMP_S = 0.25                    # list dimmed while it scrolls to a far row (see the XML)
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
        self.jumped = 0.0
        self.built = {}                          # sort -> ListItems for self.rows, recent last
        self.prebuilt = None                     # (sort, ListItems) from the background thread
        self.prebuilder = None
        _set('col', self.col)
        _set('off', 0)
        _set('settled', '')
        _set('jump', '')
        t0 = time.perf_counter()
        self.rows = L.sort_rows(self.movies, self.sort)
        start = L.find_row(self.rows, self.start_id) if self.start_id is not None else None
        self._fill(start or 0)
        xbmc.log(f'kscape.list: {len(self.rows)} rows in {1000 * (time.perf_counter() - t0):.0f} ms',
                 xbmc.LOGINFO)
        self.setFocusId(LIST)
        self.ready = True
        threading.Thread(target=self._settle_loop, daemon=True).start()
        self.prebuilder = threading.Thread(target=self._prebuild, args=('genre',), daemon=True)
        self.prebuilder.start()

    @staticmethod
    def _build(rows, sort):
        """ListItems for `rows`: the slow part of re-sorting (Kodi's API costs ~0.2 ms per item
        and a genre sort of 5,000 movies is ~15,000 rows), so it is one call per item."""
        items = []
        for row in rows:
            values = L.row_values(row, sort)
            li = xbmcgui.ListItem(values.pop('label'), offscreen=True)
            values['poster'] = row.movie.poster
            li.setProperties({k: v for k, v in values.items() if v})
            items.append(li)
        return items

    def _prebuild(self, sort):
        """Build a likely next sort in the background while the list is browsed."""
        self.prebuilt = (sort, self._build(L.sort_rows(self.movies, sort), sort))

    def _items(self):
        items = self.built.pop(self.sort, None)
        if items is None and self.prebuilder and self.prebuilder.is_alive() and self.sort == 'genre':
            self.prebuilder.join()                    # nearly done: cheaper than starting over
        if items is None and self.prebuilt and self.prebuilt[0] == self.sort:
            items, self.prebuilt = self.prebuilt[1], None
        if items is None:
            items = self._build(self.rows, self.sort)
        self.built[self.sort] = items
        while len(self.built) > KEEP_SORTS:
            del self.built[next(iter(self.built))]
        return items

    def _fill(self, index):
        t0 = time.perf_counter()
        items = self._items()
        t1 = time.perf_counter()
        self.list.reset()
        self.list.addItems(items)
        self.list.selectItem(index)
        self.cur = index
        xbmc.log(f'kscape.list: {len(items)} rows sorted by {self.sort}: items '
                 f'{1000 * (t1 - t0):.0f} ms, list {1000 * (time.perf_counter() - t1):.0f} ms', xbmc.LOGINFO)

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
            if aid in STEPS:
                self._step(STEPS[aid])
            elif aid in PAGING:
                self._collapse()
                self.cur = self.list.getSelectedPosition()
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

    def _collapse(self):
        self.moved = time.time()
        if self.settled:
            self.settled = False
            _set('settled', '')

    def _step(self, direction):
        """Up/Down. Kodi has already moved the list one row; that is kept when it is the right
        move, otherwise the list is re-sorted or sent to the movie's next value from here."""
        self._collapse()
        if not self.rows:
            return
        base = min(self.cur, len(self.rows) - 1)
        sort, rows, target = L.step(self.movies, self.rows, self.sort, self.col, base, direction)
        if rows is not self.rows:
            self.sort, self.rows = sort, rows
            self._fill(target)
        elif target == base + direction:
            self.cur = self.list.getSelectedPosition()       # plain move: keep Kodi's scroll
        else:
            if abs(target - self.list.getSelectedPosition()) > 1:
                self.jumped = time.time()
                _set('jump', 1)
            self.list.selectItem(target)
            self.cur = target

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
                if self.jumped and time.time() - self.jumped >= JUMP_S:
                    self.jumped = 0.0
                    _set('jump', '')
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
