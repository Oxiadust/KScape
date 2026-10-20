"""Scenes and Demo Scripts (pure Python): what is saved, and the rules for playing them.

A scene is a bookmarked stretch of a library movie or TV episode: a name, the video it comes
from (Kodi's database id and the file, which is what is played - the video itself is never
copied or changed), start and end in seconds, and an optional description. A Demo Script is
an ordered list of scene ids with playback options: how one scene gives way to the next
(transition) and what happens at the end (loop).

Both live in one JSON file in the add-on's profile folder, apart from Kodi's metadata. Scripts
refer to scenes by id, so renaming or re-timing a scene changes it everywhere; deleting a
scene removes it from every script; deleting a script never touches its scenes.

    {"version": 1, "next": 7,
     "scenes":  [{"id": "s1", "media": "movie", "dbid": 125, "file": "...", "title": "Heat",
                  "name": "Lobby Shootout", "start": 6270.0, "end": 6460.0, "description": "",
                  "thumbnail": "", "favourite": false, "created": "2026-10-18 20:15:00"}],
     "scripts": [{"id": "d2", "name": "Home Theater Showcase", "description": "",
                  "scenes": ["s1"], "transition": "black", "transition_s": 2.0,
                  "loop": "once", "loop_scene": ""}]}
"""
import json
import os
import re
import time

MEDIA = ('movie', 'episode')
TRANSITIONS = ('cut', 'fade', 'black')
LOOPS = ('once', 'script', 'scene')
MIN_SCENE_S = 1.0
DEFAULT_TRANSITION_S = 2.0


# ---- times -------------------------------------------------------------------------------------

def clock(seconds):
    """1:02:03, or 2:03 under an hour."""
    s = int(round(max(0.0, seconds or 0)))
    h, m, s = s // 3600, s // 60 % 60, s % 60
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'


CLOCK_RE = re.compile(r'^\s*(?:(\d+):)?(\d{1,2}):(\d{1,2}(?:\.\d+)?)\s*$')


def parse_clock(text):
    """Seconds from 'H:MM:SS', 'M:SS' or plain seconds; None if it is not a time."""
    text = (text or '').strip()
    if re.fullmatch(r'\d+(\.\d+)?', text):
        return float(text)
    m = CLOCK_RE.match(text)
    if not m:
        return None
    h, mi, s = int(m.group(1) or 0), int(m.group(2)), float(m.group(3))
    if mi >= 60 or s >= 60:
        return None
    return h * 3600 + mi * 60 + s


def check_times(start, end, runtime=0):
    """None when start/end make a scene, else why not: 'order' (end not after start),
    'short' (under MIN_SCENE_S), 'negative', or 'runtime' (past the end of the video)."""
    if start is None or end is None or start < 0 or end < 0:
        return 'negative'
    if end <= start:
        return 'order'
    if end - start < MIN_SCENE_S:
        return 'short'
    if runtime and end > runtime + 1:
        return 'runtime'
    return None


def duration(scene):
    return max(0.0, float(scene['end']) - float(scene['start']))


# ---- scripts -------------------------------------------------------------------------------------

def script_scenes(script, scenes_by_id):
    """The script's scenes in order, skipping ids whose scene no longer exists."""
    return [scenes_by_id[i] for i in script.get('scenes', []) if i in scenes_by_id]


def total_duration(script, scenes_by_id):
    return sum(duration(s) for s in script_scenes(script, scenes_by_id))


def next_index(index, count, loop, looping_scene=False):
    """Where playback goes after scene `index` of `count` ends: the same index for a looped
    scene, the next one, the first again when the script loops, or None at the end."""
    if count <= 0:
        return None
    if looping_scene:
        return index
    if index + 1 < count:
        return index + 1
    return 0 if loop == 'script' else None


def by_media(scenes, media):
    """Scenes of one kind (movie or episode), grouped by title and in order within it."""
    return sorted((s for s in scenes if s.get('media') == media),
                  key=lambda s: (s.get('title', '').casefold(), float(s['start']), s['id']))


# ---- store ---------------------------------------------------------------------------------------

