"""Text for the movie info screen, built from VideoLibrary.GetMovieDetails (pure Python).

Only what Kodi has recorded is shown: a missing rating, stream or country is left out, never
guessed. `tr` maps a string id to its localized format string (ADDON.getLocalizedString).
"""

DETAILS_PROPERTIES = [
    'title', 'year', 'plot', 'tagline', 'runtime', 'mpaa', 'country', 'genre', 'director',
    'writer', 'studio', 'cast', 'set', 'art', 'streamdetails', 'resume', 'trailer', 'ratings',
    'uniqueid', 'originaltitle', 'premiered', 'tag', 'top250', 'userrating', 'lastplayed',
    'playcount', 'dateadded', 'file',
]

HDR_NAMES = {'dolbyvision': 'Dolby Vision', 'hdr10': 'HDR10', 'hdr10plus': 'HDR10+', 'hlg': 'HLG'}

# String ids in strings.po
S_HOUR, S_HOURS, S_MINUTE, S_MINUTES, S_ASPECT = 32040, 32041, 32042, 32043, 32044


def runtime_words(seconds, tr):
    """'2 hours 3 minutes'; '' when Kodi has no runtime."""
    minutes = int(round((seconds or 0) / 60.0))
    if minutes <= 0:
        return ''
    h, m = divmod(minutes, 60)
    parts = []
    if h:
        parts.append(tr(S_HOUR if h == 1 else S_HOURS).format(h))
    if m:
        parts.append(tr(S_MINUTE if m == 1 else S_MINUTES).format(m))
    return ' '.join(parts)


def _video(streamdetails):
    video = (streamdetails or {}).get('video') or []
    return video[0] if video else {}


def video_quality(streamdetails):
    """'4K HDR', '4K Dolby Vision', 'HD' or 'SD' from the first video stream; '' if unknown."""
    v = _video(streamdetails)
    w, h = v.get('width') or 0, v.get('height') or 0
    if not (w or h):
        return ''
    if w >= 3200 or h >= 1800:
        res = '4K'
    elif w >= 1200 or h >= 700:
        res = 'HD'
    else:
        res = 'SD'
    hdr = v.get('hdrtype') or ''
    return f'{res} {HDR_NAMES.get(hdr, "HDR")}' if hdr else res


def aspect_text(streamdetails, tr):
    """'1.78 aspect ratio' for the encoded video (letterboxing included, as Kodi reports it)."""
    aspect = _video(streamdetails).get('aspect') or 0
    return tr(S_ASPECT).format(f'{aspect:.2f}') if aspect > 0 else ''


def summary_line(d, tr):
    """'Rated PG; 2 hours 3 minutes, 4K HDR, 1.85 aspect ratio, USA, 2012'."""
    facts = [
        runtime_words(d.get('runtime'), tr),
        video_quality(d.get('streamdetails')),
        aspect_text(d.get('streamdetails'), tr),
        ', '.join(d.get('country') or ()),
        str(d['year']) if d.get('year') else '',
    ]
    rest = ', '.join(f for f in facts if f)
    mpaa = (d.get('mpaa') or '').strip()
    if mpaa and rest:
        return f'{mpaa}; {rest}'
    return mpaa or rest


def cast_names(d, limit=8):
    people = sorted(d.get('cast') or [], key=lambda c: c.get('order', 0))
    return [c['name'] for c in people[:limit] if c.get('name')]


def clock(seconds):
    """'1:02:15' or '42:07'."""
    seconds = int(seconds or 0)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'


def estimate_lines(text, width_px, font_px, char_em=0.49):
    """Lines Kodi will need to wrap `text` at `width_px`, estimated from an average glyph width.

    Kodi offers no text measurement to scripts, so the info screen lays itself out with this
    estimate. `char_em` is deliberately generous so text is clipped rather than overlapping.
    """
    per_line = max(1, int(width_px / (font_px * char_em)))
    lines = 0
    for para in (text or '').split('\n'):
        used = 0
        lines += 1
        for word in para.split():
            need = len(word) if used == 0 else used + 1 + len(word)
            if need > per_line and used:
                lines += 1
                used = len(word)
            else:
                used = need
            while used > per_line:                 # a word longer than a line
                lines += 1
                used -= per_line
    return lines
