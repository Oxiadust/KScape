"""Wall geometry and motion timing, shared by the window and the XML generator.

Sizes are 1080p skin pixels. Values were measured from the reference video
(video/navigation.mp4): ~9 columns and ~3.6 rows visible, covers bleeding off every edge.
"""
from collections import namedtuple

SCREEN_W = 1920
SCREEN_H = 1080

Layout = namedtuple('Layout', 'name cover_w cover_h pitch_x pitch_y frame pool_cols pool_rows '
                              'panel_cells min_rows')


def panel_w(layout):
    """Info panel beside the focused cover, flush against the focus frame: as tall as the frame,
    reaching from the frame's edge to the far cell's edge."""
    return layout.panel_cells * layout.pitch_x - layout.frame


def panel_h(layout):
    return layout.cover_h + 2 * layout.frame


# Movie and TV posters (2:3): ~9 x 3.6 visible, 24 px gutters (even all round, so the frame is
# too). The recycled pool covers the screen plus slack for a camera glide.
POSTER = Layout('poster', cover_w=186, cover_h=279, pitch_x=210, pitch_y=303, frame=22,
                pool_cols=13, pool_rows=6, panel_cells=3, min_rows=3)
# Album covers (1:1): ~7.6 x 4.3 visible, as in the music reference (prompts/assets).
SQUARE = Layout('square', cover_w=228, cover_h=228, pitch_x=254, pitch_y=254, frame=24,
                pool_cols=11, pool_rows=7, panel_cells=3, min_rows=4)

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
