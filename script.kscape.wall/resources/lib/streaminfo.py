"""Technical facts and ratings of a movie, read from what Kodi recorded (pure Python).

Everything comes from Kodi's library: the stream details its video player measured from the
file (resolution, dynamic range, audio codecs, aspect ratio) and the ratings its scraper or NFO
stored. Nothing is guessed from titles or file names, and anything missing is left out.

Kodi 21 records the audio codec as FFmpeg names it (truehd, dtshd_ma, eac3...): it does not tell
Dolby Atmos or DTS:X apart from the codec underneath. Those two show only when the stream details
carry them (later Kodi versions, NFO files from media managers: truehd_atmos, dtshd_ma_x...).
"""

RESOLUTIONS = ('4K', '1080p', '720p', 'SD')
HDR_TYPES = ('dolbyvision', 'hdr10plus', 'hdr10', 'hlg', 'sdr')
HDR_LABELS = {'sdr': 'SDR', 'hdr10': 'HDR10', 'hdr10plus': 'HDR10+', 'dolbyvision': 'Dolby Vision',
              'hlg': 'HLG'}
# Best first: a movie with several audio tracks shows its best one.
AUDIO_FORMATS = ('atmos', 'dtsx', 'truehd', 'dtshdma', 'dtshdhra', 'ddplus', 'dts', 'dd', 'pcm',
                 'flac', 'aac')
AUDIO_LABELS = {'atmos': 'Dolby Atmos', 'dtsx': 'DTS:X', 'truehd': 'Dolby TrueHD',
                'dtshdma': 'DTS-HD MA', 'dtshdhra': 'DTS-HD HRA', 'ddplus': 'Dolby Digital Plus',
                'dts': 'DTS', 'dd': 'Dolby Digital', 'pcm': 'PCM', 'flac': 'FLAC', 'aac': 'AAC'}

TMDB_KEYS = ('themoviedb', 'tmdb')
RT_KEYS = ('tomatometerallcritics', 'rottentomatoes', 'rotten_tomatoes', 'tomatometer',
           'rottentomatoescritics', 'rt')

COUNTRY_SHORT = {'United States of America': 'USA', 'United States': 'USA',
                 'United Kingdom': 'UK', 'United Arab Emirates': 'UAE',
                 'Soviet Union': 'USSR', 'Union of Soviet Socialist Republics': 'USSR'}


def first_video(streamdetails):
    video = (streamdetails or {}).get('video') or []
    return video[0] if video else {}


def resolution(streamdetails):
    """'4K', '1080p', '720p' or 'SD' from the first video stream; '' when Kodi has none.

    Width counts as much as height, so a 2.39:1 film cropped to 3840x1606 is still 4K and one
    cropped to 1920x800 still 1080p."""
    v = first_video(streamdetails)
    w, h = v.get('width') or 0, v.get('height') or 0
    if not (w or h):
        return ''
    if w >= 3200 or h >= 1800:
        return '4K'
    if w >= 1600 or h >= 1000:
        return '1080p'
    if w >= 1100 or h >= 650:
        return '720p'
    return 'SD'


def hdr(streamdetails):
    """Dynamic range of the first video stream: an HDR_TYPES key, 'sdr' for a known stream
    without HDR, '' when Kodi has no stream details."""
    v = first_video(streamdetails)
    if not v:
        return ''
    kind = (v.get('hdrtype') or '').lower().replace('-', '').replace(' ', '')
    if not kind:
        return 'sdr'
    return kind if kind in HDR_LABELS else ('dolbyvision' if 'dolby' in kind or kind == 'dv' else 'hdr10')


def audio_key(codec):
    """AUDIO_FORMATS key for one Kodi audio codec name, or None for formats not shown."""
    c = (codec or '').lower().replace('-', '_').replace(' ', '_')
    if not c:
        return None
    if 'atmos' in c:
        return 'atmos'
    if c.startswith(('dts', 'dca')) and (c.endswith('_x') or '_x_' in c or 'dtsx' in c or 'dts:x' in c):
        return 'dtsx'
    if 'truehd' in c or c == 'mlp':
        return 'truehd'
    if c.startswith(('dtshd_ma', 'dts_hd_ma', 'dtsma')):
        return 'dtshdma'
    if c.startswith(('dtshd_hra', 'dts_hd_hra', 'dtshd')):
        return 'dtshdhra'
    if c.startswith(('dts', 'dca')):
        return 'dts'
    if c in ('eac3', 'e_ac3', 'ec3', 'ddp', 'ddplus'):
        return 'ddplus'
    if c in ('ac3', 'dd', 'a_ac3'):
        return 'dd'
    if c.startswith(('pcm', 'lpcm')):
        return 'pcm'
    if c == 'flac':
        return 'flac'
    if c.startswith('aac'):
        return 'aac'
    return None


def audio_formats(streamdetails):
    """Every shown audio format of the file, best first (no repeats)."""
    keys = {audio_key(a.get('codec')) for a in (streamdetails or {}).get('audio') or []}
    return tuple(k for k in AUDIO_FORMATS if k in keys)


def aspect(streamdetails):
    """Aspect ratio of the encoded picture as Kodi measured it (0.0 if unknown)."""
    return round(float(first_video(streamdetails).get('aspect') or 0), 2)


def aspect_label(value):
    """'2.39:1'; '' for an unknown aspect."""
    return f'{value:.2f}:1' if value and value > 0 else ''


def _rating(ratings, keys):
    for k, v in (ratings or {}).items():
        if k.lower().replace(' ', '') in keys and isinstance(v, dict) and (v.get('rating') or 0) > 0:
            return float(v['rating'])
    return 0.0


def tmdb_rating(ratings):
    """TMDB score out of 10, one decimal; 0.0 when Kodi has none."""
    return round(_rating(ratings, TMDB_KEYS), 1)


def rt_percent(ratings):
    """Rotten Tomatoes Tomatometer (0-100) when the library has it, else 0.

    Kodi scales ratings it imports with a maximum (an NFO's max="100") to ten; a value above ten
    was stored without one and is a percentage already."""
    v = _rating(ratings, RT_KEYS)
    if not v:
        return 0
    return int(round(v if v > 10 else v * 10))


def runtime_short(seconds):
    """'2h 43m', '43m', '2h'; '' when unknown."""
    minutes = int(round((seconds or 0) / 60.0))
    if minutes <= 0:
        return ''
    h, m = divmod(minutes, 60)
    if h and m:
        return f'{h}h {m}m'
    return f'{h}h' if h else f'{m}m'


def country_short(name):
    return COUNTRY_SHORT.get(name, name)


def facts_line(runtime, aspect_value, countries, year, max_countries=2):
    """'2h 43m · 2.39:1 · USA · 2021' from what is known."""
    parts = [runtime_short(runtime), aspect_label(aspect_value),
             ', '.join(country_short(c) for c in list(countries)[:max_countries]),
             str(year) if year else '']
    return ' · '.join(p for p in parts if p)


def decade(year):
    return year // 10 * 10 if year else 0


DURATIONS = (('short', 0, 95 * 60), ('medium', 95 * 60, 135 * 60), ('long', 135 * 60, 10 ** 9))


def duration_class(seconds):
    """'short' (under 1h 35m), 'medium' (to 2h 15m) or 'long'; '' when unknown."""
    if not seconds:
        return ''
    return next(name for name, lo, hi in DURATIONS if lo <= seconds < hi)
