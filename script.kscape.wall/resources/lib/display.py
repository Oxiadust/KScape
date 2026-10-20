"""Display & aspect ratio (pure Python): where KScape draws on screens that are not 16:9, and
on CinemaScope projector screens fed a 16:9 signal.

How Kodi 21 behaves (verified in the test Kodi, see README "Ultrawide and CinemaScope"):
- KScape's windows - the skin's and the add-on's - all use 1920 x 1080 coordinates. Add-on
  windows cannot use a skin's other coordinate spaces (Kodi only looks for their XML in the
  add-on, with a fixed resolution), so the skin keeps one coordinate space too.
- On a screen of another shape Kodi stretches those coordinates to fill it, but keeps text and
  images drawn with an aspect ratio in their true proportions. So a 21:9 screen simply gets a
  wider layout; only boxes that must keep a shape (cover cells, posters) need their width
  corrected by `sx`, the horizontal stretch.
- Nothing tells Kodi that a 16:9 signal lands on a 2.35:1 screen (a zoomed projector shows the
  middle band of the picture). That is a manual setting: KScape then draws inside that band
  (Stage.view), the cover wall natively, every other window scaled into it (Stage.zoom).

Offsets move the interface for projector alignment; the safe area shrinks it so nothing is cut
by overscan. Zoom and offsets are applied by skin animations that cannot take values from
settings, so they are rounded to steps the XML lists (ZOOMS, OFFSETS).
"""
from collections import namedtuple

W, H = 1920, 1080
BASE = 16 / 9.0
ASPECTS = (('auto', 0.0), ('16:9', 16 / 9.0), ('21:9', 64 / 27.0), ('2.35', 2.35), ('2.39', 2.39),
           ('2.40', 2.40))
ROWS = ('auto', '2', '3')
OFFSET_STEP, OFFSET_MAX = 10, 300          # px, either way
SAFE_MAX = 10                              # % on every side
ZOOM_MIN = 50                              # % (the narrowest band with the widest safe area)
OFFSETS = tuple(range(-OFFSET_MAX, OFFSET_MAX + 1, OFFSET_STEP))
ZOOMS = tuple(range(ZOOM_MIN, 101))
WIDE_FROM = 2.0                            # Auto: a screen this wide uses the ultrawide layout

Stage = namedtuple('Stage', 'sx banded aspect zoom dx dy view scale')
# sx      horizontal stretch Kodi applies to 1920 x 1080 coordinates on this screen (1 on 16:9)
# banded  KScape draws inside a CinemaScope band of a wider-looking 16:9 picture
# aspect  the interface aspect ratio in use
# zoom    % every window but the cover wall is scaled by (the band and safe area), int
# dx, dy  px those windows are moved by (offsets), multiples of OFFSET_STEP
# view    (x, y, w, h): where the cover wall draws, in coordinates
# scale   size of the wall's covers against the 16:9 layout (two or three rows in a band)


def aspect_value(name):
    return dict(ASPECTS).get(name, 0.0)


def _step(v, step=OFFSET_STEP, limit=OFFSET_MAX):
    v = max(-limit, min(limit, int(v)))
    return int(round(v / float(step))) * step


def stage(screen_w, screen_h, aspect='auto', rows='auto', voffset=0, hoffset=0, safe=0, cover_pitch=303):
    """Where KScape draws, for a screen (Kodi's GUI resolution) and the display settings."""
    canvas = (screen_w / float(screen_h)) if screen_w and screen_h else BASE
    sx = canvas / BASE
    target = aspect_value(aspect) or canvas
    banded = target > canvas * 1.01
    band = canvas / target if banded else 1.0          # band height, fraction of the screen
    safe = max(0, min(SAFE_MAX, int(safe)))
    f = 1.0 - 2 * safe / 100.0
    zoom = max(ZOOM_MIN, min(100, int(round(band * f * 100))))
    dx, dy = _step(hoffset), _step(voffset)
    vw, vh = W * f, H * band * f
    view = (int(round((W - vw) / 2 + dx)), int(round((H - vh) / 2 + dy)), int(round(vw)), int(round(vh)))
    return Stage(sx=sx, banded=banded, aspect=target, zoom=zoom, dx=dx, dy=dy, view=view,
                 scale=wall_scale(vh, rows if banded else 'auto', cover_pitch))


def wall_scale(view_h, rows='auto', pitch=303):
    """Cover size for the wall's height: as designed when about 3.6 rows fit; in a CinemaScope
    band, two or three rows (with part of the next ones showing) as asked, or as many as fit
    while keeping at least two and a third."""
    if rows == '2':
        return round(view_h / (2.35 * pitch), 3)
    if rows == '3':
        return round(view_h / (3.35 * pitch), 3)
    fits = view_h / float(pitch)
    return 1.0 if fits >= 2.35 else round(view_h / (2.35 * pitch), 3)


def detected(screen_w, screen_h):
    """What Auto picks for this screen: 'ultrawide' for a screen 2:1 or wider, else '16:9'.
    (A CinemaScope projector fed a 16:9 signal cannot be told from a TV: choose it by hand.)"""
    canvas = screen_w / float(screen_h) if screen_w and screen_h else BASE
    return 'ultrawide' if canvas >= WIDE_FROM else '16:9'


def properties(st):
    """Home window properties the skin's display transform reads (Includes_Display.xml): empty
    when there is nothing to change, so 16:9 screens run exactly the original layout."""
    return {
        'kscape.display.zoom': str(st.zoom) if st.zoom != 100 else '',
        'kscape.display.dx': str(st.dx) if st.dx else '',
        'kscape.display.dy': str(st.dy) if st.dy else '',
        'kscape.display.banded': '1' if st.banded else '',
        'kscape.display.sx': f'{st.sx:.4f}',
    }
