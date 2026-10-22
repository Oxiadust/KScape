"""List view: the library as a table with a fixed blue band on the focused item (WindowXML).

Up/Down move through items (Kodi's fixedlist scrolls them under the band). Left/Right move
between columns; the first Up/Down in a newly focused column re-sorts the list by it, and in a
multi-valued column (Genre, Cast, Director), Up/Down then step through the item's values first
(listmodel.step). Select does what it does on the wall (kinds.py): the movie info screen, an
album's tracks, a show's seasons. Back returns to the cover wall.

The same window lists search results: then a heading names the search, an empty result says so,
and Back returns to wherever the search started.

Over a movie wall it shares the wall's filters (Explore, C -> Filter…; window.ExploreLink): the
heading names them and how many movies match, and Back retraces them before it leaves. Explore
chosen in a list with no wall of its own (search results, a collection) opens a filtered wall.

It is a full window, not a dialog, so playback started here takes over the screen and Kodi
returns to the list when it ends.
"""
import threading
import time

import xbmc
import xbmcaddon
import xbmcgui

from . import listmodel as L
from . import collectionui, menu, modal
from . import exploreui as X
from . import scenes as S
from .search import search

ADDON = xbmcaddon.Addon('script.kscape.wall')
HOME = xbmcgui.Window(10000)
LIST = 9000
SETTLE_S = 0.45                  # rest before the band shows the poster and full values

STEPS = {xbmcgui.ACTION_MOVE_UP: -1, xbmcgui.ACTION_MOVE_DOWN: 1}
PAGING = (xbmcgui.ACTION_PAGE_UP, xbmcgui.ACTION_PAGE_DOWN, xbmcgui.ACTION_FIRST_PAGE,
          xbmcgui.ACTION_LAST_PAGE)
KEEP_SORTS = 3                   # built item lists kept for instant re-sorting
JUMP_S = 0.25                    # list dimmed while it scrolls to a far row (see the XML)
FAVOURITES_POLL_S = 1.0
BACK = (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU)
MENU = (xbmcgui.ACTION_CONTEXT_MENU, xbmcgui.ACTION_SHOW_INFO)
PLAY = (xbmcgui.ACTION_PLAYER_PLAY,)


def _set(name, value):
    HOME.setProperty(f'kscape.list.{name}', str(value))


