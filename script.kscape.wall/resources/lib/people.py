"""What the media information screens list, built from Kodi's JSON-RPC details (pure Python).

Cast & Crew rows (directors, writers, cast with their portraits), the Details page of a movie,
show, episode, album, song and artist (label / value rows), and a person's profile text. Only
what Kodi (or an optional provider, see metadata.py) has is listed: a missing field is left
out, never shown empty. `tr` maps a string id to its localized text; `lang` turns a language
code into its name.
"""
from . import info
from . import s as S
from . import streaminfo as SI


def _names(value):
    if isinstance(value, str):
        return [value] if value else []
    return [v for v in (value or []) if v]


def join(value, sep=', '):
    return sep.join(_names(value))


# ---- people -----------------------------------------------------------------------------------

def cast_rows(d, tr):
    """[{'name', 'role', 'thumb', 'department'}]: directors, then writers, then the cast in
    billing order. A person credited more than once is one row with every role, and a crew
    member who also acts takes the portrait of the cast entry."""
    d = d or {}
    rows, index = [], {}

    def add(name, role, thumb, department):
        if not name:
            return
        row = index.get(name)
        if row is None:
            row = {'name': name, 'roles': [], 'thumb': '', 'department': department}
            index[name] = row
            rows.append(row)
        if role and role not in row['roles']:
            row['roles'].append(role)
        row['thumb'] = row['thumb'] or thumb or ''

    for name in _names(d.get('director')):
        add(name, tr(S.P_DIRECTOR), '', 'Directing')
    for name in _names(d.get('writer')):
        add(name, tr(S.P_WRITER), '', 'Writing')
    for c in sorted(d.get('cast') or [], key=lambda c: c.get('order', 0)):
        add(c.get('name'), c.get('role') or '', c.get('thumbnail'), 'Acting')
        if c.get('name') in index:
            index[c['name']]['department'] = 'Acting'     # acting is the department that shows
    return [{'name': r['name'], 'role': ' · '.join(r['roles']), 'thumb': r['thumb'],
             'department': r['department']} for r in rows]


def person_summary(row, tr):
    """The line under a person's name in a movie: 'as Role' for an actor, else the crew job."""
    role = row.get('role') or ''
    crew = (tr(S.P_DIRECTOR), tr(S.P_WRITER))
    parts = [p for p in role.split(' · ') if p]
    characters = [p for p in parts if p not in crew]
    jobs = [p for p in parts if p in crew]
    if row.get('department') == 'Acting' and characters:
        return ' · '.join([tr(S.P_AS).format(characters[0])] + jobs)
    return role


def life_line(person, tr):
    """'Born 1964-09-02 in Beirut, Lebanon' / 'Born ... · Died ...' from a TMDB person record."""
    born, died, place = person.get('birthday'), person.get('deathday'), person.get('place')
    parts = []
    if born and place:
        parts.append(tr(S.P_BORN_IN).format(born, place))
    elif born:
        parts.append(tr(S.P_BORN).format(born))
    elif place:
        parts.append(place)
    if died:
        parts.append(tr(S.P_DIED).format(died))
    return ' · '.join(parts)


# ---- detail rows ------------------------------------------------------------------------------

def _row(label_id, value):
    if value in (None, '', [], ()):
        return None
    return (label_id, value if isinstance(value, str) else str(value))


def _rows(*pairs):
    return [r for r in (_row(a, b) for a, b in pairs) if r]


def _ratings_text(d):
    out = []
    tmdb = SI.tmdb_rating(d.get('ratings'))
    if tmdb:
        out.append(f'TMDB {tmdb:.1f}')
    rt = SI.rt_percent(d.get('ratings'))
    if rt:
        out.append(f'Rotten Tomatoes {rt}%')
    for name, r in (d.get('ratings') or {}).items():
        if name in SI.TMDB_KEYS or name in SI.RT_KEYS:
            continue
        value = r.get('rating') if isinstance(r, dict) else None
        if value:
            out.append(f'{name.upper() if len(name) <= 4 else name.title()} {value:.1f}')
    return ' · '.join(out)


