"""Cover wall window: camera-follow navigation and the animated related-cover shuffle.

Kodi cannot move items inside its list containers, so the wall is a pool of image slots that
the window positions itself. Motion is expressed as runtime animations (Control.setAnimations)
whose conditions reference a Home window property; flipping that property starts every
prepared animation in the same frame.

Two slot pools (A, B) double-buffer the shuffle: the new arrangement is bound into the back
pool while it is held transparent, then one property change hides the old covers that
re-appear elsewhere, flies the departing ones off-screen and flies the new ones into place.
"""
import json
import random
import threading
import time
from dataclasses import replace

import xbmc
import xbmcaddon
import xbmcgui

from . import geometry as G
from . import cache, state
from .details import show_details
from .library import fetch_cast, fetch_movie, fetch_movies, library_total, play, play_trailer
from .listwindow import show_list
from .model import Movie, merge_duplicates
from .skins import choose_skin
from .ranking import rank_related
from .wallmodel import (Wall, camera_target, cell_origin, clip_outside, ease_out_back,
                        ease_out_cubic)

POOL = G.POOL_COLS * G.POOL_ROWS
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
PROP_LAST = 'kscape.lastmovie'
PROP_REDUCED = 'kscape.reduced'         # read by the info screen's slide-in animation


def _is(prop, value):
    return f'String.IsEqual(Window(Home).Property({prop}),{value})'


class Pool:
    """One set of recycled cover slots. Slot k always serves grid cells congruent to it."""

    def __init__(self, win, base):
        self.slots = [win.getControl(base + k) for k in range(POOL)]
        self.texts = [win.getControl(base + 200 + k) for k in range(POOL)]
        self.posters = [win.getControl(base + 400 + k) for k in range(POOL)]
        self.badges = [win.getControl(base + 600 + k) for k in range(POOL)]
        self.badge_labels = [win.getControl(base + 800 + k) for k in range(POOL)]
        self.badge_shown = [True] * POOL
        self.cell = [None] * POOL
        self.shown = [None] * POOL      # movieid currently bound
        self.visible = [True] * POOL    # XML default

    def bind(self, k, cell, movie):
        if movie is None:
            self.set_visible(k, False)
            self.cell[k], self.shown[k] = cell, None
            return
        if self.cell[k] != cell:
            self.slots[k].setPosition(*cell_origin(*cell))
            self.cell[k] = cell
        if self.shown[k] != movie.movieid:
            self.posters[k].setImage(movie.poster)
            self.texts[k].setText('' if movie.poster else f'{movie.title}[CR]({movie.year})')
            if movie.badge:
                self.badge_labels[k].setLabel(movie.badge)
            if self.badge_shown[k] != bool(movie.badge):
                self.badges[k].setVisible(bool(movie.badge))
                self.badge_shown[k] = bool(movie.badge)
            self.shown[k] = movie.movieid
        self.set_visible(k, True)

    def set_visible(self, k, on):
        if self.visible[k] != on:
            self.slots[k].setVisible(on)
            self.visible[k] = on

    def reset(self):
        """Hide every slot and drop its animations (pool becomes the back buffer)."""
        for k in range(POOL):
            self.slots[k].setAnimations([])
            self.set_visible(k, False)


class LibraryMonitor(xbmc.Monitor):
    """Reports library changes: whole-library ones (scan, clean, removal) and single movie edits
    (refreshed metadata, or the play count and resume point Kodi saves after watching)."""

    def __init__(self, on_change, on_movie):
        super().__init__()
        self.on_change = on_change
        self.on_movie = on_movie

    def onScanFinished(self, library):
        if library == 'video':
            self.on_change()

    def onCleanFinished(self, library):
        if library == 'video':
            self.on_change()

    def onNotification(self, sender, method, data):
        if method not in ('VideoLibrary.OnUpdate', 'VideoLibrary.OnRemove'):
            return
        try:
            info = json.loads(data or '{}')
        except ValueError:
            return
        item = info.get('item', info)
        if item.get('type') != 'movie' or not item.get('id'):
            return
        if method == 'VideoLibrary.OnUpdate':
            self.on_movie(int(item['id']))
        else:
            self.on_change()


