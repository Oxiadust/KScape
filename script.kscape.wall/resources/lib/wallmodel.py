"""Wall layout: grid placement, related arrangement, camera and flight geometry (pure Python)."""
import math

from . import geometry as G


def grid_rows(count, layout=G.POSTER):
    """Rows for a library of `count` items: a wall roughly three times wider than tall.

    At least the layout's min_rows, so the wall fills the screen top to bottom - except for a
    handful of items (e.g. a few favourites), which sit in a short centred block instead of a
    single column."""
    if count <= 0:
        return layout.min_rows
    rows = int(round(math.sqrt(count / 3.0)))
    if count < layout.min_rows * 3:
        return max(1, rows)
    return max(layout.min_rows, min(G.WALL_MAX_ROWS, rows))


class Wall:
    """Items (movies, albums, shows) placed on a rows x cols grid, addressed (col, row). Items are
    told apart by their `key`."""

    def __init__(self, rows, cols, cells, layout=G.POSTER):
        self.rows = rows
        self.cols = cols
        self.cells = cells                       # list indexed by col * rows + row; item or None
        self.layout = layout
        self.index = {m.key: i for i, m in enumerate(cells) if m is not None}

    @classmethod
    def column_major(cls, movies, rows=None, layout=G.POSTER):
        """Initial wall: items in the given order, filling each column top to bottom."""
        rows = rows or grid_rows(len(movies), layout)
        cols = max(1, math.ceil(len(movies) / rows))
        cells = list(movies) + [None] * (rows * cols - len(movies))
        return cls(rows, cols, cells, layout)

    def at(self, col, row):
        if 0 <= col < self.cols and 0 <= row < self.rows:
            return self.cells[col * self.rows + row]
        return None

    def cell_of(self, key):
        i = self.index.get(key)
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
        px, py = self.layout.pitch_x, self.layout.pitch_y

        def dist(cell):
            c, r = cell
            d = math.hypot((c - ac) * px, (r - ar) * py)
            if cell in blocked:
                d += blocked_penalty * px
            # Angle as a deterministic tie-break, clockwise from straight up.
            ang = math.atan2(c - ac, -(r - ar)) % (2 * math.pi)
            return (round(d, 6), round(ang, 6), c, r)

        order = sorted(((c, r) for c in range(self.cols) for r in range(self.rows)
                        if (c, r) != anchor_cell), key=dist)
        cells = [None] * (self.rows * self.cols)
        cells[ac * self.rows + ar] = anchor
        for (c, r), m in zip(order, ranked):
            cells[c * self.rows + r] = m
        return Wall(self.rows, self.cols, cells, self.layout)


def cell_origin(col, row, layout=G.POSTER):
    """Top-left of a cell in wall pixels."""
    return col * layout.pitch_x, row * layout.pitch_y


def camera_target(wall, cell):
    """Camera (wall-pixel top-left of the screen) that centres `cell`, clamped to the wall."""
    lay = wall.layout
    x, y = cell_origin(*cell, layout=lay)
    cx = x + lay.cover_w / 2 - G.SCREEN_W / 2
    cy = y + lay.cover_h / 2 - G.SCREEN_H / 2
    wall_w = wall.cols * lay.pitch_x - (lay.pitch_x - lay.cover_w)
    wall_h = wall.rows * lay.pitch_y - (lay.pitch_y - lay.cover_h)
    margin_x, margin_y = lay.pitch_x * 0.5, lay.pitch_y * 0.25

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


def _segment_hits_rect(p0, p1, rect):
    """True if the segment p0 -> p1 passes through the open rectangle (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = rect
    t0, t1 = 0.0, 1.0
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    for d, o, lo, hi in ((dx, p0[0], x0, x1), (dy, p0[1], y0, y1)):
        if abs(d) < 1e-9:
            if not lo < o < hi:
                return False
            continue
        a, b = (lo - o) / d, (hi - o) / d
        if a > b:
            a, b = b, a
        t0, t1 = max(t0, a), min(t1, b)
        if t0 >= t1:
            return False
    return True


def detour(start, end, keep_out, size, margin):
    """Waypoints that steer a flying cover around `keep_out`; [] if the straight path is clear.

    `start` and `end` are the cover's top-left corners, `size` its (w, h), and `keep_out` the
    rectangle (x0, y0, x1, y1) it must not cross - the selected cover and its frame. The cover
    is swept as a point against the rectangle grown by its size. The route goes round one
    corner of that grown rectangle (plus `margin`), or along a whole side via two corners when
    the cover has to cross from one side to the other; the shortest clear route wins.
    """
    w, h = size
    grown = (keep_out[0] - w, keep_out[1] - h, keep_out[2], keep_out[3])
    if not _segment_hits_rect(start, end, grown):
        return []
    x0, y0, x1, y1 = grown[0] - margin, grown[1] - margin, grown[2] + margin, grown[3] + margin
    tl, tr, bl, br = (x0, y0), (x1, y0), (x0, y1), (x1, y1)
    routes = [[tl], [tr], [bl], [br], [tl, tr], [tr, tl], [bl, br], [br, bl],
              [tl, bl], [bl, tl], [tr, br], [br, tr]]
    best = None
    for route in routes:
        points = [start] + route + [end]
        legs = list(zip(points, points[1:]))
        clear = not any(_segment_hits_rect(a, b, grown) for a, b in legs)
        length = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in legs)
        key = (not clear, length)
        if best is None or key < best[0]:
            best = (key, route)
    return best[1]
