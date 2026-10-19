"""Scene and Demo Script playback: the service half of script.kscape.wall (service.py).

Kodi's skin can start a video but cannot stop it at a given time or chain timed scenes, so a
service add-on does it. The views ask for playback through Kodi's own notification channel
(JSONRPC.NotifyAll, sender script.kscape.wall, message kscape.demo: see request()); the service
then:

  1. Checks each scene's file still exists; missing ones are skipped (and reported).
  2. Builds a Kodi video playlist, one item per scene, each with a StartOffset so Kodi opens the
     file at the scene's start - no visible jump - and the remote's Next / Previous move between
     scenes as in any playlist.
  3. Counts a scene as started only once the player is really inside it (after onAVStarted,
     position within the scene); otherwise it seeks again, and gives up on the scene after
     LOAD_TIMEOUT_S.
  4. Ends each scene at its end time. Rather than polling, it sleeps until shortly before the end
     (re-checking at most every few seconds, and after any seek, pause or item change).
  5. Moves on: straight cut, fade to black (a black overlay fades in over the paused picture and
     out over the next scene) or a black pause, then the next scene, the first again if the
     script loops, the same one if it is the looped scene, or stops at the end.

Seeking outside the scene (or Keep watching in the controls) leaves demo mode: the video plays
on normally. Stop ends it. Playing scenes makes Kodi save resume points and play counts for
those movies and episodes, so the service puts back what they were when each one is done -
also after a Kodi restart in the middle of a demo (the snapshot is kept on disk).

Home window properties for the playback controls (VideoOSD.xml): kscape.demo.active, .scene,
.title, .progress, .script.
"""
import json
import os
import threading
import time

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from . import scenemodel as SM

ADDON_ID = 'script.kscape.wall'
ADDON = xbmcaddon.Addon(ADDON_ID)
HOME = xbmcgui.Window(10000)
FOLDER = xbmcvfs.translatePath(f'special://profile/addon_data/{ADDON_ID}/')
SCENES = os.path.join(FOLDER, 'scenes.json')
SNAPSHOT = os.path.join(FOLDER, 'demo-snapshot.json')
MESSAGE = 'kscape.demo'
LOAD_TIMEOUT_S = 15.0          # opening a file and reaching the scene
END_SLACK_S = 0.12             # end a scene this close to its end time
OWN_SEEK_S = 3.0               # seek events this soon after our own seek are ours
OUTSIDE_S = 2.0                # how far before the start counts as leaving the scene
JUMPED_S = 3.0                 # how far past the end counts as a seek away, not the scene's end
RESTORE_AFTER_S = (2.0, 6.0)   # put metadata back after Kodi saved it (twice: it may save late)
PROPS = ('active', 'scene', 'title', 'progress', 'script')


def tr(string_id):
    return ADDON.getLocalizedString(string_id)


def log(msg, level=xbmc.LOGINFO):
    xbmc.log(f'kscape.demo: {msg}', level)


def rpc(method, params):
    res = json.loads(xbmc.executeJSONRPC(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method,
                                                     'params': params})))
    if 'error' in res:
        log(f'{method} failed: {res["error"]}', xbmc.LOGWARNING)
        return {}
    return res.get('result') or {}


def request(cmd, **data):
    """Called from the views: send a command to the service."""
    rpc('JSONRPC.NotifyAll', {'sender': ADDON_ID, 'message': MESSAGE, 'data': dict(data, cmd=cmd)})


def notify(text, ms=4000):
    xbmcgui.Dialog().notification('KScape', text, xbmcgui.NOTIFICATION_INFO, ms, False)


# ---- resume points and play counts --------------------------------------------------------------

DETAILS = {'movie': ('VideoLibrary.GetMovieDetails', 'VideoLibrary.SetMovieDetails', 'movieid', 'moviedetails'),
           'episode': ('VideoLibrary.GetEpisodeDetails', 'VideoLibrary.SetEpisodeDetails', 'episodeid',
                       'episodedetails')}


def snapshot(items):
    """{'movie:125': {...}} of what playing scenes would change, for each (media, dbid)."""
    out = {}
    for media, dbid in items:
        get, _, key, result = DETAILS[media]
        d = rpc(get, {key: dbid, 'properties': ['resume', 'playcount', 'lastplayed']}).get(result)
        if d:
            r = d.get('resume') or {}
            out[f'{media}:{dbid}'] = {'position': float(r.get('position') or 0), 'total': float(r.get('total') or 0),
                                      'playcount': int(d.get('playcount') or 0), 'lastplayed': d.get('lastplayed') or ''}
    return out


