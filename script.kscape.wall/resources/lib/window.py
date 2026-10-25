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

Movie walls can be filtered (explore.py): from Explore on a movie's info screen, or C ->
Filter…. The filters are shared with the list view opened over the wall, a caption along the
bottom says what they are and how many movies match, and Back retraces them - back to the
movie's Explore panel, then to the whole library - before it leaves the wall.
"""
import itertools
import json
import math
import random
import threading
import time

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from . import geometry as G
from . import badges, cache, collectionui, displayui, menu, modal, ratings, state
from . import explore as E
from . import moviesets as MS
from . import npchip as np_chip
from . import exploreui as X
from . import scenes as S
from .favourites import Favourites
from .info import estimate_lines
from .library import fetch_sets, rpc
from .listwindow import show_list
from .model import copy_groups
from .search import search
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
PROP_MOTION = 'kscape.motion.{}'       # per wall: '<frame token>.<camera token>' (Glide)
PROP_FRONT = 'kscape.front.{}'         # per wall: the shuffle token (_transition)
PROP_REDUCED = 'kscape.reduced'         # read by the info screen's slide-in animation
FAVOURITES_FILE = xbmcvfs.translatePath('special://profile/favourites.xml')
FAVOURITES_POLL_S = 1.0
CAPTION_PX, CHIP_W = 62, 620                     # filter caption, now-playing chip (tools/np_chip.py)
HEAL_EVERY_S = 10.0                     # idle wall: look for posters that never arrived
HEAL_AFTER_S = 8.0                      # a poster this long on screen should be in Kodi's cache
HEAL_RETRIES = 6                        # reload attempts per poster, 10 s apart and doubling
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
    """One set of recycled cover slots. Slot k always serves grid cells congruent to it.

    What a slot shows comes from an offscreen list item in the pool's hidden data list
    (wallxml.slot): poster art and the properties on, text, badge, bw and fav. Updating those
    takes no GUI lock; only moving a slot (setPosition) and its animations are control calls,
    each of which waits for Kodi's GUI lock (a frame or so) - binding a screenful of covers
    control by control took tens of seconds.

    The pool's slots sit in one group (wallxml.POOL_GROUPS), hidden while the pool is the idle
    back buffer: Kodi then skips their visibility conditions every frame, and retiring a pool
    is one control call rather than one per slot."""

    def __init__(self, win, base, count, layout, sx=1.0):
        from .wallxml import POOL_GROUPS, SOURCES
        self.count = count
        self.base = base
        self.layout = layout
        self.sx = sx                     # the screen's horizontal stretch (display.stage)
        self.group = win.getControl(POOL_GROUPS[base])
        self.group_on = True             # XML default
        self.slots = [win.getControl(base + k) for k in range(count)]
        self.items = [xbmcgui.ListItem(offscreen=True) for _ in range(count)]
        win.getControl(SOURCES[base]).addItems(self.items)
        self.badge_text = [None] * count
        self.heart_shown = [False] * count
        self.bound_at = [0.0] * count    # when the poster was last set (window._heal_posters)
        self.cell = [None] * count
        self.shown = [None] * count      # key of the item currently bound
        self.visible = [False] * count   # 'on' is unset: hidden

    def bind(self, k, cell, item, fallback='', favourite=False, badge=None):
        if item is None:
            self.set_visible(k, False)
            self.cell[k], self.shown[k] = cell, None
            return
        if self.cell[k] != cell:
            self.slots[k].setPosition(*cell_origin(*cell, layout=self.layout))
            self.cell[k] = cell
        li = self.items[k]
        badge = item.badge if badge is None else badge
        if self.shown[k] != item.key:
            li.setArt({'poster': item.poster})
            li.setProperty('text', '' if item.poster else fallback)
            self.bound_at[k] = time.time()
            self.shown[k] = item.key
        if self.badge_text[k] != badge:
            li.setProperty('badge', badge or '')
            li.setProperty('bw', badge_bucket(badge) if badge else '')
            self.badge_text[k] = badge
        if self.heart_shown[k] != favourite:
            li.setProperty('fav', '1' if favourite else '')
            self.heart_shown[k] = favourite
        self.set_visible(k, True)
        if not self.group_on:
            self.group.setVisible(True)
            self.group_on = True

    def reload_poster(self, k, url, phase):
        """Ask for a poster again (window._heal_posters): cleared first, set back a moment later,
        so Kodi sees a new texture."""
        self.items[k].setArt({'poster': '' if phase == 0 else url})
        if phase:
            self.bound_at[k] = time.time()

    def set_visible(self, k, on):
        if self.visible[k] != on:
            self.items[k].setProperty('on', '1' if on else '')
            self.visible[k] = on

    def reset(self):
        """Hide the pool and every slot (pool becomes the back buffer). Slot animations stay:
        their conditions name a past shuffle token, so they no longer apply (_transition), and
        the next shuffle replaces them."""
        for k in range(self.count):
            self.set_visible(k, False)
        if self.group_on:
            self.group.setVisible(False)
            self.group_on = False


def badge_bucket(text):
    """Which fixed badge box fits `text` (wallxml.BADGE_WIDTHS)."""
    from .wallxml import BADGE_WIDTHS
    return str(next(n for n, _ in BADGE_WIDTHS if len(text) <= n))


_walls = itertools.count(1)             # wall instances: each gets its own motion properties

REDUCED_MS = 160                        # Reduce motion: a short plain glide instead of a jump
SETTLE_S = 0.8                          # idle this long: finished glides become static (Glide.settle)


def ease_out_sine(p):
    """Matches Kodi's tween="sine" easing="out"."""
    return math.sin(max(0.0, min(1.0, p)) * math.pi / 2)