class ListWindow(xbmcgui.WindowXML):
    ready = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self.kind = kwargs['kind']
        self.spec = self.kind.list_spec
        self.movies = kwargs['movies']           # library order (title, or artist for albums)
        self.start_id = kwargs.get('focus')
        self.favs = kwargs.get('favs')
        self.query = kwargs.get('query')         # set when listing search results
        self.library = kwargs.get('library') or self.movies    # what Search searches
        self.store = kwargs.get('store')         # this library's collections (None: no C menu entry)
        self.collection = kwargs.get('collection')   # listing this collection's movies
        self.result = 'wall'                     # 'wall', 'exit' or 'favourites' once closed
        self.back = kwargs.get('back') or 'wall'  # what Back does: 'wall', or 'exit' (to Home)
        self.focus_id = self.start_id            # key of the item under the band when closed
        self.explore = kwargs.get('explore')     # window.ExploreLink: the wall's filters
        self.host = kwargs.get('host')           # window.ListHost: the wall underneath, if any
        self.copies = kwargs.get('copies') or (lambda m: [m])   # duplicate copies a row stands for

    def onInit(self):
        if self.ready:
            self._apply_props()                  # back from playback, the info screen, or a
            return                               # search list (they share these properties)
        self.lock = threading.RLock()
        self.closing = False
        self.list = self.getControl(LIST)
        self.keys = self.spec.keys()
        self.col = 'title'
        self.sort = 'title'
        self.moved = 0.0
        self.settled = False
        self.jumped = 0.0
        self.favs_checked = time.time()
        self.favs_seen = self.favs.version if self.favs else 0
        self.built = {}                          # sort -> ListItems for self.rows, recent last
        self.prebuilt = None                     # (sort, ListItems) from the background thread
        self.prebuilder = None
        self._apply_props()
        _set('jump', '')
        self._load(self.start_id)
        self.setFocusId(LIST)
        self.ready = True
        threading.Thread(target=self._settle_loop, daemon=True).start()
        if self.spec.multi:
            first_multi = next(iter(self.spec.multi))
            self.prebuilder = threading.Thread(target=self._prebuild, args=(first_multi,), daemon=True)
            self.prebuilder.start()

    def _apply_props(self):
        _set('col', getattr(self, 'col', 'title'))
        _set('off', L.scroll_for(getattr(self, 'col', 'title'), self.spec))
        _set('settled', '1' if getattr(self, 'settled', False) else '')
        if self.query is None and self.explore is not None and self.explore.active:
            _set('heading', self.explore.caption(len(self.movies)))
            _set('empty', '' if self.movies else X.empty_text())
        elif self.query is None:
            _set('heading', '')
            _set('empty', '')
        else:
            _set('heading', menu.search_heading(self.query, len(self.movies)))
            _set('empty', '' if self.movies else ADDON.getLocalizedString(self.kind.s_no_match).format(self.query))
        _set('count', self.kind.counter(len(self.movies), self._total()))

    def _total(self):
        """The counter's "of": the library searched, the wall's covers before its filters, or
        (nothing narrowing the list) the rows themselves."""
        if self.query is not None:
            return len(self.library)
        if self.explore is not None and self.explore.active:
            return self.explore.total()
        return len(self.movies)

    def _load(self, focus_key):
        t0 = time.perf_counter()
        self.rows = L.sort_rows(self.movies, self.sort, self.spec)
        start = L.find_row(self.rows, focus_key) if focus_key is not None else None
        self._fill(start or 0)
        xbmc.log(f'kscape.list: {len(self.rows)} {self.kind.name} rows in '
                 f'{1000 * (time.perf_counter() - t0):.0f} ms', xbmc.LOGINFO)

    def _build(self, rows, sort):
        """ListItems for `rows`: the slow part of re-sorting (Kodi's API costs ~0.2 ms per item
        and a genre sort of 5,000 movies is ~15,000 rows), so it is one call per item."""
        items = []
        favs = self.favs
        for row in rows:
            values = L.row_values(row, sort, self.spec)
            li = xbmcgui.ListItem(values.pop('label'), offscreen=True)
            values['poster'] = row.movie.poster
            if favs is not None and favs.contains(row.movie):
                values['fav'] = '1'
            li.setProperties({k: v for k, v in values.items() if v})
            items.append(li)
        return items

    def _prebuild(self, sort):
        """Build a likely next sort in the background while the list is browsed."""
        self.prebuilt = (sort, self._build(L.sort_rows(self.movies, sort, self.spec), sort))

    def _items(self):
        items = self.built.pop(self.sort, None)
        if (items is None and self.prebuilder and self.prebuilder.is_alive()
                and self.prebuilt is None and self.sort in self.spec.multi):
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

    def abandon(self):
        """Closed because Home asked for another view (modal.py)."""
        self._close('exit')

    def _close(self, result):
        row = self._current()
        if row:
            self.focus_id = row.movie.key
        self.result = result
        self.closing = True
        self.close()

    # ---- input -----------------------------------------------------------------------------

    def onAction(self, action):
        aid = action.getId()
        if not self.ready:
            return
        follow = None
        with self.lock:
            if aid in STEPS:
                self._step(STEPS[aid])
            elif aid in PAGING:
                self._collapse()
                self.cur = self.list.getSelectedPosition()
            elif aid in (xbmcgui.ACTION_MOVE_LEFT, xbmcgui.ACTION_MOVE_RIGHT):
                step = -1 if aid == xbmcgui.ACTION_MOVE_LEFT else 1
                i = max(0, min(len(self.keys) - 1, self.keys.index(self.col) + step))
                self.col = self.keys[i]
                _set('col', self.col)
                _set('off', L.scroll_for(self.col, self.spec))
            elif aid in BACK:
                origin = self.explore.back() if self.query is None and self.explore else False
                if origin is False:
                    self._close(self.back if self.query is None else 'wall')
                else:
                    self._refilter(origin)
                    row = self._current()
                    if origin is not None and row and row.movie.key == origin:
                        follow = ('details', row.movie)
            elif aid in MENU:
                follow = self._menu()
            elif aid in PLAY:
                row = self._current()
                if row:
                    follow = ('play', row.movie)
        if follow == 'search':
            self._search()
        elif follow == 'filter':
            if self.explore.edit():
                row = self._current()
                self._refilter(row.movie.key if row else None)
        elif follow and follow[0] == 'details':
            self._activate(follow[1], page='explore')
        elif follow and follow[0] == 'play':
            self.kind.play(follow[1])
        elif follow and follow[0] == 'scenes':
            from .collectionwindow import show_collections
            show_collections(self.kind, cid='scenes', focus=follow[1])

    def _collapse(self):
        self.moved = time.time()
        if self.settled:
            self.settled = False
            _set('settled', '')

    def _step(self, direction):
        """Up/Down. Kodi has already moved the list one row; that is kept when it is the right
        move, otherwise the list is re-sorted or sent to the item's next value from here."""
        self._collapse()
        if not self.rows:
            return
        base = min(self.cur, len(self.rows) - 1)
        sort, rows, target = L.step(self.movies, self.rows, self.sort, self.col, base, direction, self.spec)
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
        if row:
            self._activate(row.movie)

    def _activate(self, movie, page=None):
        """Select on a row (or Back to a movie's Explore panel, with `page`)."""
        library = None
        if self.kind.explores:
            library = self.explore.library() if self.explore else self.library
        resolver = self.explore.resolver if self.explore else None
        follow = self.kind.activate(movie, self.favs, library=library, page=page, resolver=resolver)
        self._sync_favourites()
        self._apply_changes()
        if follow == 'search':
            self._search()
        elif isinstance(follow, tuple) and follow[0] == 'explore':
            self._explore(follow[1], movie.key)

    def _apply_changes(self):
        """Art or information edited on the info screen (Choose Art, Refresh): read those items
        again and list them as they are now."""
        from . import actions as A
        keys = [i for media, i in A.take_changes() if media == self.kind.item_type]
        if not keys:
            return
        with self.lock:
            fresh = {}
            for key in keys:
                new = self.kind.fetch_one(key)
                old = next((m for m in self.library or () if m.key == key), None) \
                    or next((m for m in self.movies if m.key == key), None)
                if new is not None:
                    fresh[key] = self.kind.carry(new, old)
            if not fresh:
                return
            swap = lambda items: [fresh.get(m.key, m) for m in items]
            row = self._current()
            self.movies = swap(self.movies)
            if self.library is not None:
                self.library = swap(self.library)
            self.built, self.prebuilt = {}, None
            self._load(row.movie.key if row else None)

    def _explore(self, f, origin):
        if self.explore is not None and self.query is None and self.explore.in_place:
            self.explore.explore(f, origin)
            self._refilter(origin)
            return
        from .window import open_wall                 # no wall of its own: open a filtered one
        open_wall(self.kind, explore=(f, origin))
        self._sync_favourites()

    def _refilter(self, focus_key=None):
        """The wall's filters changed: list what they leave now, on `focus_key` if listed."""
        with self.lock:
            self.movies = self.explore.items()
            self.built, self.prebuilt = {}, None
            self._apply_props()
            self._load(focus_key)

    def _menu(self):
        tr = ADDON.getLocalizedString
        row = self._current()
        movie = row.movie if row else None
        listing = self.query is None                  # the library, not search results
        view = []
        if listing and self.host is not None:
            view.append(('wall', tr(menu.S_VIEW), tr(menu.S_LIST_VIEW)))
        view += [menu.toggle('motion', menu.S_REDUCE_MOTION, menu.reduced_motion()),
                 menu.toggle('auto', menu.S_AUTO_SHUFFLE, ADDON.getSettingBool('auto_shuffle'))]
        misc = [('search', tr(menu.S_SEARCH))]
        if self.host is not None and self.host.favourites:
            misc.append(('favourites', tr(32187)))
        if listing and self.explore is not None and self.library:
            misc.append(('filter', tr(X.S_FILTER_MENU)))
            if self.explore.active:
                misc.append(('clearfilters', tr(X.S_CLEAR)))
        actions = []
        if self.host is not None:
            actions.append(('reload', tr(32024)))
        scene_store = S.store() if row and self.kind.name in S.MEDIA_OF_KIND else None
        if row:
            actions += menu.favourite_entries(movie, self.favs)
            if self.store is not None:
                actions.append(('collect', tr(collectionui.S_COLLECT)))
                if self.collection is not None and self.store.get(self.collection):
                    actions.append(('uncollect', tr(32165).format(collectionui.name_of(self.collection, self.store))))
            actions += S.item_entries(self.kind, movie, scene_store)
        if listing:
            actions.append(menu.exit_entry(self.host.wall if self.host is not None else self))
        else:
            actions.append(('wall', menu.exit_entry(self)[1]))   # search results: back where they started
        choice = menu.show_sections([(menu.S_VIEW_OPTIONS, view), (menu.S_MISC_OPTIONS, misc),
                                     (menu.S_ACTIONS, actions)])
        if choice == 'favourite':
            self.favs.toggle(movie)
            self._sync_favourites()
        elif choice == 'collect':
            collectionui.choose(movie, self._files(movie), self.store)
            self._drop_uncollected()
        elif choice == 'uncollect':
            self.store.remove(self.collection, self._files(movie))
            self._drop_uncollected()
        elif choice in S.ITEM_CHOICES:
            focus = S.handle_item_choice(self.kind, movie, choice, scene_store)
            if focus:
                return ('scenes', focus)
        elif choice in ('search', 'filter'):
            return choice
        elif choice == 'clearfilters':
            self.explore.clear()
            self._refilter(movie.key if movie else None)
        elif choice == 'motion':
            menu.set_reduced_motion(not menu.reduced_motion())
        elif choice == 'auto':
            menu.set_auto_shuffle(not ADDON.getSettingBool('auto_shuffle'))
        elif choice == 'reload':
            self.host.reload(self._reloaded)
        elif choice:
            self._close(choice)                       # 'wall', 'favourites' or 'exit'
        return None

    def _reloaded(self, shown, library):
        """Reload Library finished (window.ListHost.reload): list what the wall now shows."""
        with self.lock:
            if self.closing or self.query is not None:
                return
            row = self._current()
            self.movies, self.library = shown, library
            self.built, self.prebuilt = {}, None
            self._apply_props()
            self._load(row.movie.key if row else None)

    def _files(self, movie):
        return collectionui.keys_of(self.copies(movie))

    def _drop_uncollected(self):
        """Listing a collection: take out rows whose movie has left it, keeping the band near."""
        if self.collection is None or self.store.get(self.collection) is None:
            return
        files = set(self.store.get(self.collection)['members'])
        inside = lambda m: any(f in files for f in self._files(m))
        kept = [m for m in self.movies if inside(m)]
        if len(kept) == len(self.movies):
            return
        i = self.list.getSelectedPosition()
        after = [r.movie.key for r in self.rows[i:] if inside(r.movie)]
        before = [r.movie.key for r in self.rows[:i] if inside(r.movie)]
        self.movies = kept
        self.built, self.prebuilt = {}, None
        self._apply_props()
        self._load(after[0] if after else (before[-1] if before else None))

    # ---- favourites and search ---------------------------------------------------------------

    def _sync_favourites(self):
        """Mark rows whose favourite status changed (here, in an overlay or in Kodi itself)."""
        if self.favs is None or self.favs.poll() == self.favs_seen:
            return
        with self.lock:
            self.favs_seen = self.favs.version
            self.built = {self.sort: self.built.get(self.sort, [])}   # other sorts rebuild
            self.prebuilt = None
            for i, row in enumerate(self.rows):
                li = self.list.getListItem(i)
                fav = '1' if self.favs.contains(row.movie) else ''
                if li.getProperty('fav') != fav:
                    li.setProperty('fav', fav)

    def _search(self):
        query = menu.ask_search(self.kind, self.query or '')
        if not query:
            return
        results = search(self.library, query)
        if self.query is None:
            show_list(self.kind, results, None, self.favs, query=query, library=self.library, store=self.store)
            self._sync_favourites()
            return
        with self.lock:                                       # a new search replaces these results
            self.query, self.movies = query, results
            self.sort = self.col = 'title'
            self.built, self.prebuilt = {}, None
            self._apply_props()
            self._load(None)

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
            if time.time() - self.favs_checked >= FAVOURITES_POLL_S:
                self.favs_checked = time.time()
                self._sync_favourites()


def show_list(kind, movies, focus, favs=None, query=None, library=None, store=None, collection=None,
              copies=None, back='wall', explore=None, host=None):
    """Run the list view for `kind` (or search results, with `query`; `library` is what a new
    search searches; `store` the movie collections, `collection` the one listed, if any).
    Returns (result, key of the item under the band)."""
    menu.wait_for_dialogs()
    window = ListWindow(kind.list_spec.xml, ADDON.getAddonInfo('path'), 'Default', '1080i',
                        kind=kind, movies=movies, focus=focus, favs=favs, query=query, library=library,
                        store=store, collection=collection, copies=copies, back=back,
                        explore=explore, host=host)
    modal.run(window)
    result, focus_id = window.result, window.focus_id
    del window
    return result, focus_id
