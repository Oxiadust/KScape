"""Scenes and Demo Scripts in the views: making scenes during playback, editing them, organising
Demo Scripts, and asking the playback service (demoservice.py) to play them.

Making a scene (playback controls -> Mark scene start, later Mark scene end, or C -> Create
Scene on the playing movie): the first press notes where playback is; the second notes the end,
pauses, and opens the scene editor - name, start, end (typed as H:MM:SS, checked: the end must
come after the start, a scene lasts at least a second and ends within the video), description -
with the length worked out. Save stores it; playback resumes either way.

Scenes come from library movies and TV episodes only.
"""
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from . import scenemodel as SM
from .demoservice import request
from .library import rpc

ADDON = xbmcaddon.Addon('script.kscape.wall')
HOME = xbmcgui.Window(10000)
PATH = xbmcvfs.translatePath('special://profile/addon_data/script.kscape.wall/scenes.json')
PROP_START, PROP_FILE = 'kscape.scene.start', 'kscape.scene.file'
MEDIA_OF_KIND = {'movies': 'movie', 'tv': 'episode'}
TRANSITION_NAMES = {'cut': 32263, 'fade': 32264, 'black': 32265}
WHY = {'order': 32229, 'short': 32230, 'runtime': 32231, 'negative': 32229}


def tr(string_id):
    return ADDON.getLocalizedString(string_id)


def store():
    return SM.Store(PATH)


def notify(text, ms=4000):
    xbmcgui.Dialog().notification('KScape', text, xbmcgui.NOTIFICATION_INFO, ms, False)


def count_text(n, one, many):
    return tr(one) if n == 1 else tr(many).format(n)


# ---- what is playing ----------------------------------------------------------------------------

def playing():
    """The library movie or episode playing now: {media, dbid, file, title, time, total, poster},
    or None (nothing, not video, or not from the library)."""
    for p in rpc('Player.GetActivePlayers', {}) or []:
        if p.get('type') != 'video':
            continue
        pid = p['playerid']
        item = (rpc('Player.GetItem', {'playerid': pid, 'properties': [
            'file', 'title', 'showtitle', 'season', 'episode', 'art']}) or {}).get('item') or {}
        if item.get('type') not in SM.MEDIA or not item.get('id'):
            return None
        props = rpc('Player.GetProperties', {'playerid': pid, 'properties': ['time', 'totaltime']}) or {}
        secs = lambda t: (t or {}).get('hours', 0) * 3600 + (t or {}).get('minutes', 0) * 60 + \
            (t or {}).get('seconds', 0) + (t or {}).get('milliseconds', 0) / 1000.0
        art = item.get('art') or {}
        if item['type'] == 'episode':
            title = f'{item.get("showtitle", "")} {item.get("season", 0)}x{item.get("episode", 0):02d}'
            if item.get('title'):
                title += f' · {item["title"]}'
            poster = art.get('tvshow.poster') or art.get('season.poster') or art.get('thumb') or ''
        else:
            title = item.get('title') or item.get('label') or ''
            poster = art.get('poster') or art.get('thumb') or ''
        return {'media': item['type'], 'dbid': int(item['id']), 'file': item.get('file') or '', 'title': title,
                'time': secs(props.get('time')), 'total': secs(props.get('totaltime')), 'poster': poster,
                'pid': pid}
    return None


def mark():
    """Mark scene start / Mark scene end, from the playback controls."""
    now = playing()
    if not now or not now['file']:
        notify(tr(32234))
        return
    start = HOME.getProperty(PROP_START)
    if not start or HOME.getProperty(PROP_FILE) != now['file']:
        HOME.setProperty(PROP_START, f'{now["time"]:.2f}')
        HOME.setProperty(PROP_FILE, now['file'])
        notify(tr(32218).format(SM.clock(now['time'])), 6000)
        return
    HOME.clearProperty(PROP_START)
    HOME.clearProperty(PROP_FILE)
    begin, end = float(start), now['time']
    if end < begin:
        begin, end = end, begin                     # marked backwards after seeking back: swap
    was_playing = not xbmc.getCondVisibility('Player.Paused')
    if was_playing:
        xbmc.Player().pause()
    try:
        draft = {'name': f'{now["title"]} · {SM.clock(begin)}', 'start': begin, 'end': end, 'description': ''}
        result = editor(draft, now['total'], tr(32219))
        if result:
            st = store()
            st.add_scene(now['media'], now['dbid'], now['file'], now['title'], result['name'], result['start'],
                         result['end'], result['description'], poster=now['poster'])
            notify(tr(32233).format(result['name']))
    finally:
        if was_playing and xbmc.getCondVisibility('Player.Paused'):
            xbmc.Player().pause()


