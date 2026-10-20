"""Chapters embedded in a video file, read without playing it (pure Python).

Matroska (.mkv, .mka, .webm): the Chapters element (EBML), found through the SeekHead or by
walking the Segment; the default (else first) edition, hidden and disabled chapters skipped.
MP4 / MOV (.mp4, .m4v, .mov): Nero chapters (moov/udta/chpl) or a QuickTime chapter track (a
text track the video track points at with tref/chap).

Only the file's own headers are read - a few kilobytes, wherever they are - through a
read_at(offset, size) function, so Kodi's virtual file system (network shares) works too. The
file is never written. A file with no chapters, or one this can't read, gives [].
"""
import re
import struct

MAX_CHAPTERS = 500
MAX_ELEMENT = 16 * 1024 * 1024        # never read a header element bigger than this

# ---- Matroska ----------------------------------------------------------------------------------

EBML, SEGMENT, SEEKHEAD, SEEK, SEEKID, SEEKPOS = 0x1A45DFA3, 0x18538067, 0x114D9B74, 0x4DBB, 0x53AB, 0x53AC
CHAPTERS, EDITION, EDITION_DEFAULT, ATOM = 0x1043A770, 0x45B9, 0x45DB, 0xB6
T_START, T_END, HIDDEN, ENABLED, DISPLAY, STRING = 0x91, 0x92, 0x98, 0x4598, 0x80, 0x85
CLUSTER = 0x1F43B675
UNKNOWN = -1


def _vint(buf, pos, keep_marker):
    """(value, length) of the EBML variable-length integer at buf[pos]."""
    first = buf[pos]
    length = 1
    mask = 0x80
    while length <= 8 and not first & mask:
        mask >>= 1
        length += 1
    if length > 8 or pos + length > len(buf):
        raise ValueError('bad vint')
    value = first if keep_marker else first & (mask - 1)
    for b in buf[pos + 1:pos + length]:
        value = (value << 8) | b
    if not keep_marker and value == (1 << (7 * length)) - 1:
        value = UNKNOWN
    return value, length


def _children(buf, start=0, end=None):
    """(id, data start, data end) of each element in buf[start:end]."""
    pos, end = start, len(buf) if end is None else end
    while pos < end:
        eid, n = _vint(buf, pos, True)
        size, m = _vint(buf, pos + n, False)
        data = pos + n + m
        stop = end if size == UNKNOWN else min(end, data + size)
        yield eid, data, stop
        pos = stop


def _uint(buf, a, b):
    return int.from_bytes(buf[a:b], 'big') if b > a else 0


def _header(read_at, offset):
    """(id, data offset, size) of the element at `offset` in the file."""
    head = read_at(offset, 16)
    eid, n = _vint(head, 0, True)
    size, m = _vint(head, n, False)
    return eid, offset + n + m, size


def _mkv_atoms(buf, a, b):
    out = []
    for eid, s, e in _children(buf, a, b):
        if eid != ATOM:
            continue
        start, end, name, hidden, enabled = None, None, '', False, True
        for cid, cs, ce in _children(buf, s, e):
            if cid == T_START:
                start = _uint(buf, cs, ce) / 1e9
            elif cid == T_END:
                end = _uint(buf, cs, ce) / 1e9
            elif cid == HIDDEN:
                hidden = bool(_uint(buf, cs, ce))
            elif cid == ENABLED:
                enabled = bool(_uint(buf, cs, ce))
            elif cid == DISPLAY and not name:
                for did, ds, de in _children(buf, cs, ce):
                    if did == STRING:
                        name = buf[ds:de].decode('utf-8', 'replace').strip('\x00').strip()
        if start is not None and not hidden and enabled:
            out.append((start, end, name))
    return out


def _mkv_chapters(buf):
    editions = [(s, e) for eid, s, e in _children(buf) if eid == EDITION]
    chosen = None
    for s, e in editions:
        if any(cid == EDITION_DEFAULT and _uint(buf, cs, ce) for cid, cs, ce in _children(buf, s, e)):
            chosen = (s, e)
            break
    chosen = chosen or (editions[0] if editions else None)
    return _mkv_atoms(buf, *chosen) if chosen else []


