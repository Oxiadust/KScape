"""Wall geometry and motion timing, shared by the window and the XML generator.

Sizes are 1080p skin pixels. Values were measured from the reference video
(video/navigation.mp4): ~9 columns and ~3.6 rows visible, covers bleeding off every edge.
"""
import math
from collections import namedtuple

SCREEN_W = 1920
SCREEN_H = 1080

Layout = namedtuple('Layout', 'name cover_w cover_h pitch_x pitch_y frame pool_cols pool_rows '
                              'panel_cells min_rows frame_x view',
                    defaults=(None, (0, 0, SCREEN_W, SCREEN_H)))
# frame_x  thickness of the frame's left and right bars (frame on a 16:9 screen, see adapt())
# view     (x, y, w, h) the wall draws in: the whole screen, or a CinemaScope band (display.py)


def fx(layout):
    """Horizontal frame thickness."""
    return layout.frame if layout.frame_x is None else layout.frame_x


def panel_w(layout):
    """Info panel beside the focused cover, flush against the focus frame: as tall as the frame,
    reaching from the frame's edge to the far cell's edge."""
    return layout.panel_cells * layout.pitch_x - fx(layout)


def panel_h(layout):
    return layout.cover_h + 2 * layout.frame


# Movie and TV posters (2:3): ~9 x 3.6 visible, 24 px gutters (even all round, so the frame is
# too). The recycled pool covers the screen plus slack for a camera glide.
POSTER = Layout('poster', cover_w=186, cover_h=279, pitch_x=210, pitch_y=303, frame=22,
                pool_cols=13, pool_rows=6, panel_cells=3, min_rows=3)
# Album covers (1:1): ~7.6 x 4.3 visible, as in the music reference (prompts/assets).
SQUARE = Layout('square', cover_w=228, cover_h=228, pitch_x=254, pitch_y=254, frame=24,
                pool_cols=11, pool_rows=7, panel_cells=3, min_rows=4)

# The most cover slots the generated wall XML has per pool (tools/gen_wall_xml.py): enough for a
# 21:9 screen, or three rows in a CinemaScope band.
MAX_POOL = {'poster': (20, 7), 'square': (17, 8)}


def adapt(base, stage):
    """`base` (designed for a 16:9 screen) for the display stage (display.stage): covers scaled
    to the rows the view holds, every width divided by the screen's horizontal stretch so covers
    keep their shape (Kodi stretches coordinates but not text), and as many recycled slots as
    the view needs (within MAX_POOL)."""
    s, sx = stage.scale, stage.sx
    vx, vy, vw, vh = stage.view
    if abs(s - 1) < 1e-3 and abs(sx - 1) < 1e-3 and stage.view == (0, 0, SCREEN_W, SCREEN_H):
        return base
    w = lambda v: max(1, int(round(v * s / sx)))
    h = lambda v: max(1, int(round(v * s)))
    pitch_x, pitch_y = w(base.pitch_x), h(base.pitch_y)
    max_cols, max_rows = MAX_POOL[base.name]
    cols = min(max_cols, max(base.pool_cols, int(math.ceil(vw / pitch_x)) + 4))
    rows = min(max_rows, max(base.pool_rows, int(math.ceil(vh / pitch_y)) + 2))
    return base._replace(cover_w=w(base.cover_w), cover_h=h(base.cover_h), pitch_x=pitch_x, pitch_y=pitch_y,
                         frame=h(base.frame), frame_x=w(base.frame), pool_cols=cols, pool_rows=rows,
                         view=(vx, vy, vw, vh))


def view_size(layout):
    return layout.view[2], layout.view[3]


# The poster layout under its historical names.
COVER_W, COVER_H = POSTER.cover_w, POSTER.cover_h
PITCH_X, PITCH_Y = POSTER.pitch_x, POSTER.pitch_y
FRAME = POSTER.frame
POOL_COLS, POOL_ROWS = POSTER.pool_cols, POSTER.pool_rows
PANEL_CELLS = POSTER.panel_cells
PANEL_W = panel_w(POSTER)
PANEL_H = panel_h(POSTER)

# Motion (milliseconds unless noted). The focus frame glides to the next cover with a soft
# overshoot (Kodi tween "back"; "elastic" is available but wobbles several times), and the wall
# follows with a long ease-out so it settles gently instead of stopping short.
# Synopsis ~1.1 s after the last move; shuffle ~2 s later, lasting ~1.9 s (reference video).
FRAME_MS = 420
FRAME_TWEEN = 'back'
PAN_MS = 600
PANEL_DELAY_S = 1.1
SHUFFLE_DELAY_S = 3.2
FLIGHT_MS = 1150
FLIGHT_JITTER_MS = 350
FLIGHT_DELAY_MAX_MS = 300
FLIGHT_SHRINK = 72     # percent scale at mid-flight
DEPART_MS = 900

WALL_MIN_ROWS = POSTER.min_rows
WALL_MAX_ROWS = 10