class Store:
    """Scenes and scripts, saved to `path` after every change (and re-read when another process -
    the playback service or another view - changed it)."""

    def __init__(self, path):
        self.path = path
        self.scenes = []
        self.scripts = []
        self.next = 1
        self.stamp = None
        self.load()

    def _stamp(self):
        try:
            st = os.stat(self.path)
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def load(self):
        self.stamp = self._stamp()
        try:
            with open(self.path) as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        self.scenes = [s for s in data.get('scenes') or [] if s.get('id') and s.get('file')]
        self.scripts = [d for d in data.get('scripts') or [] if d.get('id')]
        ids = [int(x['id'][1:]) for x in self.scenes + self.scripts if x['id'][1:].isdigit()]
        self.next = max([int(data.get('next') or 1)] + [i + 1 for i in ids])

    def poll(self):
        if self._stamp() != self.stamp:
            self.load()
            return True
        return False

    def save(self):
        data = {'version': 1, 'next': self.next, 'scenes': self.scenes, 'scripts': self.scripts}
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + '.tmp'
            with open(tmp, 'w') as f:
                json.dump(data, f, indent=1)
            os.replace(tmp, self.path)
        except OSError:
            pass
        self.stamp = self._stamp()

    def _id(self, prefix):
        i = f'{prefix}{self.next}'
        self.next += 1
        return i

    def by_id(self):
        return {s['id']: s for s in self.scenes}

    def scene(self, sid):
        return next((s for s in self.scenes if s['id'] == sid), None)

    def script(self, did):
        return next((d for d in self.scripts if d['id'] == did), None)

    # scenes

    def add_scene(self, media, dbid, file, title, name, start, end, description='', thumbnail='', poster=''):
        if media not in MEDIA:
            raise ValueError(media)
        why = check_times(start, end)
        if why:
            raise ValueError(why)
        scene = {'id': self._id('s'), 'media': media, 'dbid': int(dbid), 'file': file, 'title': title,
                 'name': name, 'start': round(float(start), 2), 'end': round(float(end), 2),
                 'description': description, 'thumbnail': thumbnail, 'poster': poster,
                 'favourite': False, 'created': time.strftime('%Y-%m-%d %H:%M:%S')}
        self.scenes.append(scene)
        self.save()
        return scene['id']

    def update_scene(self, sid, **fields):
        s = self.scene(sid)
        if s is None:
            return False
        start = float(fields.get('start', s['start']))
        end = float(fields.get('end', s['end']))
        why = check_times(start, end)
        if why:
            raise ValueError(why)
        for k in ('name', 'description', 'thumbnail'):
            if k in fields:
                s[k] = fields[k]
        if 'favourite' in fields:
            s['favourite'] = bool(fields['favourite'])
        s['start'], s['end'] = round(start, 2), round(end, 2)
        self.save()
        return True

    def delete_scene(self, sid):
        self.scenes = [s for s in self.scenes if s['id'] != sid]
        for d in self.scripts:
            d['scenes'] = [i for i in d.get('scenes', []) if i != sid]
            if d.get('loop_scene') == sid:
                d['loop_scene'] = ''
        self.save()

    def scenes_of(self, media, dbid):
        return [s for s in by_media(self.scenes, media) if s.get('dbid') == dbid]

    def has_scene(self, media, dbid, start, end, slack=0.5):
        """Whether that video already has a scene with these times (chapters imported twice)."""
        return any(abs(float(s['start']) - start) <= slack and abs(float(s['end']) - end) <= slack
                   for s in self.scenes_of(media, dbid))

    # scripts

    def add_script(self, name, scene_ids=()):
        d = {'id': self._id('d'), 'name': name, 'description': '', 'scenes': list(scene_ids),
             'transition': 'black', 'transition_s': DEFAULT_TRANSITION_S, 'loop': 'once', 'loop_scene': ''}
        self.scripts.append(d)
        self.save()
        return d['id']

    def update_script(self, did, **fields):
        d = self.script(did)
        if d is None:
            return False
        if 'transition' in fields and fields['transition'] not in TRANSITIONS:
            raise ValueError(fields['transition'])
        if 'loop' in fields and fields['loop'] not in LOOPS:
            raise ValueError(fields['loop'])
        for k in ('name', 'description', 'transition', 'loop', 'loop_scene'):
            if k in fields:
                d[k] = fields[k]
        if 'transition_s' in fields:
            d['transition_s'] = max(0.0, min(10.0, float(fields['transition_s'])))
        self.save()
        return True

    def delete_script(self, did):
        self.scripts = [d for d in self.scripts if d['id'] != did]
        self.save()

    def duplicate_script(self, did, name):
        d = self.script(did)
        if d is None:
            return None
        copy = dict(d, id=self._id('d'), name=name, scenes=list(d.get('scenes', [])))
        self.scripts.append(copy)
        self.save()
        return copy['id']

    def add_to_script(self, did, sid):
        d = self.script(did)
        if d is not None and self.scene(sid) is not None:
            d.setdefault('scenes', []).append(sid)
            self.save()

    def remove_from_script(self, did, index):
        """Take the scene at `index` out of the script (the scene itself stays)."""
        d = self.script(did)
        if d is not None and 0 <= index < len(d.get('scenes', [])):
            removed = d['scenes'].pop(index)
            if d.get('loop_scene') == removed and removed not in d['scenes']:
                d['loop_scene'] = ''
            self.save()

    def move_in_script(self, did, index, step):
        d = self.script(did)
        if d is None:
            return index
        order = d.get('scenes', [])
        j = index + step
        if 0 <= index < len(order) and 0 <= j < len(order):
            order[index], order[j] = order[j], order[index]
            self.save()
            return j
        return index

    def scripts_with(self, sid):
        return [d for d in self.scripts if sid in d.get('scenes', [])]