class Glide:
    """A control (the camera, the focus frame) placed only by runtime slide animations from its
    XML position (0, 0); Python never calls setPosition on it.

    Each move replaces its animations with two: a hold where it is drawn now (condition: the
    current token) and the glide from there to the target (the next token). Writing the motion
    property switches from one to the other in the same frame, so a move that interrupts a
    glide carries on from where the control is, without the snap to the old target and the
    jump to the new one that setPosition between the calls caused. The camera and the frame
    share one property ('<frame token>.<camera token>'): one write starts both glides together.
    Once a glide is over, settle() swaps it for a static placement (same token), so a window
    re-init (which replays conditional animations) shows nothing moving."""

    def __init__(self, control, prop, part):
        self.control = control
        self.prop = prop
        self.part = part                 # 0: frame (first token), 1: camera (second)
        self.token = 0
        self.pos = None                  # target, in the control's coordinates
        self.anim = None                 # (start time, start position, ms, ease)
        self.settled = True

    def cond(self, token):
        if self.part == 0:
            return f'String.StartsWith(Window(Home).Property({self.prop}),{token}.)'
        return f'String.EndsWith(Window(Home).Property({self.prop}),.{token})'

    def visual(self, now):
        if not self.anim:
            return self.pos
        t0, frm, ms, ease = self.anim
        e = ease((now - t0) * 1000.0 / ms)
        return (frm[0] + (self.pos[0] - frm[0]) * e, frm[1] + (self.pos[1] - frm[1]) * e)

    def busy(self, now):
        return self.anim is not None and (now - self.anim[0]) * 1000.0 < self.anim[2]

    def plan(self, target, now, start=None, ms=0, tween='cubic', ease=None):
        """The animations taking the control to `target` (from `start`, default where it is
        drawn now; ms=0 places it at once). Bumps the token: commit with Window._commit."""
        target = (int(round(target[0])), int(round(target[1])))
        old = self.token
        self.token += 1
        if self.pos is None or not ms:
            self.pos, self.anim, self.settled = target, None, True
            return [self._place(target, self.token)]
        vis = self.visual(now) if start is None else start
        vis = (int(round(vis[0])), int(round(vis[1])))
        self.pos, self.anim, self.settled = target, (now, vis, ms, ease), False
        return [self._place(vis, old),
                ('Conditional', f'effect=slide start={vis[0]},{vis[1]} end={target[0]},{target[1]} '
                                f'time={ms} tween={tween} easing=out reversible=false '
                                f'condition={self.cond(self.token)}')]

    def _place(self, at, token):
        return ('Conditional', f'effect=slide start={at[0]},{at[1]} end={at[0]},{at[1]} time=0 '
                               f'reversible=false condition={self.cond(token)}')

    def settle(self, now):
        """After a glide: the same placement without the animation (one control call)."""
        if self.settled or self.busy(now):
            return
        self.control.setAnimations([self._place(self.pos, self.token)])
        self.anim, self.settled = None, True


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
        own = sender == 'script.kscape.wall' and method == 'Other.itemchanged'     # actions.announce_change
        if method not in (f'{prefix}.OnUpdate', f'{prefix}.OnRemove') and not own:
            return
        try:
            info = json.loads(data or '{}')
        except ValueError:
            return
        item = info.get('item', info)
        if not item.get('id'):
            return
        update = method.endswith('OnUpdate') or own
        if item.get('type') in self.kind.child_types:
            if update:
                from .library import parent_of
                parent = parent_of(item['type'], int(item['id']))
                if parent:
                    self.on_item(int(parent))
            return
        if item.get('type') != self.kind.item_type:
            return
        if update:
            self.on_item(int(item['id']))
        else:
            self.on_change()


