"""Wall geometry and motion timing, shared by the window and the XML generator.

Sizes are 1080p skin pixels. Values were measured from the reference video
(video/navigation.mp4): ~9 columns and ~3.6 rows visible, covers bleeding off every edge.
"""

SCREEN_W = 1920
SCREEN_H = 1080

COVER_W = 186
COVER_H = 279          # 2:3
PITCH_X = 210          # 24 px horizontal gutter
PITCH_Y = 303          # 24 px vertical gutter (even gutters, so the frame is even all round)
FRAME = 22             # amber focus frame: fills the gutter, drawn in front of the covers

# Recycled cover pool: enough cells to cover the screen plus slack for a camera glide.
POOL_COLS = 13
POOL_ROWS = 6

# Info panel occupies this many cells beside the focused cover, and sits flush against the
# focus frame: as tall as the frame, reaching from the frame's edge to the far cell's edge.
PANEL_CELLS = 3
PANEL_W = PANEL_CELLS * PITCH_X - FRAME
PANEL_H = COVER_H + 2 * FRAME

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

WALL_MIN_ROWS = 3
WALL_MAX_ROWS = 10
