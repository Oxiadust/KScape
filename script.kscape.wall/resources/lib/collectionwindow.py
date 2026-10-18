"""Collections view (WindowXML, script-kscape-collections.xml; -square.xml for albums).

One per library: movies, music (albums) and TV shows. Along the bottom, a tab bar of every
collection: New, Paused and Played (built in, worked out from Kodi's library each time; music
has no Paused) and then the user's own. Above it on the left, the selected collection's titles,
the focused one in a tall blue band with the line saying when it was added, paused or played;
on the right, its poster or cover. While the tab bar has focus the right side previews the
collection instead: its name, how many titles it holds and up to four posters.

  Tab bar      Left/Right choose a collection, Up enters its titles, Select opens it as the
               cover wall (C: as the list view), Back leaves.
  Titles       Up/Down move, Select opens the title (movie info, album, show), Play plays, Down
               past the last title or Back returns to the tab bar.
  C menu       on a tab: open as cover wall or list, New collection…, Rename / Delete (the
               user's own), the New period (New); on a title: favourites, Add to collection…,
               and for the user's own collections Move (Up/Down carry the title, Select or Back
               put it down) and Remove.

Built-in collections follow Kodi: the window listens for the same library notifications as the
wall (a movie or episode watched, a song played, a resume point saved, a scan or clean) and
recomputes them.
"""
import threading

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from . import cache, collectionui, menu, modal, state
from . import collectionmodel as C
from .favourites import Favourites
from .library import rpc
from .listwindow import show_list
from .search import search
from .window import LibraryMonitor, load_library

ADDON = xbmcaddon.Addon('script.kscape.wall')
TABS = 9100
MOVIES = 9200
PREVIEWS = 4
POLL_S = 0.5
FAVOURITES_FILE = xbmcvfs.translatePath('special://profile/favourites.xml')
BACK = (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU)
MENU = (xbmcgui.ACTION_CONTEXT_MENU, xbmcgui.ACTION_SHOW_INFO)
PLAY = (xbmcgui.ACTION_PLAYER_PLAY,)
STEPS = (xbmcgui.ACTION_MOVE_UP, xbmcgui.ACTION_MOVE_DOWN, xbmcgui.ACTION_PAGE_UP,
         xbmcgui.ACTION_PAGE_DOWN)
SIDEWAYS = (xbmcgui.ACTION_MOVE_LEFT, xbmcgui.ACTION_MOVE_RIGHT)
STATE_KEY = 'collection'


def tr(string_id):
    return ADDON.getLocalizedString(string_id)


def count_text(kind, n):
    return tr(kind.s_count_one) if n == 1 else tr(kind.s_count).format(n)


