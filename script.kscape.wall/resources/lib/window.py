"""Cover wall window: camera-follow navigation and the animated related-cover shuffle.

Kodi cannot move items inside its list containers, so the wall is a pool of image slots that
the window positions itself. Motion is expressed as runtime animations (Control.setAnimations)
whose conditions reference a Home window property; flipping that property starts every
prepared animation in the same frame.

Two slot pools (A, B) double-buffer the shuffle: the new arrangement is bound into the back
pool while it is held transparent, then one property change hides the old covers that
re-appear elsewhere, flies the departing ones off-screen and flies the new ones into place.

One window serves every media kind (kinds.py): movie and TV posters, or square album covers,
each with its own XML generated for that layout. In favourites mode it shows only the items
in Kodi's favourites, and follows changes to them; in collection mode only the movies of one
collection (collectionmodel.py), in the collection's order.
"""
import json
import random
import threading
import time

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from . import geometry as G
from . import cache, collectionui, menu, modal, state
from . import scenes as S
from .favourites import Favourites
from .info import estimate_lines
from .library import rpc
from .listwindow import show_list
from .model import _title_key
from .search import search
from .skins import choose_skin
from .ranking import rank_related
from .wallmodel import (Wall, camera_target, cell_origin, clip_outside, detour, ease_out_back,
                        ease_out_cubic)

MOVES = {
    xbmcgui.ACTION_MOVE_LEFT: (-1, 0),
    xbmcgui.ACTION_MOVE_RIGHT: (1, 0),
    xbmcgui.ACTION_MOVE_UP: (0, -1),
    xbmcgui.ACTION_MOVE_DOWN: (0, 1),
}
SELECT = (xbmcgui.ACTION_SELECT_ITEM,)
PLAY = (xbmcgui.ACTION_PLAYER_PLAY,)
BACK = (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU)
MENU = (xbmcgui.ACTION_CONTEXT_MENU, xbmcgui.ACTION_SHOW_INFO)

HOME = xbmcgui.Window(10000)
ADDON = xbmcaddon.Addon('script.kscape.wall')
PROP_CAM = 'kscape.cam'
PROP_FRONT = 'kscape.front'
PROP_FRAME = 'kscape.frame'
PROP_REDUCED = 'kscape.reduced'         # read by the info screen's slide-in animation
FAVOURITES_FILE = xbmcvfs.translatePath('special://profile/favourites.xml')
FAVOURITES_POLL_S = 1.0
PANEL_TITLE_PX = 40                     # kscape_panel_title, for the square panel's line estimate
PANEL_TITLE_LINE = 50
PANEL_PAD = 34


def _is(prop, value):
    return f'String.IsEqual(Window(Home).Property({prop}),{value})'


def remembered(kind):
    """(Home property, state key) holding the item last focused in `kind`. Movies keep the names
    earlier versions used, so an upgrade still opens on the same movie."""
    if kind.name == 'movies':
        return 'kscape.lastmovie', 'last_movie'
    return f'kscape.last.{kind.name}', f'last_{kind.name}'


def load_library(kind):
    """Every library item of `kind`, from the disk cache when it is still valid (see cache.py).
    Returns (items, cast_complete, cached, total): cached is the cache.load() result or None,
    total the library count the cache is keyed on (it can differ from len(items))."""
    t0 = time.perf_counter()
    total = kind.total()
    cached = cache.load(total, kind.name) if total else None
    if cached:
        items = [kind.from_cache(d) for d in cached['movies']]
        complete = cached['complete'] or not kind.has_extra
    else:
        items = kind.fetch_all() if total else []
        complete = not kind.has_extra
        if items:
            cache.save(total, [m.to_cache() for m in items], complete, kind.name)
    xbmc.log(f'kscape: {len(items)} {kind.name} from {"cache" if cached else "library"} in '
             f'{1000 * (time.perf_counter() - t0):.0f} ms', xbmc.LOGINFO)
    return items, complete, cached, total


def view_key(kind):
    """State key of the view (wall or list) last used for `kind`."""
    return 'view' if kind.name == 'movies' else f'view_{kind.name}'


class Pool:
    """One set of recycled cover slots. Slot k always serves grid cells congruent to it."""

    def __init__(self, win, base, count, layout):
        self.count = count
        self.layout = layout
        self.slots = [win.getControl(base + k) for k in range(count)]
        self.texts = [win.getControl(base + 200 + k) for k in range(count)]
        self.posters = [win.getControl(base + 400 + k) for k in range(count)]
        self.badges = [win.getControl(base + 600 + k) for k in range(count)]
        self.badge_labels = [win.getControl(base + 800 + k) for k in range(count)]
        self.hearts = [win.getControl(base + 1000 + k) for k in range(count)]
        self.badge_shown = [True] * count
        self.heart_shown = [True] * count
        self.cell = [None] * count
        self.shown = [None] * count      # key of the item currently bound
        self.visible = [True] * count    # XML default

    def bind(self, k, cell, item, fallback='', favourite=False):
        if item is None:
            self.set_visible(k, False)
            self.cell[k], self.shown[k] = cell, None
            return
        if self.cell[k] != cell:
            self.slots[k].setPosition(*cell_origin(*cell, layout=self.layout))
            self.cell[k] = cell
        if self.shown[k] != item.key:
            self.posters[k].setImage(item.poster)
            self.texts[k].setText('' if item.poster else fallback)
            if item.badge:
                self.badge_labels[k].setLabel(item.badge)
            if self.badge_shown[k] != bool(item.badge):
                self.badges[k].setVisible(bool(item.badge))
                self.badge_shown[k] = bool(item.badge)
            self.shown[k] = item.key
        if self.heart_shown[k] != favourite:
            self.hearts[k].setVisible(favourite)
            self.heart_shown[k] = favourite
        self.set_visible(k, True)

    def set_visible(self, k, on):
        if self.visible[k] != on:
            self.slots[k].setVisible(on)
            self.visible[k] = on

    def reset(self):
        """Hide every slot and drop its animations (pool becomes the back buffer)."""
        for k in range(self.count):
            self.slots[k].setAnimations([])
            self.set_visible(k, False)


