"""Movie versions (pure Python): what each version of a movie is, which formats a movie is
available in, and which version Play starts.

Kodi 21 groups versions natively: one movie, several files, each with a version type ("Standard
Edition", "Director's Cut", "4K"...). JSON-RPC lists the movie once and has no version API, but
Kodi's own library paths do (library.fetch_versions):
    videodb://movies/videoversions/            the version types in use
    videodb://movies/videoversions/<type>/     every movie with that version: its file, stream
                                               details and resume point
Playing a version's file is recognised by Kodi as that movie and version; resume points are kept
per version (per file). Copies of a film that are separate library entries can also be shown as
one (model.merge_duplicates); their copies become versions here too.

Formats are worked out from the stream details Kodi measured; missing details give no format
rather than a guess.
"""
import re
from typing import NamedTuple, Tuple

from . import streaminfo as SI

FORMATS = ('4K', '1080p', '720p', '3D', 'SD', 'DVD')     # badge order
PREFERENCES = ('4K', '1080p', '720p', 'SD', 'default')     # "Preferred version" setting values
RES_RANK = {'4K': 0, '1080p': 1, '720p': 2, 'SD': 3, '': 4}
RES_LONG = {'4K': '4K Ultra HD · 2160p', '1080p': 'Full HD · 1080p', '720p': 'HD · 720p', 'SD': 'SD',
            'DVD': 'DVD'}


class Version(NamedTuple):
    movieid: int
    file: str
    name: str = ''                    # Kodi's version type, e.g. "Director's Cut"
    resolution: str = ''
    hdr: str = ''
    audio: Tuple[str, ...] = ()
    stereo: bool = False
    resume: float = 0.0
    default: bool = False             # Kodi's default version of the movie
    vtype: str = ''                   # its version type's library path (videodb://movies/videoversions/N/);
                                      # '' for a copy that is its own library entry

    @classmethod
    def from_item(cls, movieid, item, name, vtype='', default_file=''):
        sd = item.get('streamdetails')
        return cls(movieid=int(movieid), file=item.get('file') or '', name=name,
                   resolution=SI.resolution(sd), hdr=SI.hdr(sd), audio=SI.audio_formats(sd),
                   stereo=SI.stereo(sd), resume=float((item.get('resume') or {}).get('position') or 0),
                   default=bool(default_file) and item.get('file') == default_file, vtype=vtype)

    def to_cache(self):
        d = self._asdict()
        d['audio'] = list(d['audio'])
        return d

    @classmethod
    def from_cache(cls, d):
        return cls(**dict(d, audio=tuple(d.get('audio') or ())))


_NAME_3D = re.compile(r'(?<![a-z0-9])(3d|h-?sbs|half-?sbs|h-?tab|h-?ou|half-?ou)(?![a-z0-9])', re.I)
_NAME_IMAX = re.compile(r'(?<![a-z0-9])imax(?![a-z0-9])', re.I)
_NAME_RES = ((re.compile(r'(?<![a-z0-9])(2160p|4k|uhd)(?![a-z0-9])', re.I), '4K'),
             (re.compile(r'(?<![a-z0-9])1080[pi](?![a-z0-9])', re.I), '1080p'),
             (re.compile(r'(?<![a-z0-9])720p(?![a-z0-9])', re.I), '720p'))


def _base(path):
    return (path or '').replace('\\', '/').rstrip('/').rsplit('/', 1)[-1]


def name_3d(path):
    """A file named ...3D... (or Half-SBS, H-OU...) is a 3D movie, whatever Kodi measured."""
    return bool(_NAME_3D.search(_base(path)))


def name_resolution(path):
    """'4K' / '1080p' / '720p' if the file name says so, else ''."""
    base = _base(path)
    return next((r for rx, r in _NAME_RES if rx.search(base)), '')


def name_imax(path):
    return bool(_NAME_IMAX.search(_base(path)))


def is_3d(v):
    return v.stereo or name_3d(v.file)


def resolution_of(v):
    return v.resolution or name_resolution(v.file)


def is_dvd(path):
    """A DVD folder structure (an .iso could be DVD or Blu-ray, so it is not counted)."""
    p = (path or '').lower()
    return 'video_ts' in p or p.endswith(('.ifo', '.vob'))


def format_of(resolution, path=''):
    """'4K' / '1080p' / '720p' / 'SD' / 'DVD' (an SD DVD structure); '' if unknown."""
    if resolution == 'SD' and is_dvd(path):
        return 'DVD'
    return resolution


def formats(versions, resolution='', stereo=False, path=''):
    """The formats a movie is available in, in badge order: every version's resolution, and 3D
    when one is 3D. Without versions, the movie's own file."""
    found = set()
    if versions:
        for v in versions:
            f = format_of(resolution_of(v), v.file)
            if f:
                found.add(f)
            if is_3d(v):
                found.add('3D')
    else:
        f = format_of(resolution, path)
        if f:
            found.add(f)
        if stereo or name_3d(path):
            found.add('3D')
    return tuple(f for f in FORMATS if f in found)


def order(versions, preference='4K', prefer_3d=False):
    """Versions in the order Play considers them: the preferred resolution, then the others from
    the best down; 2D before 3D unless 3D is preferred; Kodi's default version first among
    equals. 'default' preference: Kodi's default version first."""
    if preference == 'default':
        return sorted(versions, key=lambda v: (not v.default, is_3d(v) != prefer_3d))
    pref = RES_RANK.get(preference, 0)

    def key(v):
        rank = RES_RANK.get(resolution_of(v), 4)
        return (is_3d(v) != prefer_3d, rank != pref, rank, not v.default)
    return sorted(versions, key=key)


def choose(versions, preference='4K', prefer_3d=False, resume=False):
    """The version Play (or Resume, with `resume`) starts; None without versions. Resume picks,
    among the versions with a resume point, the first in Play's order."""
    ranked = order(versions, preference, prefer_3d)
    if resume:
        paused = [v for v in ranked if v.resume > 0]
        if paused:
            return paused[0]
    return ranked[0] if ranked else None


def label(v, same_names=False, title=''):
    """'Sonic the Hedgehog 3 (Director's Cut) · 4K Ultra HD · 2160p · 3D · HDR10 · Dolby Atmos'.
    The movie's name leads, then the version's; 3D and the resolution count if the file name says
    so. Unknown parts are left out. The file name is only added (`same_names`) when nothing else
    tells two versions apart."""
    tech = [RES_LONG.get(format_of(resolution_of(v), v.file), '')]
    vname = v.name or ''
    if name_imax(v.file) and not _NAME_IMAX.search(f'{title} {vname}'):
        tech.append('IMAX')
    if is_3d(v):
        tech.append('3D')
    if v.hdr:
        tech.append(SI.HDR_LABELS.get(v.hdr, ''))
    if v.audio:
        tech.append(SI.AUDIO_LABELS.get(v.audio[0], ''))
    tech = ' · '.join(t for t in tech if t)
    name = f'{title} ({vname})' if title and vname else (title or vname)
    if same_names or not name:
        base = _base(v.file)
        name = f'{name} ({base})' if name else base
    return f'{name} · {tech}' if tech else name


def labels(versions, title=''):
    plain = [label(v, title=title) for v in versions]
    return [label(v, same_names=plain.count(p) > 1, title=title) for v, p in zip(versions, plain)]