class CollectionsWindow(xbmcgui.WindowXML):
    ready = False
    pending_skin = None              # chosen from the wall's menu; switched to after closing

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self.kind = kwargs['kind']

    # ---- lifecycle -------------------------------------------------------------------------

    def onInit(self):
        if self.ready:
            return
        self.lock = threading.RLock()
        self.closing = False
        self.tabs = self.getControl(TABS)
        self.list = self.getControl(MOVIES)
        self.store = collectionui.store(self.kind)
        self.favs = Favourites(rpc, FAVOURITES_FILE)
        self.favs_seen = self.favs.version
        self.merge = ADDON.getSettingBool('merge_duplicates')
        self.days = collectionui.new_days()
        self.loading = False
        self.reload_again = False
        self.moving = None                       # row index of the movie being moved
        self.setProperty('moving', '')
        self.setProperty('status', tr(32001))
        self.all_movies, _, cached, _ = load_library(self.kind)
        if cached:
            threading.Thread(target=self._refresh_status, daemon=True).start()
        self.setProperty('status', '')
        self.monitor = LibraryMonitor(self.kind, self._start_reload, self._item_changed)
        self.collections = []
        self.state_key = STATE_KEY if self.kind.name == 'movies' else f'{STATE_KEY}_{self.kind.name}'
        self.cid = state.load().get(self.state_key) or 'new'
        self.rows = []                           # (item, stored key or None) of the open collection
        self._fill_tabs()
        self._fill_movies()
        self.setFocusId(TABS)
        self.ready = True
        threading.Thread(target=self._loop, daemon=True).start()
        if cached and cached['stale']:
            self._start_reload()

    def abandon(self):
        """Closed because Home asked for another view (modal.py)."""
        self._close()

    def _close(self):
        if self.moving is not None:
            self._end_move()
        self.closing = True
        state.save(**{self.state_key: self.cid})
        self.close()

    def _loop(self):
        """Follow changes made elsewhere: another view's collections, Kodi's favourites."""
        mon = xbmc.Monitor()
        while not self.closing and not mon.waitForAbort(POLL_S):
            with self.lock:
                if self.closing or self.moving is not None:
                    continue
                if self.store.poll():
                    self._refresh()
                elif self.favs.poll() != self.favs_seen:
                    self.favs_seen = self.favs.version
                    self._refresh()

    # ---- what is shown ---------------------------------------------------------------------

    def _shown(self):
        return self.kind.visible(self.all_movies, self.merge)

    def _members(self, cid, shown=None):
        shown = self._shown() if shown is None else shown
        return collectionui.members(cid, self.store, self.all_movies, shown, self.days)

    def _fill_tabs(self):
        shown = self._shown()
        self.collections = collectionui.all_collections(self.kind, self.store)
        ids = [c[0] for c in self.collections]
        if self.cid not in ids:
            self.cid = 'new'
        items = []
        last_builtin = max(i for i, c in enumerate(self.collections) if c[2])
        for i, (cid, name, builtin) in enumerate(self.collections):
            li = xbmcgui.ListItem(name, offscreen=True)
            li.setProperties({'count': str(len(self._members(cid, shown))), 'builtin': '1' if builtin else '',
                              'divider': '1' if i == last_builtin and i < len(self.collections) - 1 else ''})
            items.append(li)
        self.tabs.reset()
        self.tabs.addItems(items)
        self.tabs.selectItem(ids.index(self.cid))

    def _fill_movies(self, focus_key=None, index=None):
        """List the selected collection's movies and set the heading and the tab bar preview."""
        self.rows = self._members(self.cid)
        builtin = self.cid in C.BUILTIN
        items = [self._item(m) for m, _ in self.rows]
        self.list.reset()
        self.list.addItems(items)
        if focus_key is not None:
            index = next((i for i, (m, _) in enumerate(self.rows) if m.key == focus_key), index)
        if self.rows:
            self.list.selectItem(max(0, min(index or 0, len(self.rows) - 1)))
        name = collectionui.name_of(self.cid, self.store)
        self.setProperty('heading', name)
        self.setProperty('count', count_text(self.kind, len(self.rows)))
        self.setProperty('kindlabel', tr(32156 if builtin else 32157))
        self.setProperty('builtin', '1' if builtin else '')
        self.setProperty('empty', '' if self.rows else self._empty_text())
        for i in range(PREVIEWS):
            self.setProperty(f'preview{i}', self.rows[i][0].poster if i < len(self.rows) else '')
        self.setProperty('previews', str(min(len(self.rows), PREVIEWS)))
        if not self.rows and self.getFocusId() == MOVIES:
            self.setFocusId(TABS)

    def _item(self, movie):
        li = xbmcgui.ListItem(movie.title, offscreen=True)
        li.setProperties({'sub': C.describe(self.cid, movie, tr), 'poster': movie.poster,
                          'badge': movie.badge, 'fav': '1' if self.favs.contains(movie) else ''})
        return li

    def _empty_text(self):
        from .window import collection_empty
        return collection_empty(self.cid, self.days)

    def _refresh(self):
        """Recompute everything (library or collections changed), keeping the tab and movie."""
        row = self._current()
        index = self.list.getSelectedPosition()
        self._fill_tabs()
        self._fill_movies(focus_key=row[0].key if row else None, index=index)

    def _current(self):
        i = self.list.getSelectedPosition()
        return self.rows[i] if 0 <= i < len(self.rows) else None

    def _select_tab(self):
        """After Left/Right on the tab bar: show the newly selected collection."""
        i = self.tabs.getSelectedPosition()
        if 0 <= i < len(self.collections) and self.collections[i][0] != self.cid:
            self.cid = self.collections[i][0]
            self._fill_movies()

    # ---- input -----------------------------------------------------------------------------

    def onAction(self, action):
        if not self.ready:
            return
        aid = action.getId()
        follow = None
        with self.lock:
            focus = self.getFocusId()
            if self.moving is not None:
                if aid in STEPS:
                    self._carry()
                elif aid in BACK or aid in MENU:
                    self._end_move()
                return
            if aid in SIDEWAYS and focus == TABS:
                self._select_tab()
            elif aid in BACK:
                if focus == MOVIES:
                    self.setFocusId(TABS)
                else:
                    self._close()
            elif aid in MENU:
                follow = self._tab_menu() if focus == TABS else self._movie_menu()
            elif aid in PLAY and focus == MOVIES:
                row = self._current()
                if row:
                    follow = ('play', row[0])
        self._follow(follow)

    def onClick(self, control_id):
        if not self.ready:
            return
        if self.moving is not None:
            with self.lock:
                self._end_move()
            return
        if control_id == TABS:
            self._select_tab()
            self._follow(('open', 'wall'))
        elif control_id == MOVIES:
            row = self._current()
            if row:
                self._follow(('info', row[0]))

    def _follow(self, follow):
        """Actions that open other windows, run outside the lock."""
        if not follow:
            return
        what, arg = follow
        if what == 'play':
            self.kind.play(arg)
        elif what == 'info':
            if self.kind.activate(arg, self.favs) == 'search':
                self._search()
        elif what == 'open':
            self._open(arg)
        elif what == 'search':
            self._search()
        with self.lock:
            self._refresh()

    def _open(self, view):
        """The selected collection as the cover wall (or the list view), as Home opens a library."""
        if view == 'list':
            shown = self._shown()
            rows = self.rows
            row = self._current()
            show_list(self.kind, [m for m, _ in rows], row[0].key if row else None, self.favs, library=shown,
                      store=self.store, collection=self.cid if self.cid not in C.BUILTIN else None)
            return
        from .window import open_wall
        skin = open_wall(self.kind, view='wall', collection=self.cid)
        if skin:
            self.pending_skin = skin
            self._close()

    def _search(self):
        query = menu.ask_search(self.kind)
        if query:
            library = self._shown()
            show_list(self.kind, search(library, query), None, self.favs, query=query, library=library,
                      store=self.store)

    # ---- menus -----------------------------------------------------------------------------

    def _tab_menu(self):
        entries = [('wall', tr(32167)), ('list', tr(32168)), ('create', tr(32158))]
        if self.cid not in C.BUILTIN:
            entries += [('rename', tr(32159)), ('delete', tr(32160))]
        if self.cid == 'new':
            entries.append(('days', tr(32173).format(self.days)))
        choice = menu.show(None, None, entries)
        if choice in ('wall', 'list'):
            return ('open', choice)
        if choice == 'search':
            return ('search', None)
        if choice == 'create':
            cid = collectionui.create(self.store)
            if cid:
                self.cid = cid
                self._refresh()
        elif choice == 'rename':
            name = collectionui.ask_name(collectionui.name_of(self.cid, self.store))
            if name:
                self.store.rename(self.cid, name)
                self._refresh()
        elif choice == 'delete':
            name = collectionui.name_of(self.cid, self.store)
            if xbmcgui.Dialog().yesno(tr(32170).format(name), tr(32171)):
                i = [c[0] for c in self.collections].index(self.cid)
                self.store.delete(self.cid)
                self.cid = self.collections[i - 1][0]           # the tab to its left
                self._refresh()
        elif choice == 'days':
            self._choose_days()
        return None

    def _choose_days(self):
        options = [tr(32174).format(d) for d in C.NEW_DAYS_CHOICES]
        pre = C.NEW_DAYS_CHOICES.index(self.days) if self.days in C.NEW_DAYS_CHOICES else -1
        i = xbmcgui.Dialog().select(tr(32181), options, preselect=pre)
        if i >= 0:
            self.days = C.NEW_DAYS_CHOICES[i]
            ADDON.setSettingInt('new_days', self.days)
            self._refresh()

    def _movie_menu(self):
        row = self._current()
        if not row:
            return None
        movie = row[0]
        entries = [('collect', tr(32164))]
        custom = self.cid not in C.BUILTIN
        if custom:
            entries += [('move', tr(32166)), ('uncollect', tr(32165).format(collectionui.name_of(self.cid, self.store)))]
        choice = menu.show(movie, self.favs, entries)
        if choice == 'favourite':
            self.favs.toggle(movie)
            self.favs_seen = self.favs.version
            self._refresh()
        elif choice == 'search':
            return ('search', None)
        elif choice == 'collect':
            if collectionui.choose(movie, self._files(movie), self.store):
                self._refresh()
        elif choice == 'move':
            self._start_move()
        elif choice == 'uncollect':
            self.store.remove(self.cid, self._files(movie))
            self._refresh()
        return None

    def _files(self, movie):
        """Member keys of every library copy of `movie` (one cover may stand for duplicates)."""
        if not (self.kind.merges and self.merge):
            return collectionui.keys_of([movie])
        key = C.title_key(movie)
        return collectionui.keys_of([m for m in self.all_movies if C.title_key(m) == key] or [movie])

    # ---- moving a movie within a custom collection ----------------------------------------------

    def _start_move(self):
        self.moving = self.list.getSelectedPosition()
        self.setProperty('moving', '1')

    def _carry(self):
        """Kodi has already moved the list; bring the carried movie along to the new row."""
        new = self.list.getSelectedPosition()
        old = self.moving
        if new == old or not (0 <= new < len(self.rows)):
            return
        row = self.rows.pop(old)
        self.rows.insert(new, row)
        lo, hi = min(old, new), max(old, new)
        for i in range(lo, hi + 1):
            src = self._item(self.rows[i][0])
            li = self.list.getListItem(i)
            li.setLabel(src.getLabel())
            for key in ('sub', 'poster', 'badge', 'fav'):
                li.setProperty(key, src.getProperty(key))
        self.moving = new

    def _end_move(self):
        self.moving = None
        self.setProperty('moving', '')
        self.store.reorder(self.cid, [f for _, f in self.rows if f])

    # ---- library changes -------------------------------------------------------------------

    def _refresh_status(self):
        """The cache may predate the latest plays: bring play state and dates up to date."""
        from dataclasses import replace
        from .library import fetch_status
        status = fetch_status(self.kind.name)
        with self.lock:
            if self.closing:
                return
            self.all_movies = [replace(m, **status[m.key]) if m.key in status else m for m in self.all_movies]
            if self.moving is None:
                self._refresh()

    def _item_changed(self, key):
        threading.Thread(target=self._refresh_item, args=(key,), daemon=True).start()

    def _refresh_item(self, key):
        item = self.kind.fetch_one(key)
        with self.lock:
            if self.closing:
                return
            current = next((m for m in self.all_movies if m.key == key), None)
            if item is None or current is None:
                self._start_reload()
                return
            if self.kind.has_extra:
                item = self.kind.with_extra(item, {key: current.cast})
            self.all_movies = [item if m.key == key else m for m in self.all_movies]
            if self.moving is None:
                self._refresh()

    def _start_reload(self):
        if self.loading:
            self.reload_again = True
            return
        self.loading = True
        threading.Thread(target=self._reload_worker, daemon=True).start()

    def _reload_worker(self):
        while True:
            self.reload_again = False
            total = self.kind.total()
            items = self.kind.fetch_all() if total else []
            if not self.reload_again:
                break
        with self.lock:
            self.loading = False
            if self.closing:
                return
            cast = {m.key: m.cast for m in self.all_movies} if self.kind.has_extra else {}
            self.all_movies = [self.kind.with_extra(m, cast) for m in items] if cast else items
            if self.moving is None:
                self._refresh()
        if items:
            cache.save(total, [m.to_cache() for m in self.all_movies], False, self.kind.name)


def show_collections(kind):
    """Run the Collections view. Returns the skin the user chose to switch to, if any."""
    menu.wait_for_dialogs()
    window = CollectionsWindow(kind.collections_xml, ADDON.getAddonInfo('path'), 'Default', '1080i', kind=kind)
    modal.run(window)
    skin = window.pending_skin
    del window
    return skin