class WallWindow(xbmcgui.WindowXML):
    ready = False
    base_total = 0                   # covers before filters (the counter's "of")
    shown_total = 0                  # movies the wall shows (a set's cover counts its movies)

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self.kind = kwargs['kind']
        self.favourites_only = kwargs.get('favourites', False)
        self.collection = kwargs.get('collection')   # collection id: show only its movies
        self.movie_set = kwargs.get('movie_set')     # Kodi movie set id: show only its movies
        self.given = kwargs.get('library')           # (items, cast complete) from the wall beneath
        self.filtered = self.favourites_only or self.collection is not None or self.movie_set is not None
        self.start_view = kwargs.get('view')         # 'list' or 'wall' if chosen from Home
        self.layout = kwargs.get('layout') or self.kind.layout
        self.stage = kwargs.get('stage') or displayui.current(self.kind.layout.pitch_y)
        self.session = E.Session()                   # Explore / Filter… (movies)
        self.resolver = X.Resolver()
        start = kwargs.get('explore')                # (filter, movie key): a wall opened by Explore
        self.nested = start is not None              # ...from a view without its own wall
        if start:
            self.session.explore(*start)

    # ---- lifecycle -------------------------------------------------------------------------

    def onInit(self):
        if self.ready:
            return                       # back from playback: state is intact
        self.lock = threading.RLock()
        self.closing = False
        self.window_id = xbmcgui.getCurrentWindowId()
        # Display & aspect ratio: the layout for this screen and the CinemaScope band, if any
        # (open_wall built the XML for it).
        self.lay = self.layout
        self.sx = self.stage.sx
        self.pool_size = self.lay.pool_cols * self.lay.pool_rows
        self.camera = self.getControl(1000)
        self.frame = self.getControl(1001)
        self.panel = self.getControl(1900)
        self.status = self.getControl(1950)
        self.caption = self.getControl(1960)
        self.caption.setVisible(False)
        self.front = Pool(self, 10000, self.pool_size, self.lay, self.sx)
        self.back = Pool(self, 20000, self.pool_size, self.lay, self.sx)
        self.back.reset()
        n = next(_walls)
        self.prop_motion, self.prop_front = PROP_MOTION.format(n), PROP_FRONT.format(n)
        HOME.setProperty(self.prop_motion, '0.0')
        HOME.setProperty(self.prop_front, '0')
        self.frame_glide = Glide(self.frame, self.prop_motion, 0)
        self.cam_glide = Glide(self.camera, self.prop_motion, 1)
        self._place_view()
        self.frame.setVisible(False)
        self.frame_on = False
        self.panel.setVisible(False)
        self.reduced = menu.reduced_motion()
        HOME.setProperty(PROP_REDUCED, '1' if self.reduced else '')
        self.auto_shuffle = ADDON.getSettingBool('auto_shuffle')
        self.show_badges = not xbmc.getCondVisibility('Skin.HasSetting(KScapeHideFormatBadges)')
        self.library_gen = 0             # bumped by every full reload; stale results are dropped
        self.loading = False             # a full reload is running in the background
        self.list_reloaded = None        # the list view's callback for a reload it asked for
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
        self.front_token = 0
        self.shuffle_until = 0.0
        self.panel_cells = ()
        self.panel_shown = False
        self.shuffled_for = None
        self.last_input = time.time()
        self.heal_at = time.time() + HEAL_EVERY_S
        self.retries = {}                # poster url -> (attempts, next attempt time)

        self.status.setLabel('')                 # the logo says it is loading
        self.setProperty('kscape.loading', '1')
        self.group_sets = self._can_group() and ADDON.getSettingBool('group_sets')
        self.sets = {}                   # Kodi movie sets: setid -> title, artwork, plot
        if self.given:                   # a set's wall: the library the wall beneath has loaded
            (items, self.cast_complete), cached, total = self.given, None, len(self.given[0])
        else:
            items, self.cast_complete, cached, total = load_library(self.kind)
        if self.group_sets or self.movie_set is not None:
            self.sets = fetch_sets()

        self.all_movies = items
        visible = self._covers(self._visible(items))
        self.wall = Wall.column_major(visible, layout=self.lay)
        prop, key = remembered(self.kind)
        last = HOME.getProperty(prop) or str(state.load().get(key, ''))
        if self.nested:
            last = str(self.session.trail[-1][1])     # the movie explored from, if it is shown
        start = self.wall.cell_of(int(last)) if last.lstrip('-').isdigit() else None
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
        elif items and not self.cast_complete and not self.given:   # the wall beneath loads it
            threading.Thread(target=self._load_cast, args=(total, self.library_gen), daemon=True).start()
        view = self.start_view or (None if self.filtered else state.load().get(view_key(self.kind)))
        if self.start_view and not self.filtered:
            state.save(**{view_key(self.kind): self.start_view})
        if view == 'list' and items:
            self._open_list(back_home=True)   # chosen from Home, or in use when Kodi last closed

    # ---- display & aspect ratio -----------------------------------------------------------------

    def _place_view(self):
        """Put the wall in its view (the screen, or a CinemaScope band), black outside it, and
        the status, filter caption and now-playing chip inside it."""
        vx, vy, vw, vh = self.lay.view
        self.getControl(998).setPosition(vx, vy)
        masks = ((0, 0, G.SCREEN_W, vy), (0, vy + vh, G.SCREEN_W, G.SCREEN_H - vy - vh),
                 (0, vy, vx, vh), (vx + vw, vy, G.SCREEN_W - vx - vw, vh))
        for cid, (x, y, w, h) in zip((1971, 1972, 1973, 1974), masks):
            m = self.getControl(cid)
            on = w > 0 and h > 0
            if on:
                m.setPosition(x, y)
                m.setWidth(w)
                m.setHeight(h)
            m.setVisible(on)
        self.status.setPosition(vx + (vw - 1400) // 2, vy + (vh - 200) // 2)
        self.getControl(1951).setPosition(vx + (vw - 1200) // 2, vy + (vh - 225) // 2)
        self.caption.setPosition(vx, vy + vh - CAPTION_PX)
        for cid in (1961, 1963):
            self.getControl(cid).setWidth(vw)
        self.getControl(1962).setWidth(max(1, vw - 96 - np_chip.COUNT_W // 2))   # clear of the counter
        self.getControl(1965).setPosition(vx + vw - np_chip.COUNT_RIGHT - np_chip.COUNT_W,
                                          vy + vh - np_chip.COUNT_BOTTOM - np_chip.COUNT_H)
        self.getControl(1980).setPosition(vx + vw - CHIP_W - 28, vy + 26)

    def _show_status(self):
        """Loading done: an empty library or empty favourites says so; otherwise no status. The
        counter shows how many covers the wall has (of how many, when filtered)."""
        self._show_caption()
        self.setProperty('kscape.loading', '')
        count = self.kind.counter(self.shown_total, self.base_total)   # movies, a set's each counted
        if self.movie_set is not None and count:
            count = f'{self._set_title()}  ·  {count}'
        self.setProperty('kscape.count', count)
        if self.wall.movies():
            self.status.setLabel('')
        elif self.session and self.all_movies:
            self.status.setLabel(X.empty_text())
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

    # ---- Explore and filters -------------------------------------------------------------------

    def _show_caption(self):
        if self.session:
            self.getControl(1962).setLabel(X.describe(self.session.filters, len(self.wall.movies()),
                                                      self.all_movies))
        self.caption.setVisible(bool(self.session))

    def _library(self):
        """What Explore and the Filter menu choose from: the library as the wall shows it."""
        return self.kind.visible(self.all_movies)

    def _filters_changed(self, focus_key=None):
        """Show the movies the filters now leave, on `focus_key` when it is among them."""
        with self.lock:
            self._apply_library(self.all_movies, focus_key=focus_key)

    def _explore(self, f, origin):
        """An Explore filter chosen on `origin`'s info screen: the wall (or the list view, when
        it is the view in use) now shows the library's movies it matches. A favourites or
        collection wall opens a filtered wall of the whole library over itself instead."""
        if self.filtered:
            self._covered(lambda: open_wall(self.kind, explore=(f, origin)))
            self._after_favourites()
            return
        self.session.explore(f, origin)
        self._filters_changed(origin)

    def _filter_menu(self):
        with self.lock:
            current = self.wall.at(*self.focus)
            library = self._library()
            base = self._base(self.all_movies)
        if X.edit(self.session, library, lambda: self._apply_filters(base)):
            self._filters_changed(current.key if current else None)

    def _filter_back(self):
        """Back with filters: one step back (see explore.Session). Returns the movie whose
        Explore panel to reopen, or None. False when there was nothing to undo (Back leaves)."""
        if self.nested and len(self.session.trail) <= 1:
            return False
        step = self.session.back()
        if step is None:
            return False
        origin = step[1]
        self._filters_changed(origin)
        if origin is None:
            return None
        with self.lock:
            here = self.wall.at(*self.focus)
        return origin if here and here.key == origin else None

    def _apply_filters(self, items):
        filters = self.session.filters
        if not filters:
            return items
        return E.apply(filters, items, self.all_movies, self.resolver.resolve(filters))

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
            elif aid in (SELECT + PLAY) and not empty and MS.is_set(self.wall.at(*self.focus)):
                overlay = 'set'
            elif aid in SELECT and not empty:
                overlay = 'details'
            elif aid in PLAY and not empty:
                item = self.wall.at(*self.focus)
                if item:
                    self._remember(item)
                    overlay = 'play'
            elif aid in BACK:
                overlay = 'back'      # filters first; else one press back to Home (C -> Undo shuffle undoes)
            elif aid in MENU:
                overlay = self._menu()
        # Opened outside the lock: the wall's background work waits on `paused`, not the lock.
        if overlay == 'back':
            origin = self._filter_back() if self.session else False
            if origin is False:
                self._close()
            elif origin is not None:
                self._open_details(page='explore')
        elif overlay == 'details':
            self._open_details()
        elif overlay == 'set':
            self._open_set(self.wall.at(*self.focus))
        elif overlay == 'filter':
            self._filter_menu()
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
            self.caption.setVisible(False)      # it would show below the info screen's edge
        try:
            return fn()
        finally:
            with self.lock:
                self.paused = False
                self.last_input = time.time()
                self._show_caption()

    def _open_details(self, page=None):
        item = self.wall.at(*self.focus)
        if not item:
            return
        self._remember(item)
        library = self._library() if self.kind.explores else None
        follow = self._covered(lambda: self.kind.activate(item, self.favs, library=library, page=page,
                                                          resolver=self.resolver))
        self._after_favourites()
        from . import actions
        actions.take_changes()              # the monitor has patched the wall (actions.announce_change)
        if follow == 'search':
            self._search()
        elif isinstance(follow, tuple) and follow[0] == 'explore':
            self._explore(follow[1], item.key)

    def _open_list(self, back_home=False):
        """The list view over the wall. Opened as the view itself (from Home), Back there goes
        straight back to Home; opened from the wall's menu, Back returns to the wall."""
        while self._list_once(back_home) == 'favourites':
            self._open_favourites(view='list')         # C -> Favourites in the list: then back to it

    def _list_once(self, back_home):
        with self.lock:
            current = self.wall.at(*self.focus)
            items = self._visible(self.all_movies)          # library order, whatever the wall's
            if MS.is_set(current):                          # the list has no set covers
                current = next(iter(MS.members_of(items, MS.set_id(current))), None)
            library = self.kind.visible(self.all_movies)
        if not self.filtered:
            state.save(**{view_key(self.kind): 'list'})
        seen = self.session.version
        link = ExploreLink(self) if self.kind.explores else None
        result, key = self._covered(lambda: show_list(self.kind, items, current.key if current else None,
                                                      self.favs, library=library, store=self.store,
                                                      collection=self.collection, copies=self._copies,
                                                      back='exit' if back_home else 'wall', explore=link,
                                                      host=ListHost(self)))
        self.reduced = menu.reduced_motion()        # the list's menu may have toggled these
        self.auto_shuffle = ADDON.getSettingBool('auto_shuffle')
        if self.session.version != seen:
            self._filters_changed(key)              # filtered in the list: the wall follows
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
            elif result == 'exit':
                self._close()
        return result

    def _view_scenes(self):
        """View Scenes: the Collections view on the Scenes tab, at this title's first scene."""
        from .collectionwindow import show_collections
        self._covered(lambda: show_collections(self.kind, cid='scenes', focus=self.scene_focus))

    def _open_favourites(self, view='wall'):
        """This library's favourites, over this wall (in the list view, with `view`); Back
        returns here."""
        self._covered(lambda: open_wall(self.kind, view=view, favourites=True))
        self._after_favourites()
        self._after_collections()

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
            library = self.kind.visible(self.all_movies)
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
        # Frame and camera glides first, started together by one property write; the covers
        # the camera brings into the pool are bound after (they are still off-screen).
        frame = self._frame_plan(animate=True)
        cam = self._cam_plan(camera_target(self.wall, self.focus))
        self._commit(frame=frame, cam=cam)
        self._rebind(self.front)

    # ---- favourites ------------------------------------------------------------------------

    def _copies(self, item):
        """The library entries a cover stands for: itself, plus merged duplicate copies."""
        if not self.kind.merges:
            return [item]
        if getattr(self, '_copy_of', (None,))[0] is not self.all_movies:
            index = {}
            for group in copy_groups(self.all_movies):      # once per library change, not per cover
                for m in group:
                    index[m.key] = group
            self._copy_of = (self.all_movies, index)
        return self._copy_of[1].get(item.key) or [item]

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

    def _motion(self, tween, ms):
        """(ms, tween, ease) of a glide: Reduce motion keeps a short plain ease."""
        if self.reduced:
            return REDUCED_MS, 'sine', ease_out_sine
        return ms, tween, ease_out_back if tween == 'back' else ease_out_cubic

    def _commit(self, frame=None, cam=None):
        """Install planned glides (Glide.plan) and start them with one property write."""
        if frame is not None:
            self.frame.setAnimations(frame)
        if cam is not None:
            self.camera.setAnimations(cam)
        HOME.setProperty(self.prop_motion, f'{self.frame_glide.token}.{self.cam_glide.token}')
        if frame is not None and not self.frame_on:
            self.frame.setVisible(True)
            self.frame_on = True

    def _settle(self, now):
        """Idle wall: finished glides become static placements (Glide.settle)."""
        self.frame_glide.settle(now)
        self.cam_glide.settle(now)

    def _cam_plan(self, target, animate=True):
        lay = self.lay
        now = time.time()
        g = self.cam_glide
        v = g.visual(now) if g.pos is not None else (-self.cam[0], -self.cam[1])
        vis = (-v[0], -v[1])                         # camera drawn now (wall pixels)
        # Never lag further than the pool's slack, or the screen edge would show empty cells.
        dx = max(-lay.pitch_x * 1.3, min(lay.pitch_x * 1.3, target[0] - vis[0]))
        dy = max(-lay.pitch_y * 1.1, min(lay.pitch_y * 1.1, target[1] - vis[1]))
        animate = animate and (abs(dx) > 0.5 or abs(dy) > 0.5)
        self.cam = target
        ms, tween, ease = self._motion('cubic', G.PAN_MS)
        return g.plan((-target[0], -target[1]), now, start=(dx - target[0], dy - target[1]),
                      ms=ms if animate else 0, tween=tween, ease=ease)

    def _pan(self, target, animate=True):
        self._commit(cam=self._cam_plan(target, animate))
        self._rebind(self.front)

    def _origin(self):
        """Top-left grid cell of the pool window around the camera centre."""
        lay = self.lay
        vw, vh = G.view_size(lay)
        cx = self.cam[0] + vw / 2.0
        cy = self.cam[1] + vh / 2.0
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
            pool.bind(k, cell, item, self.kind.fallback(item), self._is_favourite(item),
                      self.kind.cover_badge(item, self.show_badges))

    def _rebind(self, pool, wall=None):
        wall = wall or self.wall
        for k, cell in self._slot_cells():
            self._bind(pool, k, cell, wall.at(*cell))

    def _cell_xy(self, cell):
        return cell_origin(*cell, layout=self.lay)

    def _frame_plan(self, animate=False):
        """The focus frame's glide to the focused cell, from wherever it is drawn now."""
        x, y = self._cell_xy(self.focus)
        ms, tween, ease = self._motion(G.FRAME_TWEEN, G.FRAME_MS)
        return self.frame_glide.plan((x - G.fx(self.lay), y - self.lay.frame), time.time(),
                                     ms=ms if animate else 0, tween=tween, ease=ease)

    def _set_frame(self, animate=False):
        """Move the focus frame; animated moves glide from wherever the frame is drawn now."""
        self._commit(frame=self._frame_plan(animate))

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
        right_on = x + lay.cover_w + G.fx(lay) + G.panel_w(lay) - self.cam[0] <= G.view_size(lay)[0]
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
            px = x + lay.cover_w + G.fx(lay)                       # frame's right edge
        self.setProperty('kscape.panel.side', 'left' if cells[0][0] < c else 'right')   # entrance direction
        self.panel.setPosition(px, y - lay.frame)
        title, body = self.kind.panel(item)
        if lay.name == 'square':
            # Album title on one or two lines (a textbox), the artist right below it.
            self.getControl(1901).setText(title)
            lines = min(2, estimate_lines(title, G.panel_w(lay) - 2 * PANEL_PAD, PANEL_TITLE_PX))
            self.getControl(1902).setPosition(PANEL_PAD, lay.frame + 26 + lines * PANEL_TITLE_LINE + 10)
        else:
            self.getControl(1901).setLabel(title)
        self.getControl(1902).setText(body)
        if self.kind.explores:
            self._panel_facts(item)
        self.panel.setVisible(True)
        self.panel_cells = tuple(cells)
        self.panel_shown = True

    def _panel_facts(self, item):
        """Resolution badge, TMDB score and Tomatometer under the synopsis (when known)."""
        h = 26
        self.setProperty('p.res', badges.image(item.resolution) if item.resolution else '')
        X = lambda v: max(1, int(round(v / self.sx)))    # badges keep their shape on any screen
        if item.resolution:
            self.getControl(1911).setWidth(X(badges.width(item.resolution, h)))
        self.setProperty('p.tmdb', f'{item.tmdb:.1f}' if item.tmdb else '')
        self.getControl(1912).setWidth(X(badges.width('tmdb', h)))
        self.getControl(1914).setWidth(X(h))

        def found(rt):
            with self.lock:
                if self.panel_shown and self.wall.at(*self.focus) is item:
                    self._panel_rt(rt)
        self._panel_rt(ratings.lookup(item, found))

    def _panel_rt(self, rt):
        self.setProperty('p.rt', f'{rt}%' if rt else '')
        self.setProperty('p.rticon', badges.image('rt_fresh' if rt >= 60 else 'rt_rotten') if rt else '')

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
                if idle >= SETTLE_S:
                    self._settle(now)
                if self.pending_library is not None and idle >= 1.0 and not self.shuffle_until:
                    items, self.pending_library = self.pending_library, None
                    self._apply_library(items)
                    continue
                heal = idle >= 2.0 and now >= self.heal_at and not self.shuffle_until
                if heal:
                    self.heal_at = now + HEAL_EVERY_S
                item = self.wall.at(*self.focus)
                if item and not self.panel_shown and idle >= G.PANEL_DELAY_S:
                    self._show_panel()
                if (item and self.auto_shuffle and idle >= G.SHUFFLE_DELAY_S and not self.shuffle_until
                        and self.shuffled_for != item.key and len(self.wall.movies()) > 1):
                    self.shuffled_for = item.key
                    self._shuffle_related(item)
            if heal:
                self._heal_posters()

    def _heal_posters(self):
        """Reload covers whose poster never arrived. Kodi loads a cover's artwork once; if the
        download failed (a network hiccup), the cover stays a grey card for the rest of the
        session. So, while the wall is idle, the posters on show for a while are checked against
        Kodi's texture cache (one query) and any still missing is asked for again, a few times,
        further apart each time."""
        now = time.time()
        with self.lock:
            pool = self.front
            slots = [(k, self.wall.at(*pool.cell[k])) for k in range(self.pool_size)
                     if pool.visible[k] and pool.shown[k] is not None and pool.cell[k]
                     and now - pool.bound_at[k] >= HEAL_AFTER_S]
            slots = [(k, item.poster) for k, item in slots if item is not None and item.poster
                     and item.poster.startswith('image://')]
        urls = list(dict.fromkeys(url for _, url in slots))
        if not urls:
            return
        due = [u for u in urls if self.retries.get(u, (0, 0.0))[1] <= now
               and self.retries.get(u, (0, 0.0))[0] < HEAL_RETRIES]
        if not due:
            return
        cached = {t.get('url') for t in rpc('Textures.GetTextures', {
            'properties': ['url'],
            'filter': {'or': [{'field': 'url', 'operator': 'is', 'value': u} for u in due]}}).get('textures', [])}
        missing = [u for u in due if u not in cached]
        for u in urls:
            if u in cached:
                self.retries.pop(u, None)
        if not missing:
            return
        with self.lock:
            if self.paused or self.closing or pool is not self.front:
                return
            again = [(k, url) for k, url in slots if url in missing and pool.shown[k] is not None]
            for k, url in again:
                pool.reload_poster(k, url, 0)
        time.sleep(0.2)                              # a few frames: Kodi drops the old texture
        with self.lock:
            if self.closing or pool is not self.front:
                return
            for k, url in again:
                pool.reload_poster(k, url, 1)
            for u in missing:
                n = self.retries.get(u, (0, 0.0))[0]
                self.retries[u] = (n + 1, now + HEAL_EVERY_S * 2 ** n)
        xbmc.log(f'kscape.wall: asked again for {len(missing)} poster(s) not in the texture cache', xbmc.LOGINFO)

    # ---- menu and library changes -------------------------------------------------------------

    def _menu(self):
        tr = ADDON.getLocalizedString
        item = self.wall.at(*self.focus)
        view = []
        if item:
            view.append(('list', tr(menu.S_VIEW), tr(menu.S_COVER_WALL)))
        if self._can_group():
            view.append(menu.toggle('groupsets', menu.S_GROUP_SETS, self.group_sets))
        view += [menu.toggle('motion', menu.S_REDUCE_MOTION, self.reduced),
                 menu.toggle('auto', menu.S_AUTO_SHUFFLE, self.auto_shuffle)]
        misc = [('search', tr(menu.S_SEARCH))]
        if not self.favourites_only:
            misc.append(('favourites', tr(32187)))
        if self.kind.explores and self.all_movies:
            misc.append(('filter', tr(X.S_FILTER_MENU)))
            if self.session:
                misc.append(('clearfilters', tr(X.S_CLEAR)))
        actions = []
        if self.history:
            actions.append(('undo', tr(32295)))
        if item:
            actions.append(('shuffle', tr(32021)))
        actions.append(('reload', tr(32024)))
        if item and not MS.is_set(item):              # a set cover is no single movie
            actions += menu.favourite_entries(item, self.favs, self._is_favourite(item))
            actions.append(('collect', tr(collectionui.S_COLLECT)))
            if self.collection is not None and self.store.get(self.collection):
                actions.append(('uncollect', tr(32165).format(collectionui.name_of(self.collection, self.store))))
            actions += S.item_entries(self.kind, item, self.scenes)
        actions.append(menu.exit_entry(self))
        choice = menu.show_sections([(menu.S_VIEW_OPTIONS, view), (menu.S_MISC_OPTIONS, misc),
                                     (menu.S_ACTIONS, actions)])
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
        elif choice in ('search', 'list', 'favourites', 'filter'):
            return choice
        elif choice == 'clearfilters':
            self.session.clear()
            self._apply_library(self.all_movies)
        elif choice == 'shuffle':
            self._finish_shuffle()
            if not self.panel_shown:
                self._show_panel()
            self.shuffled_for = item.key
            self._shuffle_related(item)
        elif choice == 'auto':
            self.auto_shuffle = not self.auto_shuffle
            menu.set_auto_shuffle(self.auto_shuffle)
        elif choice == 'groupsets':
            self._toggle_grouping()
        elif choice == 'motion':
            self.reduced = not self.reduced
            menu.set_reduced_motion(self.reduced)
        elif choice == 'reload':
            self._reload()
        elif choice == 'exit':
            self._close()

    def _reload(self):
        """Reload Library: drop the cache and re-read the library in the background."""
        cache.discard(self.kind.name)
        self._start_reload()

    def _visible(self, items):
        """What the wall shows: _base() narrowed by the filters (Explore, Filter…)."""
        base = self._base(items)
        self.base_total = len(base)                  # the counter: "shown of base"
        shown = self._apply_filters(base)
        self.shown_total = len(shown)
        return shown

    # ---- Group by Collection (Kodi movie sets) -----------------------------------------------------

    def _can_group(self):
        """Group by Collection applies to the movies cover wall only (not favourites, your own
        collections or a set's wall)."""
        return (self.kind.name == 'movies' and not self.favourites_only and self.collection is None
                and self.movie_set is None)

    def _covers(self, visible):
        """The wall's covers: `visible`, with each movie set as one cover when grouping."""
        if not self.group_sets:
            return visible
        return MS.group(visible, self.sets, self.kind.count_text)

    def _set_title(self):
        info = self.sets.get(self.movie_set) or {}
        if info.get('title'):
            return info['title']
        return next((m.setname for m in self.all_movies if m.setid == self.movie_set and m.setname), '')

    def _open_set(self, item):
        """Select on a set cover: a cover wall of the set's movies over this one; Back returns."""
        self._remember(item)
        library = (self.all_movies, self.cast_complete)
        self._covered(lambda: open_wall(self.kind, view='wall', movie_set=MS.set_id(item), library=library))
        self._after_favourites()
        self._after_collections()

    def _toggle_grouping(self):
        self.group_sets = not self.group_sets
        ADDON.setSettingBool('group_sets', self.group_sets)
        if self.group_sets and not self.sets:
            self.sets = fetch_sets()
        self._apply_library(self.all_movies)

    def _base(self, items):
        """The wall's items before filters: in favourites mode only favourites (any copy of a
        merged movie counts), in collection mode the collection's; separate copies of one film
        share a cover (kinds.visible)."""
        if self.collection is not None:
            shown = self.kind.visible(items)
            return [m for m, _ in collectionui.members(self.collection, self.store, items, shown, self.new_days)]
        if self.movie_set is not None:
            return self.kind.visible(MS.members_of(items, self.movie_set))
        if self.favourites_only:
            items = [m for m in items if self.favs.contains(m)]
        return self.kind.visible(items)

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
            reloaded, self.list_reloaded = self.list_reloaded, None
            if reloaded:                     # asked for by the list view on top: apply it now
                self.pending_library = None
                self._apply_library(items)
                shown, library = self._visible(self.all_movies), self.kind.visible(self.all_movies)
        if reloaded:
            reloaded(shown, library)
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
            if self.kind.has_extra:               # cast and versions are not in a single-movie fetch
                item = self.kind.carry(item, current)
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

    def _apply_library(self, items, focus_key=None):
        """Rebuild the wall from `items`, keeping the focused item (or `focus_key`) when it
        still exists."""
        self._finish_shuffle()
        current = self.wall.at(*self.focus)
        if focus_key is not None:
            current = next((m for m in items if m.key == focus_key), current)
        self.all_movies = items
        visible = self._covers(self._visible(items))
        self.wall = Wall.column_major(visible, layout=self.lay)
        self.history = []
        self.front.shown = [None] * self.pool_size     # artwork may have changed
        cell = self.wall.cell_of(current.key) if current else None
        if cell is None and current and MS.is_set(current):
            # Grouping turned off: the set's first movie.
            first = MS.members_of(visible, MS.set_id(current))
            cell = self.wall.cell_of(first[0].key) if first else None
        elif cell is None and current and getattr(current, 'setid', 0):
            cell = self.wall.cell_of(-current.setid)   # grouped now: its set's cover
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
            self.frame_on = False
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
        on = _is(self.prop_front, tok)
        before = _is(self.prop_front, tok - 1)       # the value until the flip below
        rng = random.Random(tok)
        cx, cy = self.cam
        vw, vh = G.view_size(lay)
        view = (cx, cy, cx + vw, cy + vh)
        margin = lay.pitch_x
        longest = 0
        instant = self.reduced

        # The selected cover (and its frame) stays put; nothing flies across it (wallmodel.detour).
        anchor_cell = new.cell_of(anchor_key) if anchor_key is not None else None
        if anchor_cell:
            ax, ay = self._cell_xy(anchor_cell)
            keep_out = (ax - G.fx(lay), ay - lay.frame, ax + lay.cover_w + G.fx(lay), ay + lay.cover_h + lay.frame)
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
        # The hold names the token before the flip (not "not this one"), so once the pool is
        # retired its stale animations stay inert (Pool.reset no longer clears them).
        hold = ('Conditional', f'effect=fade start=0 end=0 time=0 reversible=false condition={before}')
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

        HOME.setProperty(self.prop_front, str(tok))  # one flip starts every animation above
        self.wall = new
        self.front, self.back = self.back, self.front
        self.shuffle_until = time.time() + longest / 1000.0 + 0.05

    def _finish_shuffle(self):
        """Retire the old front buffer once its departing covers are gone (or immediately)."""
        if self.shuffle_until:
            self.back.reset()
            self.shuffle_until = 0.0


class ListHost:
    """What the list view opened over a wall asks of it: the window beneath (the menu's exit
    leads where closing the wall does), whether it can show Favourites, and Reload Library."""

    def __init__(self, wall):
        self.wall = wall

    @property
    def favourites(self):
        return not self.wall.favourites_only

    def reload(self, done):
        """Re-read the library; `done(shown, library)` runs (on a background thread) once the
        wall has it."""
        with self.wall.lock:
            self.wall.list_reloaded = done
            self.wall._reload()


class ExploreLink:
    """What the list view opened over a movie wall uses to share its filters: the movies they
    leave, the caption, the Filter menu, Explore and Back (window.py keeps the state)."""

    def __init__(self, wall):
        self.wall = wall
        self.resolver = wall.resolver

    @property
    def active(self):
        return bool(self.wall.session)

    @property
    def in_place(self):
        """Explore filters this view (a favourites or collection view opens a library wall)."""
        return not self.wall.filtered

    def library(self):
        return self.wall._library()

    def items(self):
        with self.wall.lock:
            return self.wall._visible(self.wall.all_movies)

    def total(self):
        """How many movies the wall has before its filters."""
        return self.wall.base_total

    def caption(self, count):
        s = self.wall.session
        return X.describe(s.filters, count, self.wall.all_movies) if s else ''

    def edit(self):
        with self.wall.lock:
            base = self.wall._base(self.wall.all_movies)
        return X.edit(self.wall.session, self.library(), lambda: self.wall._apply_filters(base))

    def explore(self, f, origin):
        self.wall.session.explore(f, origin)

    def clear(self):
        self.wall.session.clear()

    def back(self):
        """As WallWindow._filter_back, without touching the wall (it follows when the list
        closes): the movie key to reopen Explore on, None, or False (nothing to undo)."""
        s = self.wall.session
        if not s or (self.wall.nested and len(s.trail) <= 1):
            return False
        step = s.back()
        return False if step is None else step[1]


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


def wall_xml(kind):
    """(script path, XML file, layout, stage) of the wall for the screen Kodi draws on now: the
    shipped XML on a 16:9 screen, else XML built for the adapted layout (wallxml.prepare)."""
    stage = displayui.current(kind.layout.pitch_y)
    layout = G.adapt(kind.layout, stage)
    path = ADDON.getAddonInfo('path')
    if layout is kind.layout:
        return path, kind.wall_xml, layout, stage
    from . import wallxml
    try:
        root, name = wallxml.prepare(layout, stage.sx, path, xbmcvfs.translatePath(ADDON.getAddonInfo('profile')))
    except OSError as e:
        xbmc.log(f'kscape: could not write the adapted wall ({e}); using the 16:9 one', xbmc.LOGWARNING)
        return path, kind.wall_xml, kind.layout, stage._replace(sx=1.0, view=(0, 0, G.SCREEN_W, G.SCREEN_H))
    xbmc.log(f'kscape.wall: {layout.name} layout for this screen: covers {layout.cover_w}x{layout.cover_h}, '
             f'{layout.pool_cols}x{layout.pool_rows} slots, view {layout.view}, stretch {stage.sx:.3f}', xbmc.LOGINFO)
    return root, name, layout, stage


def open_wall(kind, view=None, favourites=False, collection=None, explore=None, movie_set=None,
              library=None):
    """Run the wall for `kind` (filtered by an Explore (filter, movie key) pair, or showing one
    Kodi movie set, if given). `library`: (items, cast complete) already loaded, if any."""
    root, name, layout, stage = wall_xml(kind)
    window = WallWindow(name, root, 'Default', '1080i', kind=kind, view=view, favourites=favourites,
                        collection=collection, explore=explore, layout=layout, stage=stage,
                        movie_set=movie_set, library=library)
    modal.run(window)
    del window