class LibraryMonitor(xbmc.Monitor):
    """Reports library changes: whole-library ones (scan, clean, removal) and single item edits
    (refreshed metadata, or the play count and resume point Kodi saves after watching). A song
    or episode that changes reports its album or show."""

    def __init__(self, kind, on_change, on_item):
        super().__init__()
        self.kind = kind
        self.on_change = on_change
        self.on_item = on_item

    def onScanFinished(self, library):
        if library == self.kind.library:
            self.on_change()

    def onCleanFinished(self, library):
        if library == self.kind.library:
            self.on_change()

    def onNotification(self, sender, method, data):
        prefix = 'AudioLibrary' if self.kind.library == 'music' else 'VideoLibrary'
        if method not in (f'{prefix}.OnUpdate', f'{prefix}.OnRemove'):
            return
        try:
            info = json.loads(data or '{}')
        except ValueError:
            return
        item = info.get('item', info)
        if not item.get('id'):
            return
        if item.get('type') in self.kind.child_types:
            if method.endswith('OnUpdate'):
                from .library import parent_of
                parent = parent_of(item['type'], int(item['id']))
                if parent:
                    self.on_item(int(parent))
            return
        if item.get('type') != self.kind.item_type:
            return
        if method.endswith('OnUpdate'):
            self.on_item(int(item['id']))
        else:
            self.on_change()