def matroska(read_at, file_size):
    eid, data, size = _header(read_at, 0)
    if eid != EBML:
        return []
    pos = data + size
    eid, seg, seg_size = _header(read_at, pos)
    if eid != SEGMENT:
        return []
    seg_end = file_size if seg_size == UNKNOWN else min(file_size, seg + seg_size)
    pos = seg
    target = None
    while pos < seg_end:
        eid, data, size = _header(read_at, pos)
        if eid == CHAPTERS:
            target = (data, size)
            break
        if eid == SEEKHEAD and 0 < size <= MAX_ELEMENT:
            buf = read_at(data, size)
            for sid, s, e in _children(buf):
                if sid != SEEK:
                    continue
                what, where = None, None
                for cid, cs, ce in _children(buf, s, e):
                    if cid == SEEKID:
                        what = _uint(buf, cs, ce)
                    elif cid == SEEKPOS:
                        where = _uint(buf, cs, ce)
                if what == CHAPTERS and where is not None:
                    cid, cdata, csize = _header(read_at, seg + where)
                    if cid == CHAPTERS:
                        target = (cdata, csize)
            if target:
                break
        if eid == CLUSTER or size == UNKNOWN:
            break                               # the media data: chapters come before it
        pos = data + size
    if not target or not 0 < target[1] <= MAX_ELEMENT:
        return []
    return _mkv_chapters(read_at(*target))


# ---- MP4 / QuickTime ----------------------------------------------------------------------------

def _atoms(read_at, start, end):
    """(type, data offset, data end) of the boxes in [start, end) of the file."""
    pos = start
    while pos + 8 <= end:
        head = read_at(pos, 16)
        if len(head) < 8:
            return
        size, kind = struct.unpack('>I4s', head[:8])
        hdr = 8
        if size == 1:
            size = struct.unpack('>Q', head[8:16])[0]
            hdr = 16
        elif size == 0:
            size = end - pos
        if size < hdr:
            return
        yield kind.decode('latin-1'), pos + hdr, min(end, pos + size)
        pos += size


def _boxes(buf, start=0, end=None):
    pos, end = start, len(buf) if end is None else end
    while pos + 8 <= end:
        size, kind = struct.unpack('>I4s', buf[pos:pos + 8])
        hdr = 8
        if size == 1:
            size = struct.unpack('>Q', buf[pos + 8:pos + 16])[0]
            hdr = 16
        elif size == 0:
            size = end - pos
        if size < hdr:
            return
        yield kind.decode('latin-1'), pos + hdr, min(end, pos + size)
        pos += size


def _find(buf, path, start=0, end=None):
    """Data range of the first box along `path` (e.g. ['mdia', 'minf', 'stbl'])."""
    for kind, s, e in _boxes(buf, start, end):
        if kind == path[0]:
            return (s, e) if len(path) == 1 else _find(buf, path[1:], s, e)
    return None


def _chpl(buf, s, e):
    version = buf[s]
    p = s + 4 + (4 if version else 0)
    count = buf[p]
    p += 1
    out = []
    for _ in range(min(count, MAX_CHAPTERS)):
        if p + 9 > e:
            break
        start = struct.unpack('>Q', buf[p:p + 8])[0] / 1e7
        n = buf[p + 8]
        name = buf[p + 9:p + 9 + n].decode('utf-8', 'replace').strip()
        out.append((start, None, name))
        p += 9 + n
    return out


def _track_id(buf, s, e):
    r = _find(buf, ['tkhd'], s, e)
    if not r:
        return None
    version = buf[r[0]]
    off = r[0] + (20 if version == 1 else 12)
    return struct.unpack('>I', buf[off:off + 4])[0]