def restore(entries):
    for k, v in entries.items():
        media, _, dbid = k.partition(':')
        _, set_, key, _ = DETAILS[media]
        rpc(set_, {key: int(dbid), 'resume': {'position': v['position'], 'total': v['total']},
                   'playcount': v['playcount'], 'lastplayed': v['lastplayed']})
    if entries:
        log(f'restored resume points and play counts of {len(entries)} item(s)')


def save_snapshot(entries):
    try:
        os.makedirs(FOLDER, exist_ok=True)
        with open(SNAPSHOT, 'w') as f:
            json.dump(entries, f)
    except OSError:
        pass


def recover():
    """After a Kodi restart in the middle of a demo: put back what the demo changed."""
    try:
        with open(SNAPSHOT) as f:
            entries = json.load(f)
    except (OSError, ValueError):
        return
    log('restoring after an interrupted demo')
    restore(entries)
    try:
        os.remove(SNAPSHOT)
    except OSError:
        pass


# ---- the black overlay used by transitions ------------------------------------------------------

class Black(xbmcgui.WindowXMLDialog):
    """Full-screen black over the video, fading in and out (script-kscape-black.xml)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self.engine = kwargs['engine']
        self.ms = kwargs['ms']
        self.ready = threading.Event()

    def onInit(self):
        img = self.getControl(10)
        img.setAnimations([('Visible', f'effect=fade start=0 end=100 time={self.ms}'),
                           ('Hidden', f'effect=fade start=100 end=0 time={self.ms}')])
        img.setVisible(True)
        self.ready.set()

    def onAction(self, action):
        if action.getId() in (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_STOP):
            self.engine.stop()


class Overlay:
    def __init__(self, engine):
        self.engine = engine
        self.win = None

    def show(self, fade_ms):
        if self.win is not None:
            return
        self.win = Black('script-kscape-black.xml', ADDON.getAddonInfo('path'), 'Default', '1080i',
                         engine=self.engine, ms=max(1, int(fade_ms)))
        self.win.show()
        self.win.ready.wait(2.0)

    def hide(self, fade_ms):
        win, self.win = self.win, None
        if win is None:
            return
        try:
            win.getControl(10).setVisible(False)
        except RuntimeError:
            pass
        time.sleep(max(0, fade_ms) / 1000.0)
        win.close()
        del win


# ---- the engine ----------------------------------------------------------------------------------

class Player(xbmc.Player):
    def __init__(self, engine):
        super().__init__()
        self.engine = engine

    def onPlayBackStarted(self):
        self.engine.on_item_starting()

    def onAVStarted(self):
        self.engine.on_started()

    def onPlayBackSeek(self, time_ms, offset_ms):
        self.engine.on_seek()

    def onPlayBackPaused(self):
        self.engine.wake.set()

    def onPlayBackResumed(self):
        self.engine.wake.set()

    def onPlayBackStopped(self):
        self.engine.on_stopped()

    def onPlayBackEnded(self):
        self.engine.on_ended()

    def onPlayBackError(self):
        self.engine.on_error()


class Monitor(xbmc.Monitor):
    def __init__(self, engine):
        super().__init__()
        self.engine = engine

    def onNotification(self, sender, method, data):
        if sender == ADDON_ID and method == f'Other.{MESSAGE}':
            try:
                self.engine.command(json.loads(data or '{}'))
            except ValueError:
                pass


class Engine:
    def __init__(self):
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.player = Player(self)
        self.monitor = Monitor(self)
        self.overlay = Overlay(self)
        self.session = None
        self.expect_stop = False
        self.own_seek = 0.0
        for p in PROPS:
            HOME.clearProperty(f'kscape.demo.{p}')
        recover()
        threading.Thread(target=self._worker, daemon=True).start()

    # ---- requests from the views and the playback controls -----------------------------------------

    def command(self, data):
        cmd = data.get('cmd')
        log(f'request {cmd}')
        if cmd == 'play':
            self.play(data.get('scenes') or [], int(data.get('start') or 0), data.get('script'))
        elif cmd in ('next', 'prev'):
            self.step(1 if cmd == 'next' else -1)
        elif cmd == 'exit':
            self.leave(tr(32246))
        elif cmd == 'stop':
            self.stop()

    def play(self, scene_ids, start=0, script_id=None):
        store = SM.Store(SCENES)
        script = store.script(script_id) if script_id else None
        wanted = [store.scene(i) for i in scene_ids]
        queue, missing = [], []
        first = None
        for i, s in enumerate(wanted):
            if s is None:
                continue
            if not xbmcvfs.exists(s['file']):
                missing.append(s)
                log(f'missing file for scene {s["id"]}: {s["file"]}', xbmc.LOGWARNING)
                continue
            if first is None and i >= start:
                first = len(queue)
            queue.append(s)
        if missing:
            notify(tr(32240).format(len(missing)) if len(missing) > 1 else tr(32241).format(missing[0]['name']), 6000)
        if not queue:
            log('nothing playable')
            return
        with self.lock:
            self._end_session(restore_all=True, stop=False)
            items = list(dict.fromkeys((s['media'], s['dbid']) for s in queue))
            snap = snapshot(items)
            save_snapshot(snap)
            self.session = {
                'queue': queue, 'index': first or 0, 'phase': 'switching', 'since': time.time(),
                'script': script['name'] if script else '',
                'transition': (script or {}).get('transition', 'cut'),
                'secs': float((script or {}).get('transition_s', 0)),
                'loop': (script or {}).get('loop', 'once'),
                'loop_scene': (script or {}).get('loop_scene', ''),
                'snapshot': snap, 'played': set(), 'restored': set(),
            }
            pl = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
            pl.clear()
            for s in queue:
                li = xbmcgui.ListItem(s.get('title') or s['name'], offscreen=True)
                li.getVideoInfoTag().setTitle(s.get('title') or s['name'])
                li.setProperty('StartOffset', f'{float(s["start"]):.3f}')
                if s.get('thumbnail') or s.get('poster'):
                    li.setArt({'thumb': s.get('thumbnail') or s.get('poster'), 'poster': s.get('poster', '')})
                pl.add(s['file'], li)
            self.playlist = pl
            log(f'playing {len(queue)} scene(s){" of " + script["name"] if script else ""}, from {self.session["index"] + 1}')
            self._props(queue[self.session['index']])
        self.player.play(pl, startpos=self.session['index'])

    def step(self, direction):
        with self.lock:
            s = self.session
            if not s:
                return
            j = s['index'] + direction
            if j < 0 or j >= len(s['queue']):
                if s['loop'] != 'script':
                    return
                j %= len(s['queue'])
        self._go(j)

    def stop(self):
        with self.lock:
            if not self.session:
                return
            log('stopped by the user')
            self._end_session(restore_all=True, stop=True)

    def leave(self, message=None):
        """Leave demo mode: the current video plays on normally."""
        with self.lock:
            s = self.session
            if not s:
                return
            pos = s['index']
            size = self.playlist.size()
            for p in range(size - 1, pos, -1):
                rpc('Playlist.Remove', {'playlistid': xbmc.PLAYLIST_VIDEO, 'position': p})
            for _ in range(pos):
                rpc('Playlist.Remove', {'playlistid': xbmc.PLAYLIST_VIDEO, 'position': 0})
            current = s['queue'][pos]
            keep = f'{current["media"]}:{current["dbid"]}'
            self._end_session(restore_all=True, stop=False, keep=keep)
            log('left demo mode; normal playback')
        self.overlay.hide(150)
        if message:
            notify(message)

    # ---- player events ---------------------------------------------------------------------------

    def on_item_starting(self):
        with self.lock:
            if self.session:
                self.session['phase'] = 'switching'
                self.session['since'] = time.time()

    def on_started(self):
        with self.lock:
            s = self.session
            if not s:
                return
            pos = self.playlist.getposition()
            if not 0 <= pos < len(s['queue']):
                log(f'playlist position {pos} is not a scene; leaving demo mode', xbmc.LOGWARNING)
                self._end_session(restore_all=True, stop=False)
                return
            s['index'] = pos
            s['phase'] = 'loading'
            s['since'] = time.time()
            scene = s['queue'][pos]
            try:
                t = self.player.getTime()
            except RuntimeError:
                t = -1
            if not (scene['start'] - OUTSIDE_S <= t <= scene['end']):
                self._seek(scene['start'])
            self._props(scene)
            current = f'{scene["media"]}:{scene["dbid"]}'
            s['played'].add(current)
            s['restored'].discard(current)            # playing again: Kodi will save it again
        self._restore_later(exclude=current)
        self.wake.set()

    def on_seek(self):
        with self.lock:
            s = self.session
            if not s or s['phase'] != 'playing' or time.time() - self.own_seek < OWN_SEEK_S:
                self.wake.set()
                return
            scene = s['queue'][s['index']]
            try:
                t = self.player.getTime()
            except RuntimeError:
                return
            outside = t < scene['start'] - OUTSIDE_S or t > scene['end'] + JUMPED_S
        if outside:
            log(f'seek to {t:.1f}s left the scene ({scene["start"]}-{scene["end"]})')
            self.leave(tr(32246))
        else:
            self.wake.set()
            threading.Timer(0.8, self.wake.set).start()     # look again once the seek has landed

    def on_stopped(self):
        with self.lock:
            if self.expect_stop:
                self.expect_stop = False
                return
            if self.session:
                log('playback stopped; demo over')
                self._end_session(restore_all=True, stop=False)
        self.overlay.hide(0)

    def on_ended(self):
        with self.lock:
            s = self.session
            if not s:
                return
            if s['index'] >= len(s['queue']) - 1 and s['phase'] != 'switching':
                # The file ran out at (or before) the last scene's end.
                nxt = SM.next_index(s['index'], len(s['queue']), s['loop'])
                if nxt is None:
                    self._end_session(restore_all=True, stop=False)
                    return
            # Otherwise Kodi moves on to the next playlist item by itself.

    def on_error(self):
        with self.lock:
            s = self.session
            if not s:
                return
            scene = s['queue'][s['index']]
            log(f'playback error in scene {scene["id"]} ({scene["file"]})', xbmc.LOGERROR)
        notify(tr(32242).format(scene['name']))
        self._advance()

    # ---- the scene clock -------------------------------------------------------------------------

    def _worker(self):
        while not self.monitor.abortRequested():
            delay = self._tick()
            self.wake.wait(delay)
            self.wake.clear()

    def _tick(self):
        """One look at the player; returns how long to sleep before the next."""
        with self.lock:
            s = self.session
            if not s or s['phase'] == 'switching':
                if s and time.time() - s['since'] > LOAD_TIMEOUT_S * 2:
                    log('no scene started in time; demo over', xbmc.LOGWARNING)
                    self._end_session(restore_all=True, stop=True)
                return 5.0 if not s else 0.5
            scene = s['queue'][s['index']]
            try:
                playing = self.player.isPlayingVideo()
                t = self.player.getTime() if playing else -1
            except RuntimeError:
                return 0.5
            if not playing:
                return 1.0
            if s['phase'] == 'loading':
                if scene['start'] - OUTSIDE_S <= t <= scene['end']:
                    s['phase'] = 'playing'
                    log(f'scene {s["index"] + 1}/{len(s["queue"])} "{scene["name"]}" started at {t:.1f}s')
                    threading.Thread(target=self._reveal, daemon=True).start()
                elif time.time() - s['since'] > LOAD_TIMEOUT_S:
                    log(f'scene "{scene["name"]}" did not start (at {t:.1f}s); skipping', xbmc.LOGWARNING)
                    threading.Thread(target=self._advance, daemon=True).start()
                    return 1.0
                else:
                    if time.time() - self.own_seek > OWN_SEEK_S:
                        self._seek(scene['start'])
                    return 0.25
            remaining = scene['end'] - t
            if t < scene['start'] - OUTSIDE_S - 1 or t > scene['end'] + JUMPED_S:
                # Far outside the scene: the user seeked away (the seek event may have come
                # before the new position was known).
                log(f'at {t:.1f}s, outside the scene ({scene["start"]}-{scene["end"]}): leaving demo mode')
                threading.Thread(target=self.leave, args=(tr(32246),), daemon=True).start()
                return 1.0
            if remaining <= END_SLACK_S:
                s['phase'] = 'switching'
                s['since'] = time.time()
                threading.Thread(target=self._scene_ended, daemon=True).start()
                return 0.5
            if xbmc.getCondVisibility('Player.Paused'):
                return 5.0                    # resumed: woken by the event
            if remaining > 1.0:
                return min(remaining - 0.6, 5.0)
            return max(remaining - END_SLACK_S, 0.02)

    def _seek(self, seconds):
        self.own_seek = time.time()
        try:
            self.player.seekTime(float(seconds))
        except RuntimeError:
            pass

    def _scene_ended(self):
        with self.lock:
            s = self.session
            if not s:
                return
            i = s['index']
            scene = s['queue'][i]
            looping = s['loop'] == 'scene' and scene['id'] == s['loop_scene']
            nxt = SM.next_index(i, len(s['queue']), s['loop'], looping)
            log(f'scene "{scene["name"]}" ended; next: {nxt}')
            if nxt == i and looping:
                s['phase'] = 'loading'
                s['since'] = time.time()
                self._seek(scene['start'])
                return
            if nxt is None:
                tr_, secs = s['transition'], s['secs']
        if nxt is None:
            if tr_ != 'cut' and secs > 0:
                self._pause()
                self.overlay.show(min(1000, secs * 500))
            with self.lock:
                self._end_session(restore_all=True, stop=True)
            self.overlay.hide(0)
            notify(tr(32243))
            return
        self._go(nxt, transition=True)

    def _advance(self):
        with self.lock:
            s = self.session
            if not s:
                return
            nxt = SM.next_index(s['index'], len(s['queue']), s['loop'])
            if nxt is None or nxt == s['index']:
                self._end_session(restore_all=True, stop=True)
                return
        self._go(nxt)

    def _pause(self):
        if not xbmc.getCondVisibility('Player.Paused'):
            self.player.pause()

    def _go(self, index, transition=False):
        with self.lock:
            s = self.session
            if not s:
                return
            kind, secs = (s['transition'], s['secs']) if transition else ('cut', 0)
            s['phase'] = 'switching'
            s['since'] = time.time()
            s['index'] = index
        if kind == 'black' and secs > 0:
            self._pause()
            self.overlay.show(200)
            time.sleep(secs)
        elif kind == 'fade' and secs > 0:
            self._pause()
            self.overlay.show(secs * 500)
            time.sleep(secs / 2.0)
        with self.lock:
            if not self.session:
                self.overlay.hide(0)
                return
            self.session['since'] = time.time()
        self.player.playselected(index)

    def _reveal(self):
        """The scene is playing: take the black overlay away (fading for a fade)."""
        with self.lock:
            s = self.session
            ms = s['secs'] * 500 if s and s['transition'] == 'fade' else 200
        self.overlay.hide(ms)

    # ---- session bookkeeping ---------------------------------------------------------------------

    def _props(self, scene):
        s = self.session
        HOME.setProperty('kscape.demo.active', '1')
        HOME.setProperty('kscape.demo.scene', scene['name'])
        HOME.setProperty('kscape.demo.title', scene.get('title', ''))
        HOME.setProperty('kscape.demo.progress', tr(32244).format(s['index'] + 1, len(s['queue'])))
        HOME.setProperty('kscape.demo.script', s['script'])

    def _restore_later(self, exclude=None):
        """Put back what Kodi saved for items no longer playing, once Kodi has saved it."""
        with self.lock:
            s = self.session
            if not s:
                return
            todo = {k: v for k, v in s['snapshot'].items()
                    if k in s['played'] and k != exclude and k not in s['restored']}
            s['restored'].update(todo)
        self._restore_soon(todo)

    @staticmethod
    def _restore_soon(todo, then=None):
        if not todo:
            if then:
                then()
            return

        def run():
            last = 0.0
            for at in RESTORE_AFTER_S:
                time.sleep(at - last)
                last = at
                restore(todo)
            if then:
                then()
        threading.Thread(target=run, daemon=True).start()

    def _end_session(self, restore_all=True, stop=False, keep=None):
        s, self.session = self.session, None
        for p in PROPS:
            HOME.clearProperty(f'kscape.demo.{p}')
        if not s:
            return
        if stop and self.player.isPlaying():
            self.expect_stop = True
            self.player.stop()
        if restore_all:
            todo = {k: v for k, v in s['snapshot'].items()
                    if k in s['played'] and k != keep and k not in s['restored']}

            def forget():
                try:
                    os.remove(SNAPSHOT)
                except OSError:
                    pass
            self._restore_soon(todo, then=forget)

    def shutdown(self):
        with self.lock:
            if self.session:
                self._end_session(restore_all=False, stop=False)   # restored on the next start


def run():
    engine = Engine()
    log('service started')
    while not engine.monitor.abortRequested():
        if engine.monitor.waitForAbort(30):
            break
    engine.shutdown()