class WallWindow(xbmcgui.WindowXML):
    ready = False
    pending_skin = None              # set when the user picks another skin; acted on after close

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self.kind = kwargs['kind']
        self.favourites_only = kwargs.get('favourites', False)
        self.collection = kwargs.get('collection')   # collection id: show only its movies
        self.filtered = self.favourites_only or self.collection is not None
        self.start_view = kwargs.get('view')         # 'list' or 'wall' if chosen from Home

    # ---- lifecycle -------------------------------------------------------------------------

    def onInit(self):
        if self.ready:
            return                       # back from playback: state is intact
        self.lock = threading.RLock()
        self.closing = False
        self.window_id = xbmcgui.getCurrentWindowId()
        self.lay = self.kind.layout
        self.pool_size = self.lay.pool_cols * self.lay.pool_rows
        self.camera = self.getControl(1000)
        self.frame = self.getControl(1001)
        self.panel = self.getControl(1900)
        self.status = self.getControl(1950)
        self.front = Pool(self, 10000, self.pool_size, self.lay)
        self.back = Pool(self, 20000, self.pool_size, self.lay)
        for k in range(self.pool_size):
            self.front.set_visible(k, False)
            self.back.set_visible(k, False)
        self.frame.setVisible(False)
        self.panel.setVisible(False)
        self.reduced = (ADDON.getSettingBool('reduced_motion')
                        or xbmc.getCondVisibility('Skin.HasSetting(ReducedMotion)'))
        HOME.setProperty(PROP_REDUCED, '1' if self.reduced else '')
        self.auto_shuffle = ADDON.getSettingBool('auto_shuffle')
        self.merge = ADDON.getSettingBool('merge_duplicates')
        self.frame_pos = None            # frame target position (wall pixels)
        self.frame_anim = None           # (start time, start position, duration ms)
        self.frame_token = 0
        self.library_gen = 0             # bumped by every full reload; stale results are dropped
        self.loading = False             # a full reload is running in the background
        self.reload_again = False        # another change arrived while it was running
        self.pending_library = None      # reloaded items waiting for an idle moment
        self.paused = False              # the info screen or list view is on top of the wall
        self.monitor = LibraryMonitor(self.kind, self._start_reload, self._item_changed)
        self.favs = Favourites(rpc, FAVOURITES_FILE)
        self.favs_seen = self.favs.version
        self.favs_checked = time.time()
        self.store = collectionui.store(self.kind)
        self.scenes = S.store() if self.kind.name in S.MEDIA_OF_KIND else None
        self.new_days = collectionui.new_days()

        self.wall = Wall.column_major([], layout=self.lay)
        self.all_movies = []             # every library entry; the wall may filter or merge them
        self.history = []                # (wall, focus) before each shuffle, for Back
        self.focus = (0, 0)
        self.cam = (0, 0)
        self.cam_anim = None             # (start time, start camera, duration ms)
        self.cam_token = 0
        self.front_token = 0
        self.shuffle_until = 0.0
        self.panel_cells = ()
        self.panel_shown = False
        self.shuffled_for = None
        self.last_input = time.time()

        self.status.setLabel(ADDON.getLocalizedString(32001))
        items, self.cast_complete, cached, total = load_library(self.kind)

        self.all_movies = items
        visible = self._visible(items)
        self.wall = Wall.column_major(visible, layout=self.lay)
        prop, key = remembered(self.kind)
        last = HOME.getProperty(prop) or str(state.load().get(key, ''))
        start = self.wall.cell_of(int(last)) if last.isdigit() else None
        self.focus = start or (0, 0)
        self._show_status()
        if visible:
            self._set_frame()
            self._pan(camera_target(self.wall, self.focus), animate=False)
        self.ready = True
        threading.Thread(target=self._dwell_loop, daemon=True).start()
        if cached and cached['stale']:
            self._start_reload()
        elif cached and self.collection is not None:
            threading.Thread(target=self._refresh_status, daemon=True).start()
        elif items and not self.cast_complete:
            threading.Thread(target=self._load_cast, args=(total, self.library_gen), daemon=True).start()
        view = self.start_view or (None if self.filtered else state.load().get(view_key(self.kind)))
        if self.start_view and not self.filtered:
            state.save(**{view_key(self.kind): self.start_view})
        if view == 'list' and items:
            self._open_list(back_home=True)   # chosen from Home, or in use when Kodi last closed

    def _show_status(self):
        """Loading done: an empty library or empty favourites says so; otherwise no status."""
        if self.wall.movies():
            self.status.setLabel('')
        elif self.collection is not None and self.all_movies:
            self.status.setLabel(collection_empty(self.collection, self.new_days))
        elif self.favourites_only and self.all_movies:
            self.status.setLabel(f'{ADDON.getLocalizedString(32005)}[CR][COLOR FF9AA3B5]'
                                 f'{ADDON.getLocalizedString(32006)}[/COLOR]')
        else:
            self.status.setLabel(ADDON.getLocalizedString(self.kind.s_empty))

    def _close(self):
        self.closing = True
        item = self.wall.at(*self.focus)
        if item:
            self._remember(item)
        self.close()

    def abandon(self):
        """Closed because Home asked for another view (modal.py)."""
        self._close()

    def _remember(self, item):
        prop, key = remembered(self.kind)
        HOME.setProperty(prop, str(item.key))
        state.save(**{key: item.key})

    # ---- input -----------------------------------------------------------------------------

    def onAction(self, action):
        aid = action.getId()
        if not self.ready:
            if aid in BACK:
                self._close()
            return
        overlay = None
        with self.lock:
            empty = not self.wall.movies()
            if aid in MOVES and not empty:
                self._move(*MOVES[aid])
            elif aid in SELECT and not empty:
                overlay = 'details'
            elif aid in PLAY and not empty:
                item = self.wall.at(*self.focus)
                if item:
                    self._remember(item)
                    overlay = 'play'
            elif aid in BACK:
                self._close()                     # one press back to Home (C -> Undo shuffle undoes)
            elif aid in MENU:
                overlay = self._menu()
        # Opened outside the lock: the wall's background work waits on `paused`, not the lock.
        if overlay == 'details':
            self._open_details()
        elif overlay == 'play':
            self._covered(lambda: self.kind.play(self.wall.at(*self.focus)))
        elif overlay == 'list':
            self._open_list()
        elif overlay == 'search':
            self._search()
        elif overlay == 'favourites':
            self._open_favourites()
        elif overlay == 'scenes':
            self._view_scenes()

    # ---- overlays: info screen, list view, search -------------------------------------------

    def _covered(self, fn):
        """Run `fn` (which may open other windows) with the wall's background work paused."""
        with self.lock:
            self.paused = True
            self._hide_panel()
        try:
            return fn()
        finally:
            with self.lock:
                self.paused = False
                self.last_input = time.time()

    def _open_details(self):
        item = self.wall.at(*self.focus)
        if not item:
            return
        self._remember(item)
        follow = self._covered(lambda: self.kind.activate(item, self.favs))
        self._after_favourites()
        if follow == 'search':
            self._search()

    def _open_list(self, back_home=False):
        """The list view over the wall. Opened as the view itself (from Home), Back there goes
        straight back to Home; opened from the wall's menu, Back returns to the wall."""
        with self.lock:
            current = self.wall.at(*self.focus)
            items = self._visible(self.all_movies)          # library order, whatever the wall's
        if not self.filtered:
            state.save(**{view_key(self.kind): 'list'})
        library = self.kind.visible(self.all_movies, self.merge)
        result, key = self._covered(lambda: show_list(self.kind, items, current.key if current else None,
                                                      self.favs, library=library, store=self.store,
                                                      collection=self.collection, copies=self._copies,
                                                      back='exit' if back_home else 'wall'))
        self._after_favourites()
        self._after_collections()
        with self.lock:
            cell = self.wall.cell_of(key) if key is not None else None
            if cell and cell != self.focus:
                self._finish_shuffle()
                self.focus = cell
                self._set_frame()
                self._pan(camera_target(self.wall, self.focus), animate=False)
            if result == 'wall':
                if not self.filtered:
                    state.save(**{view_key(self.kind): 'wall'})
            elif result == 'skin':
                skin = choose_skin()
                if skin:
                    self.pending_skin = skin
                    self._close()
            elif result == 'exit':
                self._close()

    def _view_scenes(self):
        """View Scenes: the Collections view on the Scenes tab, at this title's first scene."""
        from .collectionwindow import show_collections
        skin = self._covered(lambda: show_collections(self.kind, cid='scenes', focus=self.scene_focus))
        if skin:
            self.pending_skin = skin
            self._close()

    def _open_favourites(self):
        """The cover wall of just this library's favourites, over this one; Back returns here."""
        skin = self._covered(lambda: open_wall(self.kind, view='wall', favourites=True))
        self._after_favourites()
        self._after_collections()
        if skin:
            self.pending_skin = skin
            self._close()

    @property
    def _order(self):
        """Library order (title, or artist for albums) of every item."""
        return {m.key: i for i, m in enumerate(self.all_movies)}

    def _search(self):
        """Search the whole library of this kind (favourites mode too) and list the results."""
        query = menu.ask_search(self.kind)
        if not query:
            return
        with self.lock:
            library = self.kind.visible(self.all_movies, self.merge)
        results = search(library, query)
        self._covered(lambda: show_list(self.kind, results, None, self.favs, query=query, library=library,
                                        store=self.store, copies=self._copies))
        self._after_favourites()
        self._after_collections()

    def _move(self, dx, dy):
        c, r = self.focus[0] + dx, self.focus[1] + dy
        if self.wall.at(c, r) is None:
            return                        # wall edge or padding cell: stay put
        self._finish_shuffle()
        self.focus = (c, r)
        self.last_input = time.time()
        self._hide_panel()
        self._set_frame(animate=True)
        self._pan(camera_target(self.wall, self.focus))

    # ---- favourites ------------------------------------------------------------------------

    def _copies(self, item):
        """The library entries a cover stands for: itself, plus merged duplicate copies."""
        if not (self.kind.merges and self.merge):
            return [item]
        key = _title_key(item)
        return [m for m in self.all_movies if _title_key(m) == key] or [item]

    def _is_favourite(self, item):
        return any(self.favs.contains(c) for c in self._copies(item))

    def _toggle_favourite(self, item):
        if self._is_favourite(item):
            for c in self._copies(item):
                if self.favs.contains(c):
                    self.favs.toggle(c)
        else:
            self.favs.toggle(item)
        self._favourites_changed()

    def _after_collections(self):
        """A collection may have changed in an overlay (list view, search results)."""
        if self.store.poll() and self.collection is not None:
            with self.lock:
                self._apply_library(self.all_movies)

    def _collect(self, item):
        """Add to collection…: the user's collections, ticked where `item` (any copy) is."""
        keys = collectionui.keys_of(self._copies(item))
        if collectionui.choose(item, keys, self.store) and self.collection is not None:
            self._apply_library(self.all_movies)

    def _uncollect(self, item):
        self.store.remove(self.collection, collectionui.keys_of(self._copies(item)))
        self._apply_library(self.all_movies)

    def _after_favourites(self):
        """Favourites may have changed in an overlay (info screen, list, search results)."""
        with self.lock:
            if self.favs.poll() != self.favs_seen:
                self._favourites_changed()

    def _favourites_changed(self):
        self.favs_seen = self.favs.version
        self.favs_checked = time.time()
        if self.favourites_only:
            self._apply_library(self.all_movies)
        else:
            self._rebind(self.front)               # hearts follow the new favourites

    # ---- camera ----------------------------------------------------------------------------

    def _visual_cam(self, now):
        if not self.cam_anim:
            return self.cam
        t0, frm, dur = self.cam_anim
        e = ease_out_cubic((now - t0) * 1000.0 / dur) if dur else 1.0
        return (frm[0] + (self.cam[0] - frm[0]) * e, frm[1] + (self.cam[1] - frm[1]) * e)

    def _pan(self, target, animate=True):
        lay = self.lay
        now = time.time()
        vis = self._visual_cam(now)
        # Never lag further than the pool's slack, or the screen edge would show empty cells.
        dx = max(-lay.pitch_x * 1.3, min(lay.pitch_x * 1.3, target[0] - vis[0]))
        dy = max(-lay.pitch_y * 1.1, min(lay.pitch_y * 1.1, target[1] - vis[1]))
        animate = animate and not self.reduced and (abs(dx) > 0.5 or abs(dy) > 0.5)
        self.cam = target
        self._rebind(self.front)
        if animate:
            self.cam_anim = (now, (target[0] - dx, target[1] - dy), G.PAN_MS)
            self.cam_token += 1
            self.camera.setAnimations([('Conditional',
                f'effect=slide start={int(round(dx))},{int(round(dy))} end=0,0 time={G.PAN_MS} '
                f'tween=cubic easing=out reversible=false condition={_is(PROP_CAM, self.cam_token)}')])
        else:
            self.cam_anim = None
            self.camera.setAnimations([])
        self.camera.setPosition(-int(target[0]), -int(target[1]))
        if animate:
            HOME.setProperty(PROP_CAM, str(self.cam_token))

    def _origin(self):
        """Top-left grid cell of the pool window around the camera centre."""
        lay = self.lay
        cx = self.cam[0] + G.SCREEN_W / 2.0
        cy = self.cam[1] + G.SCREEN_H / 2.0
        return int(cx // lay.pitch_x) - lay.pool_cols // 2, int(cy // lay.pitch_y) - lay.pool_rows // 2

    def _slot_cells(self):
        cols, rows = self.lay.pool_cols, self.lay.pool_rows
        c0, r0 = self._origin()
        for k in range(self.pool_size):
            i, j = k % cols, k // cols
            yield k, (c0 + (i - c0) % cols, r0 + (j - r0) % rows)

    def _bind(self, pool, k, cell, item):
        if item is None:
            pool.bind(k, cell, None)
        else:
            pool.bind(k, cell, item, self.kind.fallback(item), self._is_favourite(item))

    def _rebind(self, pool, wall=None):
        wall = wall or self.wall
        for k, cell in self._slot_cells():
            self._bind(pool, k, cell, wall.at(*cell))

    def _cell_xy(self, cell):
        return cell_origin(*cell, layout=self.lay)

    def _visual_frame(self, now):
        if not self.frame_anim:
            return self.frame_pos
        t0, frm, dur = self.frame_anim
        p = (now - t0) * 1000.0 / dur if dur else 1.0
        e = ease_out_back(p) if G.FRAME_TWEEN == 'back' else ease_out_cubic(p)
        return (frm[0] + (self.frame_pos[0] - frm[0]) * e, frm[1] + (self.frame_pos[1] - frm[1]) * e)

    def _set_frame(self, animate=False):
        """Move the focus frame; animated moves glide from wherever the frame is drawn now."""
        x, y = self._cell_xy(self.focus)
        target = (x - self.lay.frame, y - self.lay.frame)
        now = time.time()
        animate = animate and not self.reduced and self.frame_pos is not None
        if animate:
            vis = self._visual_frame(now)
            dx, dy = int(round(vis[0] - target[0])), int(round(vis[1] - target[1]))
            self.frame_token += 1
            self.frame.setAnimations([('Conditional',
                f'effect=slide start={dx},{dy} end=0,0 time={G.FRAME_MS} tween={G.FRAME_TWEEN} '
                f'easing=out reversible=false condition={_is(PROP_FRAME, self.frame_token)}')])
            self.frame_anim = (now, vis, G.FRAME_MS)
        else:
            self.frame.setAnimations([])
            self.frame_anim = None
        self.frame.setPosition(*target)
        self.frame_pos = target
        self.frame.setVisible(True)
        if animate:
            HOME.setProperty(PROP_FRAME, str(self.frame_token))

    # ---- info panel ------------------------------------------------------------------------

    def _show_panel(self):
        item = self.wall.at(*self.focus)
        if not item:
            return
        lay = self.lay
        c, r = self.focus
        x, y = self._cell_xy(self.focus)
        left = [(c - i, r) for i in range(1, lay.panel_cells + 1)]
        right = [(c + i, r) for i in range(1, lay.panel_cells + 1)]
        left_on = self._cell_xy(left[-1])[0] - self.cam[0] >= 0
        right_on = x + lay.cover_w + lay.frame + G.panel_w(lay) - self.cam[0] <= G.SCREEN_W
        hidden = lambda cells: sum(self.wall.at(*cell) is not None for cell in cells)
        if left_on and right_on and hidden(left) != hidden(right):
            cells = left if hidden(left) < hidden(right) else right   # e.g. a short favourites row
        elif left_on and c - lay.panel_cells >= 0:
            cells = left
        else:
            cells = right
        if cells[0][0] < c:
            px = self._cell_xy((c - lay.panel_cells, r))[0]       # far cell's left edge
        else:
            px = x + lay.cover_w + lay.frame                       # frame's right edge
        self.panel.setPosition(px, y - lay.frame)
        title, body = self.kind.panel(item)
        if lay is G.SQUARE:
            # Album title on one or two lines (a textbox), the artist right below it.
            self.getControl(1901).setText(title)
            lines = min(2, estimate_lines(title, G.panel_w(lay) - 2 * PANEL_PAD, PANEL_TITLE_PX))
            self.getControl(1902).setPosition(PANEL_PAD, lay.frame + 26 + lines * PANEL_TITLE_LINE + 10)
        else:
            self.getControl(1901).setLabel(title)
        self.getControl(1902).setText(body)
        self.panel.setVisible(True)
        self.panel_cells = tuple(cells)
        self.panel_shown = True

    def _hide_panel(self):
        if self.panel_shown:
            self.panel.setVisible(False)
            self.panel_shown = False

    def _dwell_loop(self):
        mon = xbmc.Monitor()
        while not self.closing and not mon.abortRequested():
            time.sleep(0.05)
            with self.lock:
                now = time.time()
                if self.paused or xbmcgui.getCurrentWindowId() != self.window_id:
                    # Covered (full-screen video, Home, another window): stay idle. A video
                    # playing behind the wall no longer counts, so browsing during playback
                    # keeps the synopsis panel and the shuffle.
                    self.last_input = now
                    continue
                if now - self.favs_checked >= FAVOURITES_POLL_S:
                    self.favs_checked = now
                    if self.favs.poll() != self.favs_seen:   # e.g. from Kodi's favourites window
                        self._favourites_changed()
                        continue
                if self.shuffle_until and now >= self.shuffle_until:
                    self._finish_shuffle()
                idle = now - self.last_input
                if self.pending_library is not None and idle >= 1.0 and not self.shuffle_until:
                    items, self.pending_library = self.pending_library, None
                    self._apply_library(items)
                    continue
                item = self.wall.at(*self.focus)
                if item and not self.panel_shown and idle >= G.PANEL_DELAY_S:
                    self._show_panel()
                if (item and self.auto_shuffle and idle >= G.SHUFFLE_DELAY_S and not self.shuffle_until
                        and self.shuffled_for != item.key and len(self.wall.movies()) > 1):
                    self.shuffled_for = item.key
                    self._shuffle_related(item)

    # ---- menu and library changes -------------------------------------------------------------

    def _menu(self):
        tr = ADDON.getLocalizedString
        on_off = lambda flag: tr(32030 if flag else 32031)
        item = self.wall.at(*self.focus)
        entries = []
        if self.history:
            entries.append(('undo', tr(32295)))
        if item:
            entries += [
                ('list', tr(32071)),
                ('shuffle', tr(32021)),
                ('auto', tr(32022).format(on_off(self.auto_shuffle))),
                ('motion', tr(32023).format(on_off(self.reduced))),
            ]
            if self.kind.merges:
                entries.append(('merge', tr(32029).format(on_off(self.merge))))
        if item:
            for e in reversed(S.item_entries(self.kind, item, self.scenes)):
                entries.insert(0, e)
            entries.insert(0, ('collect', tr(collectionui.S_COLLECT)))
            if self.collection is not None and self.store.get(self.collection):
                entries.insert(1, ('uncollect', tr(32165).format(collectionui.name_of(self.collection, self.store))))
        if not self.favourites_only:
            entries.append(('favourites', tr(32187)))
        entries += [
            ('reload', tr(32024)),
            ('skin', tr(32025)),
            ('exit', tr(32026)),
        ]
        choice = menu.show(item, self.favs, entries,
                           is_favourite=self._is_favourite(item) if item else None)
        self.last_input = time.time()
        if choice == 'favourite':
            self._toggle_favourite(item)
        elif choice == 'undo':
            if self.history:
                self._undo()
        elif choice == 'collect':
            self._collect(item)
        elif choice == 'uncollect':
            self._uncollect(item)
        elif choice in S.ITEM_CHOICES:
            self.scene_focus = S.handle_item_choice(self.kind, item, choice, self.scenes)
            if self.scene_focus:
                return 'scenes'
        elif choice in ('search', 'list', 'favourites'):
            return choice
        elif choice == 'shuffle':
            self._finish_shuffle()
            if not self.panel_shown:
                self._show_panel()
            self.shuffled_for = item.key
            self._shuffle_related(item)
        elif choice == 'auto':
            self.auto_shuffle = not self.auto_shuffle
            ADDON.setSettingBool('auto_shuffle', self.auto_shuffle)
        elif choice == 'motion':
            self.reduced = not self.reduced
            ADDON.setSettingBool('reduced_motion', self.reduced)
            HOME.setProperty(PROP_REDUCED, '1' if self.reduced else '')
        elif choice == 'merge':
            self.merge = not self.merge
            ADDON.setSettingBool('merge_duplicates', self.merge)
            self._apply_library(self.all_movies)
        elif choice == 'reload':
            cache.discard(self.kind.name)
            self._start_reload()
        elif choice == 'skin':
            skin = choose_skin()
            if skin:
                self.pending_skin = skin
                self._close()
        elif choice == 'exit':
            self._close()

    def _visible(self, items):
        """What the wall shows: in favourites mode only favourites (any copy of a merged movie
        counts), then duplicate copies merged when that setting is on."""
        if self.collection is not None:
            shown = self.kind.visible(items, self.merge)
            return [m for m, _ in collectionui.members(self.collection, self.store, items, shown, self.new_days)]
        if self.favourites_only:
            items = [m for m in items if self.favs.contains(m)]
        return self.kind.visible(items, self.merge)

    # Library data is fetched on background threads (a large library takes tens of seconds) and
    # applied under the lock, so the wall stays responsive while it loads.

    def _load_cast(self, total, gen):
        """Fill in cast for the shuffle ranking after the wall is already showing."""
        t0 = time.perf_counter()
        extra = self.kind.fetch_extra()
        with self.lock:
            if self.closing or gen != self.library_gen:
                return
            self.all_movies = [self.kind.with_extra(m, extra) for m in self.all_movies]
            self._patch({m.key: m for m in self.all_movies})
            self.cast_complete = True
            snapshot = list(self.all_movies)
        xbmc.log(f'kscape.wall: cast for {len(extra)} {self.kind.name} in '
                 f'{1000 * (time.perf_counter() - t0):.0f} ms', xbmc.LOGINFO)
        cache.save(total, [m.to_cache() for m in snapshot], True, self.kind.name)

    def _start_reload(self):
        """Re-read the whole library in the background; it is applied once the wall is idle."""
        if self.loading:
            self.reload_again = True
            return
        self.loading = True
        self.library_gen += 1
        threading.Thread(target=self._reload_worker, args=(self.library_gen,), daemon=True).start()

    def _reload_worker(self, gen):
        while True:
            self.reload_again = False
            total = self.kind.total()
            items = self.kind.fetch_all() if total else []
            extra = self.kind.fetch_extra() if items else {}
            if not self.reload_again:
                break
        items = [self.kind.with_extra(m, extra) for m in items]
        with self.lock:
            self.loading = False
            if self.closing or gen != self.library_gen:
                return
            self.pending_library = items
            self.cast_complete = True
        if items:
            cache.save(total, [m.to_cache() for m in items], True, self.kind.name)

    def _refresh_status(self):
        """Collection mode: the cache may predate the latest plays; bring play state and dates
        up to date (they decide New, Paused and Played)."""
        from dataclasses import replace
        from .library import fetch_status
        status = fetch_status(self.kind.name)
        with self.lock:
            if self.closing:
                return
            self.pending_library = [replace(m, **status[m.key]) if m.key in status else m
                                    for m in self.all_movies]    # applied once the wall is idle

    def _item_changed(self, key):
        """One item changed (e.g. watched): patch it in place without re-laying out the wall."""
        threading.Thread(target=self._refresh_item, args=(key,), daemon=True).start()

    def _refresh_item(self, key):
        item = self.kind.fetch_one(key)
        with self.lock:
            if self.closing:
                return
            current = next((m for m in self.all_movies if m.key == key), None)
            if item is None or current is None:
                self._start_reload()              # added or vanished: needs a full re-read
                return
            if self.kind.has_extra and not self.cast_complete:
                item = self.kind.with_extra(item, {key: current.cast})
            was_in = self.collection is not None and self._in_view(current)
            self.all_movies = [item if m.key == key else m for m in self.all_movies]
            if self.collection is not None and was_in != self._in_view(item):
                self._apply_library(self.all_movies)  # e.g. watched: moves from Paused to Played
            else:
                self._patch({key: item})
            snapshot, complete = list(self.all_movies), self.cast_complete
        cache.save(len(snapshot), [m.to_cache() for m in snapshot], complete, self.kind.name)

    def _in_view(self, item):
        return any(m.key == item.key for m in self._visible(self.all_movies))

    def _patch(self, by_key):
        """Swap updated items into the wall and Back history, keeping every cell in place."""
        def patched(wall):
            return Wall(wall.rows, wall.cols,
                        [by_key.get(m.key, m) if m is not None else None for m in wall.cells], self.lay)
        old = {m.key: m for m in self.wall.movies()}
        self.wall = patched(self.wall)
        self.history = [(patched(w), f) for w, f in self.history]
        changed = {k for k, m in by_key.items() if k in old and not old[k].looks_same(m)}
        if changed:
            self.front.shown = [None if k in changed else k for k in self.front.shown]
            self._rebind(self.front)

    def _apply_library(self, items):
        """Rebuild the wall from `items`, keeping the focused item when it still exists."""
        self._finish_shuffle()
        current = self.wall.at(*self.focus)
        self.all_movies = items
        visible = self._visible(items)
        self.wall = Wall.column_major(visible, layout=self.lay)
        self.history = []
        self.front.shown = [None] * self.pool_size     # artwork may have changed
        cell = self.wall.cell_of(current.key) if current else None
        if cell is None and current and self.kind.merges:
            # The focused copy was merged away: stay on the copy that represents that title.
            cell = next((self.wall.cell_of(m.key) for m in self.wall.movies()
                         if (m.title, m.year) == (current.title, current.year)), None)
        if cell is None and current and current.key in self._order:
            # Gone from favourites: stay near where it was, on the next item in library order.
            order = self._order
            after = [m for m in visible if order.get(m.key, 0) > order[current.key]]
            cell = self.wall.cell_of(after[0].key) if after else None
            if cell is None and visible:
                cell = self.wall.cell_of(visible[-1].key)
        self.focus = cell or (0, 0)
        self.shuffled_for = None
        self._hide_panel()
        self._show_status()
        if visible:
            self._set_frame()
            self._pan(camera_target(self.wall, self.focus), animate=False)
        else:
            self.frame.setVisible(False)
            self.front.reset()
            self.back.reset()
        xbmc.log(f'kscape.wall: applied library of {len(visible)} covers', xbmc.LOGINFO)

    # ---- shuffle ---------------------------------------------------------------------------

    def _shuffle_related(self, anchor):
        t0 = time.perf_counter()
        ranked = rank_related(anchor, self.wall.movies(), score_fn=self.kind.score_fn)
        t1 = time.perf_counter()
        new = self.wall.arranged_around(self.focus, ranked, blocked=self.panel_cells)
        xbmc.log(f'kscape.wall: shuffle {len(ranked)} {self.kind.name}: rank {1000 * (t1 - t0):.1f} ms, '
                 f'place {1000 * (time.perf_counter() - t1):.1f} ms', xbmc.LOGINFO)
        self.history.append((self.wall, self.focus))
        self._transition(new, anchor_key=anchor.key)

    def _undo(self):
        self._finish_shuffle()
        wall, focus = self.history.pop()
        item = self.wall.at(*self.focus)
        self._transition(wall, anchor_key=item.key if item and wall.cell_of(item.key) == self.focus
                         else None)
        self.focus = focus
        self.shuffled_for = wall.at(*focus).key if wall.at(*focus) else None
        self.last_input = time.time()
        self._hide_panel()
        self._set_frame()
        self._pan(camera_target(self.wall, self.focus))

    def _transition(self, new, anchor_key=None):
        """Fly every cover from where it is in the current wall to its cell in `new`."""
        lay = self.lay
        old = self.wall
        self.front_token += 1
        tok = self.front_token
        on = _is(PROP_FRONT, tok)
        rng = random.Random(tok)
        cx, cy = self.cam
        view = (cx, cy, cx + G.SCREEN_W, cy + G.SCREEN_H)
        margin = lay.pitch_x
        longest = 0
        instant = self.reduced

        # The selected cover (and its frame) stays put; nothing flies across it (wallmodel.detour).
        anchor_cell = new.cell_of(anchor_key) if anchor_key is not None else None
        if anchor_cell:
            ax, ay = self._cell_xy(anchor_cell)
            keep_out = (ax - lay.frame, ay - lay.frame, ax + lay.cover_w + lay.frame, ay + lay.cover_h + lay.frame)
        size = (lay.cover_w, lay.cover_h)

        def path(a, b):
            return [a] + (detour(a, b, keep_out, size, lay.frame) if anchor_cell else []) + [b]

        def slides(points, origin, delay, dur, easing):
            """Slide animations moving a cover through `points` (absolute top-lefts; the control
            sits at `origin`). One leg keeps the single eased slide; a detour chains one slide per
            leg - the first holds the cover at its start during the delay, later ones add on - with
            each leg's time proportional to its length."""
            offs = [(p[0] - origin[0], p[1] - origin[1]) for p in points]
            legs = list(zip(offs, offs[1:]))
            if len(legs) == 1:
                (s0, s1), = legs
                return [('Conditional', f'effect=slide start={int(s0[0])},{int(s0[1])} end={int(s1[0])},{int(s1[1])} '
                                        f'delay={delay} time={dur} tween=cubic easing={easing} '
                                        f'reversible=false condition={on}')]
            lengths = [max(1.0, ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5) for a, b in legs]
            total = sum(lengths)
            out, t = [], delay
            for i, ((a, b), length) in enumerate(zip(legs, lengths)):
                ms = max(1, int(round(dur * length / total)))
                tween = 'tween=sine easing=in' if i == 0 else ('tween=sine easing=out' if i == len(legs) - 1
                                                                else 'tween=linear')
                start = a if i == 0 else (0, 0)
                end = b if i == 0 else (b[0] - a[0], b[1] - a[1])
                out.append(('Conditional', f'effect=slide start={int(start[0])},{int(start[1])} '
                                           f'end={int(end[0])},{int(end[1])} delay={t} time={ms} {tween} '
                                           f'reversible=false condition={on}'))
                t += ms
            return out

        def flight(start, cell_xy, delay, dur):
            half = dur // 2
            grow = int(round(100 * 100.0 / G.FLIGHT_SHRINK))
            return slides(path(start, cell_xy), cell_xy, delay, dur, 'inout') + [
                ('Conditional', f'effect=zoom start=100 end={G.FLIGHT_SHRINK} center=auto delay={delay} '
                                f'time={half} tween=sine easing=out reversible=false condition={on}'),
                ('Conditional', f'effect=zoom start=100 end={grow} center=auto delay={delay + half} '
                                f'time={half} tween=sine easing=in reversible=false condition={on}'),
            ]

        # Back buffer: new arrangement, transparent until the trigger, then flying into place.
        hold = ('Conditional', f'effect=fade start=0 end=0 time=0 reversible=false condition=!{on}')
        for k, cell in self._slot_cells():
            item = new.at(*cell)
            anims = [hold]
            if item is not None and item.key != anchor_key and not instant:
                px, py = self._cell_xy(cell)
                prev = old.cell_of(item.key)
                qx, qy = self._cell_xy(prev) if prev else (px, py)
                sx, sy = clip_outside((px, py), (qx, qy), view, margin)
                if (sx, sy) != (px, py):
                    delay = int(rng.uniform(0, G.FLIGHT_DELAY_MAX_MS))
                    dur = G.FLIGHT_MS + int(rng.uniform(0, G.FLIGHT_JITTER_MS))
                    anims += flight((sx, sy), (px, py), delay, dur)
                    longest = max(longest, delay + dur)
            self.back.slots[k].setAnimations(anims)
            self._bind(self.back, k, cell, item)

        # Front buffer: covers that leave the screen fly out; everything else vanishes at the
        # trigger because the back buffer now shows it (in flight or in place).
        vanish = ('Conditional', f'effect=fade start=0 end=0 time=0 reversible=false condition={on}')
        pool_cells = {cell for _, cell in self._slot_cells()}
        for k in range(self.pool_size):
            key = self.front.shown[k]
            if key is None or not self.front.visible[k]:
                continue
            ox, oy = self._cell_xy(self.front.cell[k])
            on_screen = view[0] - lay.cover_w < ox < view[2] and view[1] - lay.cover_h < oy < view[3]
            dest = new.cell_of(key)
            dx_, dy_ = self._cell_xy(dest) if dest else (ox, oy)
            stays_in_pool = dest in pool_cells
            if instant or not on_screen or stays_in_pool:
                self.front.slots[k].setAnimations([vanish])
                continue
            ex, ey = clip_outside((ox, oy), (dx_, dy_), view, margin)
            delay = int(rng.uniform(0, G.FLIGHT_DELAY_MAX_MS * 0.5))
            dur = G.DEPART_MS + int(rng.uniform(0, G.FLIGHT_JITTER_MS))
            self.front.slots[k].setAnimations(slides(path((ox, oy), (ex, ey)), (ox, oy), delay, dur, 'in') + [
                ('Conditional', f'effect=zoom start=100 end={G.FLIGHT_SHRINK} center=auto delay={delay} '
                                f'time={dur} tween=sine easing=in reversible=false condition={on}'),
                ('Conditional', f'effect=fade start=100 end=0 delay={delay + dur * 2 // 3} '
                                f'time={dur // 3} reversible=false condition={on}'),
            ])
            longest = max(longest, delay + dur)

        HOME.setProperty(PROP_FRONT, str(tok))      # one flip starts every animation above
        self.wall = new
        self.front, self.back = self.back, self.front
        self.shuffle_until = time.time() + longest / 1000.0 + 0.05

    def _finish_shuffle(self):
        """Retire the old front buffer once its departing covers are gone (or immediately)."""
        if self.shuffle_until:
            self.back.reset()
            self.shuffle_until = 0.0


def collection_empty(cid, days):
    """Status text of an empty collection: what would put movies in it."""
    tr = ADDON.getLocalizedString
    if cid == 'new':
        return tr(32177).format(days)
    if cid == 'paused':
        return tr(32178)
    if cid == 'played':
        return tr(32179)
    return f'{tr(32175)}[CR][COLOR FF9AA3B5]{tr(32176)}[/COLOR]'


def open_wall(kind, view=None, favourites=False, collection=None):
    """Run the wall for `kind`. Returns the skin the user chose to switch to, if any."""
    window = WallWindow(kind.wall_xml, ADDON.getAddonInfo('path'), 'Default', '1080i',
                        kind=kind, view=view, favourites=favourites, collection=collection)
    modal.run(window)
    skin = window.pending_skin
    del window
    return skin