def _text_samples(buf, s, e, read_at):
    """(start seconds, text) of each sample of a QuickTime text track."""
    mdhd = _find(buf, ['mdia', 'mdhd'], s, e)
    stbl = _find(buf, ['mdia', 'minf', 'stbl'], s, e)
    if not mdhd or not stbl:
        return []
    v = buf[mdhd[0]]
    scale = struct.unpack('>I', buf[mdhd[0] + (20 if v == 1 else 12):][:4])[0] or 1

    def table(kind):
        r = _find(buf, [kind], *stbl)
        if not r:
            return None
        n = struct.unpack('>I', buf[r[0] + 4:r[0] + 8])[0]
        return r[0] + 8, n

    stts, stsz, stsc = table('stts'), table('stsz'), table('stsc')
    stco, co64 = table('stco'), table('co64')
    if not (stts and stsz and stsc and (stco or co64)):
        return []
    times, t = [], 0
    p, n = stts
    for i in range(n):
        count, delta = struct.unpack('>II', buf[p + 8 * i:p + 8 * i + 8])
        for _ in range(count):
            times.append(t)
            t += delta
            if len(times) > MAX_CHAPTERS:
                break
    p = stsz[0] - 8                       # stsz: version/flags, sample_size, count, sizes
    fixed, count = struct.unpack('>II', buf[p + 4:p + 12])
    sizes = [fixed] * count if fixed else [struct.unpack('>I', buf[p + 12 + 4 * i:p + 16 + 4 * i])[0]
                                           for i in range(min(count, MAX_CHAPTERS))]
    if co64:
        p, n = co64
        chunks = [struct.unpack('>Q', buf[p + 8 * i:p + 8 * i + 8])[0] for i in range(n)]
    else:
        p, n = stco
        chunks = [struct.unpack('>I', buf[p + 4 * i:p + 4 * i + 4])[0] for i in range(n)]
    p, n = stsc
    runs = [struct.unpack('>III', buf[p + 12 * i:p + 12 * i + 12]) for i in range(n)]
    offsets = []
    for r, (first, per_chunk, _) in enumerate(runs):
        last = runs[r + 1][0] - 1 if r + 1 < len(runs) else len(chunks)
        for c in range(first, last + 1):
            if c - 1 >= len(chunks):
                break
            off = chunks[c - 1]
            for _ in range(per_chunk):
                k = len(offsets)
                if k >= len(sizes):
                    break
                offsets.append(off)
                off += sizes[k]
    out = []
    for k, off in enumerate(offsets[:min(len(times), MAX_CHAPTERS)]):
        data = read_at(off, min(sizes[k], 1024))
        if len(data) < 2:
            continue
        n = struct.unpack('>H', data[:2])[0]
        raw = data[2:2 + n]
        if raw[:2] in (b'\xfe\xff', b'\xff\xfe'):
            text = raw.decode('utf-16', 'replace')
        else:
            text = raw.decode('utf-8', 'replace')
        out.append((times[k] / float(scale), None, text.strip()))
    return out


def mp4(read_at, file_size):
    moov = next(((s, e) for kind, s, e in _atoms(read_at, 0, file_size) if kind == 'moov'), None)
    if not moov or moov[1] - moov[0] > MAX_ELEMENT:
        return []
    buf = read_at(moov[0], moov[1] - moov[0])
    chpl = _find(buf, ['udta', 'chpl'])
    if chpl:
        found = _chpl(buf, *chpl)
        if found:
            return found
    tracks = [(s, e) for kind, s, e in _boxes(buf) if kind == 'trak']
    wanted = set()
    for s, e in tracks:
        chap = _find(buf, ['tref', 'chap'], s, e)
        if chap:
            wanted.update(struct.unpack('>I', buf[p:p + 4])[0] for p in range(chap[0], chap[1] - 3, 4))
    for s, e in tracks:
        if _track_id(buf, s, e) in wanted:
            return _text_samples(buf, s, e, read_at)
    return []


def read(read_at, file_size):
    """[(start s, end s or None, name)] of the file's chapters, in order; [] if none or unreadable."""
    try:
        head = read_at(0, 12)
        if head[:4] == b'\x1a\x45\xdf\xa3':
            found = matroska(read_at, file_size)
        elif head[4:8] in (b'ftyp', b'moov', b'mdat', b'free', b'wide', b'skip'):
            found = mp4(read_at, file_size)
        else:
            found = []
    except (ValueError, IndexError, struct.error, OSError):
        return []
    return sorted(found, key=lambda c: c[0])[:MAX_CHAPTERS]


def from_percentages(text, total):
    """Chapter starts from Kodi's Player.Chapters info label ('0.00,12.50,...' percent of the
    running time), for a file this module can't read while Kodi is playing it."""
    out = []
    for part in (text or '').split(','):
        try:
            pct = float(part)
        except ValueError:
            continue
        out.append((total * pct / 100.0, None, ''))
    return out


GENERIC = re.compile(r'^\s*(chapter|chapitre|kapitel|cap[ií]tulo|capitolo|hoofdstuk|ch\.?)?\s*#?\d+\s*$'
                     r'|^\s*\d{1,2}:\d{2}(:\d{2})?([.,]\d+)?\s*$', re.IGNORECASE)


def scenes(chapters, runtime, default_name, min_length=1.0):
    """[(name, start, end)] scenes made from chapters: each ends where the next begins (or at its
    own end, or the end of the video). A chapter name that is only a number or a time gives way
    to default_name ('Chapter {}') - the file's names are kept, none are invented."""
    out = []
    starts = [c[0] for c in chapters]
    for i, (start, end, name) in enumerate(chapters):
        stop = end if end and end > start else (starts[i + 1] if i + 1 < len(starts) else runtime)
        if not stop or stop - start < min_length:
            continue
        label = name if name and not GENERIC.match(name) else default_name.format(i + 1)
        out.append((label, round(start, 2), round(stop, 2)))
    return out
