"""Cover wall window: camera-follow navigation and the animated related-cover shuffle.

Kodi cannot move items inside its list containers, so the wall is a pool of image slots that
the window positions itself. Motion is expressed as runtime animations (Control.setAnimations)
whose conditions reference a Home window property; flipping that property starts every
prepared animation in the same frame.

Two slot pools (A, B) double-buffer the shuffle: the new arrangement is bound into the back
pool while it is held transparent, then one property change hides the old covers that
re-appear elsewhere, flies the departing ones off-screen and flies the new ones into place.
"""
import random
import threading
import time

import xbmc
import xbmcaddon
import xbmcgui

from . import geometry as G
from .library import fetch_movies, play
from .ranking import rank_related
from .wallmodel import Wall, camera_target, cell_origin, clip_outside, ease_out_cubic

POOL = G.POOL_COLS * G.POOL_ROWS
MOVES = {
    xbmcgui.ACTION_MOVE_LEFT: (-1, 0),
    xbmcgui.ACTION_MOVE_RIGHT: (1, 0),
    xbmcgui.ACTION_MOVE_UP: (0, -1),
    xbmcgui.ACTION_MOVE_DOWN: (0, 1),
}
SELECT = (xbmcgui.ACTION_SELECT_ITEM, xbmcgui.ACTION_PLAYER_PLAY)
BACK = (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU)

HOME = xbmcgui.Window(10000)
ADDON = xbmcaddon.Addon('script.kscape.wall')
PROP_CAM = 'kscape.cam'
PROP_FRONT = 'kscape.front'
PROP_LAST = 'kscape.lastmovie'


def _is(prop, value):
    return f'String.IsEqual(Window(Home).Property({prop}),{value})'


class Pool:
    """One set of recycled cover slots. Slot k always serves grid cells congruent to it."""

    def __init__(self, win, base):
        self.slots = [win.getControl(base + k) for k in range(POOL)]
        self.texts = [win.getControl(base + 200 + k) for k in range(POOL)]
        self.posters = [win.getControl(base + 400 + k) for k in range(POOL)]
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


class WallWindow(xbmcgui.WindowXML):
    ready = False

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
        self.front, self.back = Pool(self, 1100), Pool(self, 2100)
        for k in range(POOL):
            self.front.set_visible(k, False)
            self.back.set_visible(k, False)
        self.frame.setVisible(False)
        self.panel.setVisible(False)
        self.reduced = xbmc.getCondVisibility('Skin.HasSetting(ReducedMotion)')

        self.status.setLabel(ADDON.getLocalizedString(32001))
        movies = fetch_movies()
        if not movies:
            self.status.setLabel(ADDON.getLocalizedString(32002))
            self.ready = True
            return
        self.status.setLabel('')

        self.wall = Wall.column_major(movies)
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

        last = HOME.getProperty(PROP_LAST)
        start = self.wall.cell_of(int(last)) if last.isdigit() else None
        self.focus = start or (0, 0)
        self._set_frame()
        self._pan(camera_target(self.wall, self.focus), animate=False)
        self.ready = True
        threading.Thread(target=self._dwell_loop, daemon=True).start()

    def _close(self):
        self.closing = True
        movie = self.wall.at(*self.focus) if getattr(self, 'wall', None) else None
        if movie:
            HOME.setProperty(PROP_LAST, str(movie.movieid))
        self.close()

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
        with self.lock:
            if aid in MOVES:
                self._move(*MOVES[aid])
            elif aid in SELECT:
                movie = self.wall.at(*self.focus)
                if movie:
                    HOME.setProperty(PROP_LAST, str(movie.movieid))
                    play(movie)
            elif aid in BACK:
                if self.history:
                    self._undo()
                else:
                    self._close()

    def _move(self, dx, dy):
        c, r = self.focus[0] + dx, self.focus[1] + dy
        if self.wall.at(c, r) is None:
            return                        # wall edge or padding cell: stay put
        self._finish_shuffle()
        self.focus = (c, r)
        self.last_input = time.time()
        self._hide_panel()
        self._set_frame()
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

    def _set_frame(self):
        x, y = cell_origin(*self.focus)
        self.frame.setPosition(x - G.FRAME, y - G.FRAME)
        self.frame.setVisible(True)

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
        self.panel.setPosition(*cell_origin(*min(cells)))
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
                if xbmc.getCondVisibility('Player.HasVideo'):
                    self.last_input = now     # wall is behind the video: stay idle
                    continue
                if self.shuffle_until and now >= self.shuffle_until:
                    self._finish_shuffle()
                idle = now - self.last_input
                if not self.panel_shown and idle >= G.PANEL_DELAY_S:
                    self._show_panel()
                movie = self.wall.at(*self.focus)
                if (movie and idle >= G.SHUFFLE_DELAY_S and not self.shuffle_until
                        and self.shuffled_for != movie.movieid):
                    self.shuffled_for = movie.movieid
                    self._shuffle_related(movie)

    # ---- shuffle ---------------------------------------------------------------------------

    def _shuffle_related(self, anchor):
        ranked = rank_related(anchor, self.wall.movies())
        new = self.wall.arranged_around(self.focus, ranked, blocked=self.panel_cells)
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
