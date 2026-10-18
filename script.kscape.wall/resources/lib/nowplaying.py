"""Now Playing: what Kodi's music player is playing, with its queue (WindowXML).

Cover, title, artist, album, progress and play state come straight from Kodi's player info
labels in script-kscape-nowplaying.xml, and the Previous / Play-Pause / Stop / Next buttons run
Kodi's own PlayerControl actions, so nothing here plays audio itself. Python only keeps the
queue list in step with Kodi's music playlist (Select on a track jumps to it) and offers the
C menu: Add to / Remove from Favourites for the playing album, and Search music.
"""
import threading

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from . import menu, modal
from .favourites import Favourites
from .library import MUSIC_PLAYLIST, fetch_album, fetch_albums, rpc
from .search import search

ADDON = xbmcaddon.Addon('script.kscape.wall')
BACK = (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU)
CONTEXT = (xbmcgui.ACTION_CONTEXT_MENU,)
QUEUE = 700
PLAY_PAUSE = 602
POLL_S = 0.5
FAVOURITES_FILE = xbmcvfs.translatePath('special://profile/favourites.xml')


def _player():
    """Kodi's audio player id, or None when no music is playing."""
    for p in rpc('Player.GetActivePlayers', {}) or []:
        if p.get('type') == 'audio':
            return p['playerid']
    return None


class NowPlayingWindow(xbmcgui.WindowXML):
    ready = False

    def onInit(self):
        if self.ready:
            return
        self.closing = False
        self.queue = self.getControl(QUEUE)
        self.queue_sig = None                # (playlist size, first and last song ids)
        self.position = None
        self.favs = None
        self._refresh()
        self.setFocusId(PLAY_PAUSE)
        self.ready = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        mon = xbmc.Monitor()
        while not self.closing and not mon.waitForAbort(POLL_S):
            self._refresh()

    def _refresh(self):
        items = rpc('Playlist.GetItems', {'playlistid': MUSIC_PLAYLIST,
                                          'properties': ['title', 'artist', 'duration', 'thumbnail']})
        items = items.get('items') or []
        sig = (len(items), items[0].get('id') if items else None, items[-1].get('id') if items else None)
        if sig != self.queue_sig:
            self.queue_sig = sig
            self.queue.reset()
            lis = []
            for it in items:
                li = xbmcgui.ListItem(it.get('title') or it.get('label') or '',
                                      ' / '.join(it.get('artist') or ()))
                li.setArt({'thumb': it.get('thumbnail') or ''})
                d = int(it.get('duration') or 0)
                li.setProperty('duration', f'{d // 60}:{d % 60:02d}' if d else '')
                lis.append(li)
            self.queue.addItems(lis)
            self.position = None
        player = _player()
        pos = None
        if player is not None:
            pos = (rpc('Player.GetProperties', {'playerid': player, 'properties': ['position']}) or {}).get('position')
        if pos != self.position:
            for i in range(self.queue.size()):
                self.queue.getListItem(i).setProperty('playing', '1' if i == pos else '')
            if pos is not None and pos >= 0 and self.getFocusId() != QUEUE:
                self.queue.selectItem(pos)
            self.position = pos

    def onClick(self, control_id):
        if control_id == PLAY_PAUSE and _player() is None and self.queue.size():
            # Stopped: Kodi's PlayerControl(Play) does nothing, so start the queue again.
            rpc('Player.Open', {'item': {'playlistid': MUSIC_PLAYLIST, 'position': max(0, self.position or 0)}})
        elif control_id == QUEUE:
            player = _player()
            i = self.queue.getSelectedPosition()
            if player is not None and i >= 0:
                rpc('Player.GoTo', {'playerid': player, 'to': i})
            elif i >= 0:
                rpc('Player.Open', {'item': {'playlistid': MUSIC_PLAYLIST, 'position': i}})

    def abandon(self):
        self.closing = True
        self.close()

    def onAction(self, action):
        aid = action.getId()
        if aid in BACK:
            self.closing = True
            self.close()
        elif aid in CONTEXT:
            self._menu()

    def _playing_album(self):
        player = _player()
        if player is None:
            return None
        item = (rpc('Player.GetItem', {'playerid': player, 'properties': ['albumid']}) or {}).get('item') or {}
        return fetch_album(item['albumid']) if item.get('albumid') else None

    def _menu(self):
        from .kinds import KINDS
        if self.favs is None:
            self.favs = Favourites(rpc, FAVOURITES_FILE)
        else:
            self.favs.poll()
        album = self._playing_album()
        choice = menu.show(album, self.favs, [('close', ADDON.getLocalizedString(32066))])
        if choice == 'favourite':
            self.favs.toggle(album)
        elif choice == 'search':
            kind = KINDS['music']
            query = menu.ask_search(kind)
            if query:
                from .listwindow import show_list
                library = fetch_albums()
                from .collectionui import store
                show_list(kind, search(library, query), None, self.favs, query=query, library=library,
                          store=store(kind))
        elif choice == 'close':
            self.closing = True
            self.close()


HOME = xbmcgui.Window(10000)
PROP_OPEN = 'kscape.nowplaying.open'


def show_now_playing():
    """Open Now Playing, unless it is already open further down (e.g. music started from a
    search begun on Now Playing): closing what is on top of it then brings it back."""
    if HOME.getProperty(PROP_OPEN):
        return
    HOME.setProperty(PROP_OPEN, '1')
    menu.wait_for_dialogs()
    try:
        window = NowPlayingWindow('script-kscape-nowplaying.xml', ADDON.getAddonInfo('path'), 'Default', '1080i')
        modal.run(window)
        window.closing = True
        del window
    finally:
        HOME.clearProperty(PROP_OPEN)