def _languages(streamdetails, kind, lang):
    seen = []
    for s in (streamdetails or {}).get(kind) or []:
        code = s.get('language') or ''
        if code:
            name = lang(code)
            if name and name not in seen:
                seen.append(name)
    return seen


def _date_time(stamp):
    return (stamp or '')[:16] if stamp and not stamp.startswith('0000') else ''


def _video_line(d):
    v = SI.first_video(d.get('streamdetails')) if d.get('streamdetails') else {}
    if not v:
        return ''
    parts = []
    if v.get('width') and v.get('height'):
        parts.append(f'{v["width"]}×{v["height"]}')
    if v.get('codec'):
        parts.append(v['codec'].upper())
    hdr = SI.hdr(d.get('streamdetails'))
    if hdr and hdr != 'sdr':
        parts.append(SI.HDR_LABELS.get(hdr, hdr))
    aspect = SI.aspect(d.get('streamdetails'))
    if aspect:
        parts.append(f'{aspect:.2f}:1')
    return ' · '.join(parts)


def _audio_line(d):
    out = []
    for a in ((d.get('streamdetails') or {}).get('audio') or [])[:4]:
        bits = [(a.get('codec') or '').upper(), f'{a["channels"]} ch' if a.get('channels') else '']
        text = ' '.join(b for b in bits if b)
        if text and text not in out:
            out.append(text)
    return ' · '.join(out)


def _ids(d):
    ids = d.get('uniqueid') or {}
    return ' · '.join(f'{k.upper() if len(k) <= 4 else k.title()} {v}' for k, v in ids.items() if v)


def movie_rows(d, extra, tr, lang=lambda c: c):
    """The movie's Details page: [(label id, value)] from Kodi's details, plus `extra` (metadata.py
    answer: budget, revenue, companies, original language, awards) when a provider gave one."""
    d, extra = d or {}, extra or {}
    sd = d.get('streamdetails')
    original = d.get('originaltitle') or extra.get('original_title') or ''
    if original == d.get('title'):
        original = ''
    language = extra.get('original_language') or ''
    return _rows(
        (S.D_ORIGINAL_TITLE, original),
        (S.D_TAGLINE, d.get('tagline') or extra.get('tagline')),
        (S.D_RELEASED, d.get('premiered') or extra.get('released') or (str(d['year']) if d.get('year') else '')),
        (S.D_RUNTIME, info.runtime_words(d.get('runtime'), tr)),
        (S.D_GENRES, join(d.get('genre'))),
        (S.D_DIRECTORS, join(d.get('director'))),
        (S.D_WRITERS, join(d.get('writer'))),
        (S.D_STUDIOS, join(d.get('studio'))),
        (S.D_COMPANIES, join(extra.get('companies'))),
        (S.D_COUNTRY, join(d.get('country')) or join(extra.get('countries'))),
        (S.D_LANGUAGE, lang(language) if language else ''),
        (S.D_AUDIO_LANGS, join(_languages(sd, 'audio', lang))),
        (S.D_SUBTITLES, join(_languages(sd, 'subtitle', lang))),
        (S.D_CERT, (d.get('mpaa') or '').strip()),
        (S.D_RATINGS, _ratings_text(d)),
        (S.D_USER_RATING, f'{d["userrating"]}/10' if d.get('userrating') else ''),
        (S.D_TOP250, f'#{d["top250"]}' if d.get('top250') else ''),
        (S.D_TAGS, join(d.get('tag'))),
        (S.D_COLLECTION, d.get('set') or ''),
        (S.D_BUDGET, extra.get('budget')),
        (S.D_REVENUE, extra.get('revenue')),
        (S.D_AWARDS, extra.get('awards')),
        (S.D_VIDEO, _video_line(d)),
        (S.D_AUDIO, _audio_line(d)),
        (S.D_PLAYS, str(d['playcount']) if d.get('playcount') else ''),
        (S.D_LAST_PLAYED, _date_time(d.get('lastplayed'))),
        (S.D_ADDED, _date_time(d.get('dateadded'))),
        (S.D_IDS, _ids(d)),
        (S.D_FILE, d.get('file') or ''),
    )