def ask_time(heading, value):
    text = xbmcgui.Dialog().input(tr(heading), SM.clock(value), type=xbmcgui.INPUT_ALPHANUM)
    if not text:
        return None
    t = SM.parse_clock(text)
    if t is None:
        xbmcgui.Dialog().ok(tr(heading), tr(32232))
    return t


def editor(draft, runtime=0, heading=None):
    """The scene editor: returns the edited {name, start, end, description}, or None if
    cancelled. Times are checked before Save is accepted."""
    d = dict(draft)
    while True:
        rows = [('name', tr(32220).format(d['name'])), ('start', tr(32221).format(SM.clock(d['start']))),
                ('end', tr(32222).format(SM.clock(d['end']))),
                ('length', tr(32223).format(SM.clock(max(0, d['end'] - d['start'])))),
                ('description', tr(32225).format(d.get('description') or '-')), ('save', tr(32224))]
        i = xbmcgui.Dialog().select(heading or tr(32236), [label for _, label in rows],
                                    preselect=len(rows) - 1)
        if i < 0:
            return None
        key = rows[i][0]
        if key == 'name':
            name = xbmcgui.Dialog().input(tr(32228), d['name'], type=xbmcgui.INPUT_ALPHANUM).strip()
            d['name'] = name or d['name']
        elif key in ('start', 'end'):
            t = ask_time(32226 if key == 'start' else 32227, d[key])
            if t is not None:
                d[key] = t
        elif key == 'description':
            d['description'] = xbmcgui.Dialog().input(tr(32235), d.get('description', ''),
                                                      type=xbmcgui.INPUT_ALPHANUM).strip()
        elif key == 'save':
            why = SM.check_times(d['start'], d['end'], runtime)
            if why:
                xbmcgui.Dialog().ok(heading or tr(32236), tr(WHY[why]))
                continue
            return d


# ---- scene and script actions ---------------------------------------------------------------------

def runtime_of(scene):
    if scene['media'] == 'movie':
        d = rpc('VideoLibrary.GetMovieDetails', {'movieid': scene['dbid'], 'properties': ['runtime']}).get('moviedetails')
    else:
        d = rpc('VideoLibrary.GetEpisodeDetails', {'episodeid': scene['dbid'], 'properties': ['runtime']}).get('episodedetails')
    return float((d or {}).get('runtime') or 0)


def edit_scene(st, sid):
    s = st.scene(sid)
    if not s:
        return False
    result = editor(s, runtime_of(s))
    if not result:
        return False
    st.update_scene(sid, name=result['name'], start=result['start'], end=result['end'],
                    description=result['description'])
    return True


def rename_scene(st, sid):
    s = st.scene(sid)
    if not s:
        return False
    name = xbmcgui.Dialog().input(tr(32228), s['name'], type=xbmcgui.INPUT_ALPHANUM).strip()
    if name and name != s['name']:
        st.update_scene(sid, name=name)
        return True
    return False


def delete_scene(st, sid):
    s = st.scene(sid)
    if s and xbmcgui.Dialog().yesno(tr(32170).format(s['name']), tr(32238)):
        st.delete_scene(sid)
        return True
    return False


def new_script(st, scene_ids=()):
    name = xbmcgui.Dialog().input(tr(32245), '', type=xbmcgui.INPUT_ALPHANUM).strip()
    return st.add_script(name, scene_ids) if name else None


def add_to_scripts(st, sid):
    """Add a scene to one or more Demo Scripts (or a new one)."""
    s = st.scene(sid)
    if not s:
        return False
    options = [d['name'] for d in st.scripts] + [tr(32261)]
    chosen = xbmcgui.Dialog().multiselect(tr(32288).format(s['name']), options)
    if not chosen:
        return False
    for i in chosen:
        if i < len(st.scripts):
            st.add_to_script(st.scripts[i]['id'], sid)
        else:
            new_script(st, [sid])
    return True