class WallWindow(xbmcgui.WindowXML):
    ready = False
    pending_skin = None              # set when the user picks another skin; acted on after close

    # ---- lifecycle -------------------------------------------------------------------------

    def onInit(self):
        if self.ready:
            return                       # back from playback: state is intact
        self.lock = threading.RLock()
        self.closing = False
        self.camera = self.getControl(1000)
        self.frame = self.getControl(1001)
        self.panel = self.getControl(1900)
        self.status = self.getControl(1950)
        self.front, self.back = Pool(self, 10000), Pool(self, 20000)
        for k in range(POOL):
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
        self.pending_library = None      # reloaded movies waiting for an idle moment
        self.paused = False              # the info screen or list view is on top of the wall
        self.monitor = LibraryMonitor(self._start_reload, self._movie_changed)

        self.status.setLabel(ADDON.getLocalizedString(32001))
        t0 = time.perf_counter()
        total = library_total()
        cached = cache.load(total) if total else None
        if cached:
            movies = [Movie.from_cache(d) for d in cached['movies']]
            self.cast_complete = cached['complete']
        else:
            movies = fetch_movies()
            self.cast_complete = False
        xbmc.log(f'kscape.wall: {len(movies)} movies from {"cache" if cached else "library"} in '
                 f'{1000 * (time.perf_counter() - t0):.0f} ms', xbmc.LOGINFO)
        if not movies:
            self.status.setLabel(ADDON.getLocalizedString(32002))
            self.ready = True
            return
        self.status.setLabel('')

        self.all_movies = movies         # every library entry; the wall may merge duplicates
        self.wall = Wall.column_major(self._visible(movies))
        self.history = []                # (wall, focus) before each shuffle, for Back
        self.cam = (0, 0)
        self.cam_anim = None             # (start time, start camera, duration ms)
        self.cam_token = 0
        self.front_token = 0
        self.shuffle_until = 0.0
        self.panel_cells = ()
        self.panel_shown = False
        self.shuffled_for = None
        self.last_input = time.time()

        last = HOME.getProperty(PROP_LAST) or str(state.load().get('last_movie', ''))
        start = self.wall.cell_of(int(last)) if last.isdigit() else None
        self.focus = start or (0, 0)
        self._set_frame()
        self._pan(camera_target(self.wall, self.focus), animate=False)
        self.ready = True
        threading.Thread(target=self._dwell_loop, daemon=True).start()
        if cached and cached['stale']:
            self._start_reload()
        elif not self.cast_complete:
            threading.Thread(target=self._load_cast, args=(total, self.library_gen), daemon=True).start()
        if state.load().get('view') == 'list':
            self._open_list()             # the list view was in use when Kodi last closed

    def _close(self):
        self.closing = True
        movie = self.wall.at(*self.focus) if getattr(self, 'wall', None) else None
        if movie:
            self._remember(movie)
        self.close()

    def _remember(self, movie):
        HOME.setProperty(PROP_LAST, str(movie.movieid))
        state.save(last_movie=movie.movieid)

    # ---- input -----------------------------------------------------------------------------

    def onAction(self, action):
        aid = action.getId()
        if not self.ready:
            if aid in BACK:
                self._close()
            return
        if not hasattr(self, 'wall'):
            if aid in BACK:
                self._close()             # empty library
            return
        overlay = None
        with self.lock:
            if aid in MOVES:
                self._move(*MOVES[aid])
            elif aid in SELECT:
                overlay = 'details'
            elif aid in PLAY:
                movie = self.wall.at(*self.focus)
                if movie:
                    self._remember(movie)
                    play(movie)
            elif aid in BACK:
                if self.history:
                    self._undo()
                else:
                    self._close()
            elif aid in MENU:
                overlay = self._menu()
        # Opened outside the lock: the wall's background work waits on `paused`, not the lock.
        if overlay == 'details':
            self._open_details()
        elif overlay == 'list':
            self._open_list()

    # ---- info screen and list view -------------------------------------------------------------

    def _open_details(self):
        with self.lock:
            movie = self.wall.at(*self.focus)
            if not movie:
                return
            self.paused = True
            self._hide_panel()
        try:
            choice, details = show_details(movie)
        finally:
            with self.lock:
                self.paused = False
                self.last_input = time.time()
        if choice in ('play', 'resume'):
            self._remember(movie)
            play(movie, resume=choice == 'resume')
        elif choice == 'trailer' and details and details.get('trailer'):
            play_trailer(details['trailer'])

    def _open_list(self):
        with self.lock:
            self.paused = True
            self._hide_panel()
            current = self.wall.at(*self.focus)
            movies = self._visible(self.all_movies)
        state.save(view='list')
        try:
            result, movieid = show_list(movies, current.movieid if current else None)
        finally:
            with self.lock:
                self.paused = False
                self.last_input = time.time()
        with self.lock:
            cell = self.wall.cell_of(movieid) if movieid is not None else None
            if cell and cell != self.focus:
                self._finish_shuffle()
                self.focus = cell
                self._set_frame()
                self._pan(camera_target(self.wall, self.focus), animate=False)
            if result == 'wall':
                state.save(view='wall')
            elif result == 'skin':
                skin = choose_skin()
                if skin:
                    self.pending_skin = skin
                    self._close()
            elif result == 'exit':
                self._close()

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

    # ---- camera ----------------------------------------------------------------------------

    def _visual_cam(self, now):
        if not self.cam_anim:
            return self.cam
        t0, frm, dur = self.cam_anim
        e = ease_out_cubic((now - t0) * 1000.0 / dur) if dur else 1.0
        return (frm[0] + (self.cam[0] - frm[0]) * e, frm[1] + (self.cam[1] - frm[1]) * e)

    def _pan(self, target, animate=True):
        now = time.time()
        vis = self._visual_cam(now)
        # Never lag further than the pool's slack, or the screen edge would show empty cells.
        dx = max(-G.PITCH_X * 1.3, min(G.PITCH_X * 1.3, target[0] - vis[0]))
        dy = max(-G.PITCH_Y * 1.1, min(G.PITCH_Y * 1.1, target[1] - vis[1]))
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
        cx = self.cam[0] + G.SCREEN_W / 2.0
        cy = self.cam[1] + G.SCREEN_H / 2.0
        return int(cx // G.PITCH_X) - G.POOL_COLS // 2, int(cy // G.PITCH_Y) - G.POOL_ROWS // 2

    def _slot_cells(self):
        c0, r0 = self._origin()
        for k in range(POOL):
            i, j = k % G.POOL_COLS, k // G.POOL_COLS
            yield k, (c0 + (i - c0) % G.POOL_COLS, r0 + (j - r0) % G.POOL_ROWS)

    def _rebind(self, pool, wall=None):
        wall = wall or self.wall
        for k, cell in self._slot_cells():
            pool.bind(k, cell, wall.at(*cell))

    def _visual_frame(self, now):
        if not self.frame_anim:
            return self.frame_pos
        t0, frm, dur = self.frame_anim
        p = (now - t0) * 1000.0 / dur if dur else 1.0
        e = ease_out_back(p) if G.FRAME_TWEEN == 'back' else ease_out_cubic(p)
        return (frm[0] + (self.frame_pos[0] - frm[0]) * e, frm[1] + (self.frame_pos[1] - frm[1]) * e)

    def _set_frame(self, animate=False):
        """Move the focus frame; animated moves glide from wherever the frame is drawn now."""
        x, y = cell_origin(*self.focus)
        target = (x - G.FRAME, y - G.FRAME)
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
        movie = self.wall.at(*self.focus)
        if not movie:
            return
        c, r = self.focus
        left_x = cell_origin(c - G.PANEL_CELLS, r)[0] - self.cam[0]
        if left_x >= 0 and c - G.PANEL_CELLS >= 0:
            cells = [(c - i, r) for i in range(1, G.PANEL_CELLS + 1)]
        else:
            cells = [(c + i, r) for i in range(1, G.PANEL_CELLS + 1)]
        x, y = cell_origin(c, r)
        if cells[0][0] < c:
            px = cell_origin(c - G.PANEL_CELLS, r)[0]           # far cell's left edge
        else:
            px = x + G.COVER_W + G.FRAME                       # frame's right edge
        self.panel.setPosition(px, y - G.FRAME)
        self.getControl(1901).setLabel(movie.title)
        self.getControl(1902).setText(movie.plot)
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
                if self.paused or xbmc.getCondVisibility('Player.HasVideo'):
                    self.last_input = now     # wall is covered: stay idle
                    continue
                if self.shuffle_until and now >= self.shuffle_until:
                    self._finish_shuffle()
                idle = now - self.last_input
                if self.pending_library is not None and idle >= 1.0 and not self.shuffle_until:
                    movies, self.pending_library = self.pending_library, None
                    self._apply_library(movies)
                    continue
                if not self.panel_shown and idle >= G.PANEL_DELAY_S:
                    self._show_panel()
                movie = self.wall.at(*self.focus)
                if (movie and self.auto_shuffle and idle >= G.SHUFFLE_DELAY_S and not self.shuffle_until
                        and self.shuffled_for != movie.movieid):
                    self.shuffled_for = movie.movieid
                    self._shuffle_related(movie)

    # ---- menu and library changes -------------------------------------------------------------

    def _menu(self):
        on_off = lambda flag: ADDON.getLocalizedString(32030 if flag else 32031)
        items = [
            ('list', ADDON.getLocalizedString(32071)),
            ('shuffle', ADDON.getLocalizedString(32021)),
            ('auto', ADDON.getLocalizedString(32022).format(on_off(self.auto_shuffle))),
            ('motion', ADDON.getLocalizedString(32023).format(on_off(self.reduced))),
            ('merge', ADDON.getLocalizedString(32029).format(on_off(self.merge))),
            ('reload', ADDON.getLocalizedString(32024)),
            ('skin', ADDON.getLocalizedString(32025)),
            ('exit', ADDON.getLocalizedString(32026)),
        ]
        i = xbmcgui.Dialog().select(ADDON.getLocalizedString(32020), [label for _, label in items])
        choice = items[i][0] if i >= 0 else None
        self.last_input = time.time()
        if choice == 'list':
            return 'list'
        if choice == 'shuffle':
            movie = self.wall.at(*self.focus)
            if movie:
                self._finish_shuffle()
                if not self.panel_shown:
                    self._show_panel()
                self.shuffled_for = movie.movieid
                self._shuffle_related(movie)
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
            cache.discard()
            self._start_reload()
        elif choice == 'skin':
            skin = choose_skin()
            if skin:
                self.pending_skin = skin
                self._close()
        elif choice == 'exit':
            self._close()

    def _visible(self, movies):
        return merge_duplicates(movies) if self.merge else movies

    # Library data is fetched on background threads (a large library takes tens of seconds) and
    # applied under the lock, so the wall stays responsive while it loads.

    def _load_cast(self, total, gen):
        """Fill in cast for the shuffle ranking after the wall is already showing."""
        t0 = time.perf_counter()
        cast = fetch_cast()
        with self.lock:
            if self.closing or gen != self.library_gen:
                return
            self.all_movies = [replace(m, cast=cast.get(m.movieid, ())) for m in self.all_movies]
            self._patch({m.movieid: m for m in self.all_movies})
            self.cast_complete = True
            snapshot = list(self.all_movies)
        xbmc.log(f'kscape.wall: cast for {len(cast)} movies in {1000 * (time.perf_counter() - t0):.0f} ms',
                 xbmc.LOGINFO)
        cache.save(total, [m.to_cache() for m in snapshot], complete=True)

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
            total = library_total()
            movies = fetch_movies()
            cast = fetch_cast()
            if not self.reload_again:
                break
        movies = [replace(m, cast=cast.get(m.movieid, ())) for m in movies]
        with self.lock:
            self.loading = False
            if self.closing or gen != self.library_gen or not movies:
                return
            self.pending_library = movies
            self.cast_complete = True
        cache.save(total, [m.to_cache() for m in movies], complete=True)

    def _movie_changed(self, movieid):
        """One movie changed (e.g. watched): patch it in place without re-laying out the wall."""
        threading.Thread(target=self._refresh_movie, args=(movieid,), daemon=True).start()

    def _refresh_movie(self, movieid):
        movie = fetch_movie(movieid)
        with self.lock:
            if self.closing or not hasattr(self, 'all_movies'):
                return
            known = any(m.movieid == movieid for m in self.all_movies)
            if movie is None or not known:
                self._start_reload()              # added or vanished: needs a full re-read
                return
            if not self.cast_complete:
                current = next(m for m in self.all_movies if m.movieid == movieid)
                movie = replace(movie, cast=current.cast)
            self.all_movies = [movie if m.movieid == movieid else m for m in self.all_movies]
            self._patch({movieid: movie})
            snapshot, complete = list(self.all_movies), self.cast_complete
        cache.save(len(snapshot), [m.to_cache() for m in snapshot], complete=complete)

    def _patch(self, by_id):
        """Swap updated movies into the wall and Back history, keeping every cell in place."""
        def patched(wall):
            return Wall(wall.rows, wall.cols,
                        [by_id.get(m.movieid, m) if m is not None else None for m in wall.cells])
        old = {m.movieid: m for m in self.wall.movies()}
        self.wall = patched(self.wall)
        self.history = [(patched(w), f) for w, f in self.history]
        changed = {mid for mid, m in by_id.items() if mid in old and not old[mid].looks_same(m)}
        if changed:
            self.front.shown = [None if mid in changed else mid for mid in self.front.shown]
            self._rebind(self.front)

    def _apply_library(self, movies):
        """Rebuild the wall from `movies`, keeping the focused movie when it still exists."""
        self._finish_shuffle()
        current = self.wall.at(*self.focus)
        self.all_movies = movies
        visible = self._visible(movies)
        if not visible:
            return
        self.wall = Wall.column_major(visible)
        self.history = []
        self.front.shown = [None] * POOL       # posters/badges may have changed
        cell = self.wall.cell_of(current.movieid) if current else None
        if cell is None and current:
            # The focused copy was merged away: stay on the copy that represents that title.
            cell = next((self.wall.cell_of(m.movieid) for m in self.wall.movies()
                         if (m.title, m.year) == (current.title, current.year)), None)
        self.focus = cell or (0, 0)
        self.shuffled_for = None
        self._hide_panel()
        self._set_frame()
        self._pan(camera_target(self.wall, self.focus), animate=False)
        xbmc.log(f'kscape.wall: applied library of {len(visible)} covers', xbmc.LOGINFO)

    # ---- shuffle ---------------------------------------------------------------------------

    def _shuffle_related(self, anchor):
        t0 = time.perf_counter()
        ranked = rank_related(anchor, self.wall.movies())
        t1 = time.perf_counter()
        new = self.wall.arranged_around(self.focus, ranked, blocked=self.panel_cells)
        xbmc.log(f'kscape.wall: shuffle {len(ranked)} movies: rank {1000 * (t1 - t0):.1f} ms, '
                 f'place {1000 * (time.perf_counter() - t1):.1f} ms', xbmc.LOGINFO)
        self.history.append((self.wall, self.focus))
        self._transition(new, anchor_id=anchor.movieid)

    def _undo(self):
        self._finish_shuffle()
        wall, focus = self.history.pop()
        movie = self.wall.at(*self.focus)
        self._transition(wall, anchor_id=movie.movieid if wall.cell_of(movie.movieid) == self.focus
                         else None)
        self.focus = focus
        self.shuffled_for = wall.at(*focus).movieid if wall.at(*focus) else None
        self.last_input = time.time()
        self._hide_panel()
        self._set_frame()
        self._pan(camera_target(self.wall, self.focus))

    def _transition(self, new, anchor_id=None):
        """Fly every cover from where it is in the current wall to its cell in `new`."""
        old = self.wall
        self.front_token += 1
        tok = self.front_token
        on = _is(PROP_FRONT, tok)
        rng = random.Random(tok)
        cx, cy = self.cam
        view = (cx, cy, cx + G.SCREEN_W, cy + G.SCREEN_H)
        margin = G.PITCH_X
        longest = 0
        instant = self.reduced

        def flight(sx, sy, delay, dur):
            half = dur // 2
            grow = int(round(100 * 100.0 / G.FLIGHT_SHRINK))
            return [
                ('Conditional', f'effect=slide start={int(sx)},{int(sy)} end=0,0 delay={delay} '
                                f'time={dur} tween=cubic easing=inout reversible=false condition={on}'),
                ('Conditional', f'effect=zoom start=100 end={G.FLIGHT_SHRINK} center=auto delay={delay} '
                                f'time={half} tween=sine easing=out reversible=false condition={on}'),
                ('Conditional', f'effect=zoom start=100 end={grow} center=auto delay={delay + half} '
                                f'time={half} tween=sine easing=in reversible=false condition={on}'),
            ]

        # Back buffer: new arrangement, transparent until the trigger, then flying into place.
        hold = ('Conditional', f'effect=fade start=0 end=0 time=0 reversible=false condition=!{on}')
        for k, cell in self._slot_cells():
            movie = new.at(*cell)
            anims = [hold]
            if movie is not None and movie.movieid != anchor_id and not instant:
                px, py = cell_origin(*cell)
                prev = old.cell_of(movie.movieid)
                qx, qy = cell_origin(*prev) if prev else (px, py)
                sx, sy = clip_outside((px, py), (qx, qy), view, margin)
                if (sx, sy) != (px, py):
                    delay = int(rng.uniform(0, G.FLIGHT_DELAY_MAX_MS))
                    dur = G.FLIGHT_MS + int(rng.uniform(0, G.FLIGHT_JITTER_MS))
                    anims += flight(sx - px, sy - py, delay, dur)
                    longest = max(longest, delay + dur)
            self.back.slots[k].setAnimations(anims)
            self.back.bind(k, cell, movie)

        # Front buffer: covers that leave the screen fly out; everything else vanishes at the
        # trigger because the back buffer now shows it (in flight or in place).
        vanish = ('Conditional', f'effect=fade start=0 end=0 time=0 reversible=false condition={on}')
        pool_cells = {cell for _, cell in self._slot_cells()}
        for k in range(POOL):
            mid = self.front.shown[k]
            if mid is None or not self.front.visible[k]:
                continue
            ox, oy = cell_origin(*self.front.cell[k])
            on_screen = view[0] - G.COVER_W < ox < view[2] and view[1] - G.COVER_H < oy < view[3]
            dest = new.cell_of(mid)
            dx_, dy_ = cell_origin(*dest) if dest else (ox, oy)
            stays_in_pool = dest in pool_cells
            if instant or not on_screen or stays_in_pool:
                self.front.slots[k].setAnimations([vanish])
                continue
            ex, ey = clip_outside((ox, oy), (dx_, dy_), view, margin)
            delay = int(rng.uniform(0, G.FLIGHT_DELAY_MAX_MS * 0.5))
            dur = G.DEPART_MS + int(rng.uniform(0, G.FLIGHT_JITTER_MS))
            self.front.slots[k].setAnimations([
                ('Conditional', f'effect=slide start=0,0 end={int(ex - ox)},{int(ey - oy)} delay={delay} '
                                f'time={dur} tween=cubic easing=in reversible=false condition={on}'),
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