def show_rows(d, seasons, tr):
    """A TV show's Details page."""
    d = d or {}
    return _rows(
        (S.D_ORIGINAL_TITLE, d.get('originaltitle') if d.get('originaltitle') != d.get('title') else ''),
        (S.D_FIRST_AIRED, d.get('premiered') or (str(d['year']) if d.get('year') else '')),
        (S.D_NETWORK, join(d.get('studio'))),
        (S.D_STATUS, d.get('status') or ''),
        (S.D_GENRES, join(d.get('genre'))),
        (S.D_CERT, (d.get('mpaa') or '').strip()),
        (S.D_RATINGS, _ratings_text(d)),
        (S.D_USER_RATING, f'{d["userrating"]}/10' if d.get('userrating') else ''),
        (S.D_SEASONS, str(len([s for s in seasons or [] if s.get('season')])) if seasons else ''),
        (S.D_EPISODES, f'{d["episode"]}' + (f' ({d["watchedepisodes"]} watched)' if d.get('watchedepisodes') else '')
         if d.get('episode') else ''),
        (S.D_TAGS, join(d.get('tag'))),
        (S.D_LAST_PLAYED, _date_time(d.get('lastplayed'))),
        (S.D_ADDED, _date_time(d.get('dateadded'))),
        (S.D_IDS, _ids(d)),
        (S.D_FILE, d.get('file') or ''),
    )


def episode_rows(d, tr, lang=lambda c: c):
    """An episode's Details page."""
    d = d or {}
    sd = d.get('streamdetails')
    return _rows(
        (S.D_SEASON_EPISODE, f'S{d.get("season", 0):02d}E{d.get("episode", 0):02d}'),
        (S.D_AIRED, d.get('firstaired') or ''),
        (S.D_RUNTIME, info.runtime_words(d.get('runtime'), tr)),
        (S.D_DIRECTORS, join(d.get('director'))),
        (S.D_WRITERS, join(d.get('writer'))),
        (S.D_RATINGS, _ratings_text(d)),
        (S.D_AUDIO_LANGS, join(_languages(sd, 'audio', lang))),
        (S.D_SUBTITLES, join(_languages(sd, 'subtitle', lang))),
        (S.D_VIDEO, _video_line(d)),
        (S.D_AUDIO, _audio_line(d)),
        (S.D_PLAYS, str(d['playcount']) if d.get('playcount') else ''),
        (S.D_LAST_PLAYED, _date_time(d.get('lastplayed'))),
        (S.D_ADDED, _date_time(d.get('dateadded'))),
        (S.D_FILE, d.get('file') or ''),
    )


def _clock(seconds):
    return info.clock(seconds) if seconds else ''


def album_rows(d, songs, tr):
    """An album's Details page; `songs` are Kodi's song records (for the duration and credits)."""
    d = d or {}
    total = sum(s.get('duration') or 0 for s in songs or [])
    composers = []
    for s in songs or []:
        for c in s.get('contributors') or []:
            if 'composer' in (c.get('role') or '').lower() and c.get('name') and c['name'] not in composers:
                composers.append(c['name'])
    return _rows(
        (S.D_ARTIST, join(d.get('artist'), ' / ')),
        (S.D_RELEASED, d.get('releasedate') or d.get('originaldate') or (str(d['year']) if d.get('year') else '')),
        (S.D_ORIGINAL_DATE, d.get('originaldate') if d.get('originaldate') != d.get('releasedate') else ''),
        (S.D_GENRES, join(d.get('genre'))),
        (S.D_STYLES, join(d.get('style'))),
        (S.D_MOODS, join(d.get('mood'))),
        (S.D_THEMES, join(d.get('theme'))),
        (S.D_TYPE, d.get('type') or ''),
        (S.D_LABEL, d.get('albumlabel') or d.get('label') or ''),
        (S.D_RATING, f'{d["rating"]:.1f}' if d.get('rating') else ''),
        (S.D_USER_RATING, f'{d["userrating"]}/10' if d.get('userrating') else ''),
        (S.D_TRACKS, str(len(songs)) if songs else ''),
        (S.D_DURATION, _clock(total)),
        (S.D_COMPOSER, join(composers)),
        (S.D_PLAYS, str(d['playcount']) if d.get('playcount') else ''),
        (S.D_ADDED, _date_time(d.get('dateadded'))),
        (S.D_MUSICBRAINZ, d.get('musicbrainzalbumid') or ''),
    )