def choose_scene(scenes, heading=None):
    if not scenes:
        return None
    if len(scenes) == 1:
        return scenes[0]
    i = xbmcgui.Dialog().select(heading or tr(32287), [f'{s["name"]}  ({SM.clock(SM.duration(s))})' for s in scenes])
    return scenes[i] if i >= 0 else None


def rename_script(st, did):
    d = st.script(did)
    if not d:
        return False
    name = xbmcgui.Dialog().input(tr(32245), d['name'], type=xbmcgui.INPUT_ALPHANUM).strip()
    if name and name != d['name']:
        st.update_script(did, name=name)
        return True
    return False


def duplicate_script(st, did):
    d = st.script(did)
    return st.duplicate_script(did, tr(32262).format(d['name'])) if d else None


def delete_script(st, did):
    d = st.script(did)
    if d and xbmcgui.Dialog().yesno(tr(32170).format(d['name']), tr(32239)):
        st.delete_script(did)
        return True
    return False


def loop_text(st, d):
    if d.get('loop') == 'script':
        return tr(32269)
    if d.get('loop') == 'scene':
        s = st.scene(d.get('loop_scene', ''))
        return tr(32270).format(s['name'] if s else '-')
    return tr(32268)


def options_text(st, d):
    t = tr(TRANSITION_NAMES.get(d.get('transition'), 32263))
    if d.get('transition') != 'cut':
        t += f' ({d.get("transition_s", 0):g} s)'
    return f'{tr(32266).format(t)}  ·  {tr(32271).format(loop_text(st, d))}'


def edit_script(st, did):
    """Name, description and playback options of a Demo Script."""
    changed = False
    while True:
        d = st.script(did)
        if not d:
            return changed
        t = tr(TRANSITION_NAMES.get(d.get('transition'), 32263))
        rows = [('name', tr(32220).format(d['name'])), ('description', tr(32225).format(d.get('description') or '-')),
                ('transition', tr(32266).format(t))]
        if d.get('transition') != 'cut':
            rows.append(('secs', tr(32267).format(f'{d.get("transition_s", 0):g}')))
        rows += [('loop', tr(32271).format(loop_text(st, d))), ('done', tr(32273))]
        i = xbmcgui.Dialog().select(tr(32257), [label for _, label in rows], preselect=len(rows) - 1)
        if i < 0 or rows[i][0] == 'done':
            return changed
        key = rows[i][0]
        if key == 'name':
            changed |= rename_script(st, did)
        elif key == 'description':
            text = xbmcgui.Dialog().input(tr(32235), d.get('description', ''), type=xbmcgui.INPUT_ALPHANUM)
            st.update_script(did, description=text.strip())
            changed = True
        elif key == 'transition':
            keys = list(SM.TRANSITIONS)
            j = xbmcgui.Dialog().select(tr(32266).format(''), [tr(TRANSITION_NAMES[k]) for k in keys],
                                        preselect=keys.index(d.get('transition', 'cut')))
            if j >= 0:
                st.update_script(did, transition=keys[j])
                changed = True
        elif key == 'secs':
            values = [0.5, 1, 2, 3, 5, 8]
            j = xbmcgui.Dialog().select(tr(32267).format(''), [f'{v:g} s' for v in values])
            if j >= 0:
                st.update_script(did, transition_s=values[j])
                changed = True
        elif key == 'loop':
            j = xbmcgui.Dialog().select(tr(32271).format(''), [tr(32268), tr(32269), tr(32270).format('…')])
            if j == 0:
                st.update_script(did, loop='once', loop_scene='')
            elif j == 1:
                st.update_script(did, loop='script', loop_scene='')
            elif j == 2:
                s = choose_scene(SM.script_scenes(d, st.by_id()), tr(32272))
                if s:
                    st.update_script(did, loop='scene', loop_scene=s['id'])
            changed |= j >= 0


def play_scene(sid):
    request('play', scenes=[sid], start=0)


