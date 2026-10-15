"""Wall layout: grid placement, related arrangement, camera and flight geometry (pure Python)."""
import math

from . import geometry as G


def grid_rows(count):
    """Rows for a library of `count` movies: a wall roughly three times wider than tall."""
    if count <= 0:
        return G.WALL_MIN_ROWS
    return max(G.WALL_MIN_ROWS, min(G.WALL_MAX_ROWS, int(round(math.sqrt(count / 3.0)))))


class Wall:
    """Movies placed on a rows x cols grid. Cells are addressed (col, row)."""

    def __init__(self, rows, cols, cells):
        self.rows = rows
        self.cols = cols
        self.cells = cells                       # list indexed by col * rows + row; Movie or None
        self.index = {m.movieid: i for i, m in enumerate(cells) if m is not None}

    @classmethod
    def column_major(cls, movies, rows=None):
        """Initial wall: movies in the given order, filling each column top to bottom."""
        rows = rows or grid_rows(len(movies))
        cols = max(1, math.ceil(len(movies) / rows))
        cells = list(movies) + [None] * (rows * cols - len(movies))
        return cls(rows, cols, cells)

    def at(self, col, row):
        if 0 <= col < self.cols and 0 <= row < self.rows:
            return self.cells[col * self.rows + row]
        return None

    def cell_of(self, movieid):
        i = self.index.get(movieid)
        return None if i is None else (i // self.rows, i % self.rows)

    def movies(self):
        return [m for m in self.cells if m is not None]

    def arranged_around(self, anchor_cell, ranked, blocked=(), blocked_penalty=2.5):
        """New wall with the anchor kept in place and `ranked` movies filling the nearest cells.

        Distance is measured in screen pixels so rows and columns weigh as they look. Cells in
        `blocked` (e.g. under the info panel) count as `blocked_penalty` cells farther away.
        """
        ac, ar = anchor_cell
        anchor = self.at(ac, ar)
        blocked = set(blocked)

        def dist(cell):
            c, r = cell
            d = math.hypot((c - ac) * G.PITCH_X, (r - ar) * G.PITCH_Y)
            if cell in blocked:
                d += blocked_penalty * G.PITCH_X
            # Angle as a deterministic tie-break, clockwise from straight up.
            ang = math.atan2(c - ac, -(r - ar)) % (2 * math.pi)
            return (round(d, 6), round(ang, 6), c, r)

        order = sorted(((c, r) for c in range(self.cols) for r in range(self.rows)
                        if (c, r) != anchor_cell), key=dist)
        cells = [None] * (self.rows * self.cols)
        cells[ac * self.rows + ar] = anchor
        for (c, r), m in zip(order, ranked):
            cells[c * self.rows + r] = m
        return Wall(self.rows, self.cols, cells)


def cell_origin(col, row):
    """Top-left of a cell in wall pixels."""
    return col * G.PITCH_X, row * G.PITCH_Y


def camera_target(wall, cell):
    """Camera (wall-pixel top-left of the screen) that centres `cell`, clamped to the wall."""
    x, y = cell_origin(*cell)
    cx = x + G.COVER_W / 2 - G.SCREEN_W / 2
    cy = y + G.COVER_H / 2 - G.SCREEN_H / 2
    wall_w = wall.cols * G.PITCH_X - (G.PITCH_X - G.COVER_W)
    wall_h = wall.rows * G.PITCH_Y - (G.PITCH_Y - G.COVER_H)
    margin_x, margin_y = G.PITCH_X * 0.5, G.PITCH_Y * 0.25

    def clamp(v, size, screen, margin):
        if size + 2 * margin <= screen:
            return (size - screen) / 2.0            # whole axis fits: centre it
        return max(-margin, min(size - screen + margin, v))

    return (round(clamp(cx, wall_w, G.SCREEN_W, margin_x)),
            round(clamp(cy, wall_h, G.SCREEN_H, margin_y)))


def ease_out_cubic(p):
    """Matches Kodi's tween="cubic" easing="out"."""
    p = max(0.0, min(1.0, p))
    return 1 - (1 - p) ** 3


BACK_OVERSHOOT = 1.70158


def ease_out_back(p, s=BACK_OVERSHOOT):
    """Matches Kodi's tween="back" easing="out": overshoots slightly, then settles."""
    p = max(0.0, min(1.0, p)) - 1
    return p * p * ((s + 1) * p + s) + 1


def clip_outside(origin, target, rect, margin):
    """Where a cover travelling origin -> target should start/end if target is off-screen.

    Returns target unchanged if it lies within `rect` grown by `margin`; otherwise the point on
    the segment just beyond that grown rect, so far-away covers enter or leave from the
    nearest edge instead of crossing the whole wall.
    """
    x0, y0, x1, y1 = rect[0] - margin, rect[1] - margin, rect[2] + margin, rect[3] + margin
    tx, ty = target
    if x0 <= tx <= x1 and y0 <= ty <= y1:
        return target
    ox, oy = origin
    dx, dy = tx - ox, ty - oy
    t_exit = 1.0
    for d, o, lo, hi in ((dx, ox, x0, x1), (dy, oy, y0, y1)):
        if d > 0:
            t_exit = min(t_exit, (hi - o) / d)
        elif d < 0:
            t_exit = min(t_exit, (lo - o) / d)
    t_exit = max(0.0, t_exit)
    return ox + dx * t_exit, oy + dy * t_exit