def _contributors(items):
    """'Producer: A, B · Mixer: C' from Kodi's contributors (name, role)."""
    roles = {}
    for c in items or []:
        roles.setdefault((c.get('role') or '').strip(), []).append(c.get('name') or '')
    return ' · '.join(f'{role}: {", ".join(n for n in names if n)}' if role else ', '.join(names)
                      for role, names in roles.items())


def song_rows(d, tr):
    """A song's information page (every credit Kodi has, and the file's audio facts)."""
    d = d or {}
    return _rows(
        (S.D_ARTIST, join(d.get('artist'), ' / ')),
        (S.D_ALBUM, d.get('album') or ''),
        (S.D_TRACK, (f'{d["disc"]}-{d["track"]}' if d.get('disc', 0) > 1 else str(d['track'])) if d.get('track') else ''),
        (S.D_DURATION, _clock(d.get('duration'))),
        (S.D_GENRES, join(d.get('genre'))),
        (S.D_YEAR, str(d['year']) if d.get('year') else ''),
        (S.D_COMPOSER, d.get('displaycomposer') or ''),
        (S.D_LYRICIST, d.get('displaylyricist') or ''),
        (S.D_CONDUCTOR, d.get('displayconductor') or ''),
        (S.D_CREDITS, _contributors(d.get('contributors'))),
        (S.D_ORIGINAL_DATE, d.get('originaldate') or ''),
        (S.D_CODEC, (d.get('file') or '').rsplit('.', 1)[-1].upper() if '.' in (d.get('file') or '') else ''),
        (S.D_BITRATE, f'{d["bitrate"] // 1000} kbps' if d.get('bitrate') else ''),
        (S.D_SAMPLE_RATE, f'{d["samplerate"] / 1000:g} kHz' if d.get('samplerate') else ''),
        (S.D_CHANNELS, str(d['channels']) if d.get('channels') else ''),
        (S.D_RATING, f'{d["userrating"]}/10' if d.get('userrating') else ''),
        (S.D_PLAYS, str(d['playcount']) if d.get('playcount') else ''),
        (S.D_LAST_PLAYED, _date_time(d.get('lastplayed'))),
        (S.D_COMMENT, d.get('comment') or ''),
        (S.D_FILE, d.get('file') or ''),
    )


def artist_rows(d, tr):
    """An artist's facts (the Details page and the profile's summary)."""
    d = d or {}
    return _rows(
        (S.D_TYPE, d.get('type') or ''),
        (S.D_GENDER, d.get('gender') or ''),
        (S.D_BORN, d.get('born') or ''),
        (S.D_FORMED, d.get('formed') or ''),
        (S.D_DIED, d.get('died') or ''),
        (S.D_DISBANDED, d.get('disbanded') or ''),
        (S.D_YEARS_ACTIVE, join(d.get('yearsactive'))),
        (S.D_GENRES, join(d.get('genre'))),
        (S.D_STYLES, join(d.get('style'))),
        (S.D_MOODS, join(d.get('mood'))),
        (S.D_INSTRUMENTS, join(d.get('instrument'))),
        (S.D_SORT_NAME, d.get('sortname') if d.get('sortname') != d.get('artist') else ''),
        (S.D_MUSICBRAINZ, d.get('musicbrainzartistid') if isinstance(d.get('musicbrainzartistid'), str)
         else join(d.get('musicbrainzartistid'))),
    )


def artist_summary(d, tr):
    """'Born 1964 · Beirut · Rock, Pop' - the line under an artist's name."""
    d = d or {}
    life = d.get('born') or d.get('formed') or ''
    label = tr(S.D_BORN) if d.get('born') else tr(S.D_FORMED)
    parts = [f'{label} {life}' if life else '', d.get('died') and f'{tr(S.D_DIED)} {d["died"]}' or '',
             d.get('disbanded') and f'{tr(S.D_DISBANDED)} {d["disbanded"]}' or '', join(d.get('genre'))]
    return ' · '.join(p for p in parts if p)


def rows_to_text(rows, tr):
    """[(label id, value)] -> [(label, value)] in the user's language."""
    return [(tr(label), value) for label, value in rows]