def play_script(st, did, start=0):
    d = st.script(did)
    if not d:
        return
    ids = [s['id'] for s in SM.script_scenes(d, st.by_id())]
    if not ids:
        notify(tr(32282))
        return
    request('play', scenes=ids, start=start, script=did)


# ---- rows for the Collections view -----------------------------------------------------------------

class Row:
    """A scene or Demo Script shown in the Collections view, with the attributes the view reads
    from a movie (title, poster, badge, key)."""
    badge = ''
    file = ''

    def __init__(self, kind, data, title, poster, sub):
        self.kind = kind                 # 'scene' or 'script'
        self.data = data
        self.title = title
        self.poster = poster
        self.sub = sub
        self.key = data['id']
        self.year = 0


def scene_rows(st, media, library_keys=None, posters=None):
    """Scenes of `media`, grouped by movie or episode; scenes whose video left the library say so.
    `posters` ({dbid: artwork}) stands in for scenes saved without artwork."""
    rows = []
    for s in SM.by_media(st.scenes, media):
        gone = library_keys is not None and s['dbid'] not in library_keys
        detail = tr(32277) if gone else s.get('title', '')
        art = s.get('thumbnail') or s.get('poster') or (posters or {}).get(s['dbid'], '')
        rows.append(Row('scene', s, s['name'], art,
                        f'{detail}  ·  {SM.clock(SM.duration(s))}'))
    return rows


def script_rows(st):
    by_id = st.by_id()
    rows = []
    for d in st.scripts:
        scenes = SM.script_scenes(d, by_id)
        cover = next((s.get('thumbnail') or s.get('poster', '') for s in scenes if s.get('thumbnail') or s.get('poster')), '')
        sub = f'{count_text(len(scenes), 32213, 32212)}  ·  {SM.clock(SM.total_duration(d, by_id))}'
        rows.append(Row('script', d, d['name'], cover, sub))
    return rows


def episode_ids_of(tvshowid):
    result = rpc('VideoLibrary.GetEpisodes', {'tvshowid': tvshowid, 'properties': []})
    return {int(e['episodeid']) for e in result.get('episodes', [])}


def scenes_for_item(st, kind, item):
    """Scenes of a movie, or of a TV show's episodes."""
    if kind.name == 'movies':
        return st.scenes_of('movie', item.key)
    ids = episode_ids_of(item.key)
    return [s for s in SM.by_media(st.scenes, 'episode') if s['dbid'] in ids]


def is_playing(item):
    """Whether `item` (a movie) is what the video player is playing."""
    now = playing()
    return bool(now and now['media'] == 'movie' and now['dbid'] == item.key)


def library_movie_ids():
    result = rpc('VideoLibrary.GetMovies', {})
    return {int(m['movieid']) for m in result.get('movies', [])}


def library_episode_ids():
    result = rpc('VideoLibrary.GetEpisodes', {})
    return {int(e['episodeid']) for e in result.get('episodes', [])}



# ---- C menu entries on a movie or TV show ----------------------------------------------------------

ITEM_CHOICES = ('viewscenes', 'createscene', 'scene2script')


def item_entries(kind, item, st):
    """View Scenes and Add Scene to Demo Script… when the movie (or the show's episodes) has
    scenes; Create Scene (Mark scene end once started) when that movie is playing."""
    if kind.name not in MEDIA_OF_KIND or st is None:
        return []
    found = scenes_for_item(st, kind, item)
    entries = [('viewscenes', tr(32253))] if found else []
    if kind.name == 'movies' and is_playing(item):
        entries.append(('createscene', tr(32217 if HOME.getProperty(PROP_START) else 32254)))
    if found:
        entries.append(('scene2script', tr(32255)))
    return entries


def handle_item_choice(kind, item, choice, st):
    """Run a choice from item_entries. For View Scenes returns the scene id to show first (the
    caller opens the Scenes collection on it)."""
    if choice == 'viewscenes':
        found = scenes_for_item(st, kind, item)
        return found[0]['id'] if found else None
    if choice == 'createscene':
        mark()
    elif choice == 'scene2script':
        s = choose_scene(scenes_for_item(st, kind, item))
        if s:
            add_to_scripts(st, s['id'])
    return None
