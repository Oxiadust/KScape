"""Estuary's information-screen actions, done through Kodi itself: Choose Art, Refresh, Play Extra,
mark watched, queue music.

Everything goes through Kodi's own JSON-RPC (VideoLibrary / AudioLibrary Set...Details and
Refresh...) and its standard dialogs, so the library, the Kodi skin views and every other add-on
see the same result. The wall and lists follow by themselves: Kodi announces the change
(OnUpdate) and KScape re-reads the item.
"""
import xbmc
import xbmcgui

from . import artchoice, extras, kodidb
from . import s as S
from .library import MUSIC_PLAYLIST, rpc

tr = None                                  # set by _tr() (the add-on's getLocalizedString)


def _tr(string_id):
    global tr
    if tr is None:
        import xbmcaddon
        tr = xbmcaddon.Addon('script.kscape.wall').getLocalizedString
    return tr(string_id)


# media type -> (Get method, Set method, id key, result key, art types Kodi offers, art type labels)
ART_TYPES = {
    'movie': ('poster', 'fanart', 'banner', 'landscape', 'clearlogo', 'clearart', 'discart', 'keyart'),
    'tvshow': ('poster', 'fanart', 'banner', 'landscape', 'clearlogo', 'clearart', 'keyart'),
    'season': ('poster', 'banner', 'landscape', 'fanart'),
    'episode': ('thumb',),
    'album': ('thumb', 'back', 'spine', 'discart'),
    'artist': ('thumb', 'fanart', 'banner', 'clearlogo', 'landscape'),
}
ART_LABELS = {'poster': S.A_POSTER, 'fanart': S.A_FANART, 'banner': S.A_BANNER, 'clearlogo': S.A_CLEARLOGO,
              'clearart': S.A_CLEARART, 'landscape': S.A_LANDSCAPE, 'discart': S.A_DISCART,
              'keyart': S.A_KEYART, 'thumb': S.A_THUMB}
BACK_LABELS = {'back': 'Back cover', 'spine': 'Spine'}
RPC = {
    'movie': ('VideoLibrary.GetMovieDetails', 'VideoLibrary.SetMovieDetails', 'movieid', 'moviedetails'),
    'tvshow': ('VideoLibrary.GetTVShowDetails', 'VideoLibrary.SetTVShowDetails', 'tvshowid', 'tvshowdetails'),
    'season': ('VideoLibrary.GetSeasonDetails', 'VideoLibrary.SetSeasonDetails', 'seasonid', 'seasondetails'),
    'episode': ('VideoLibrary.GetEpisodeDetails', 'VideoLibrary.SetEpisodeDetails', 'episodeid', 'episodedetails'),
    'album': ('AudioLibrary.GetAlbumDetails', 'AudioLibrary.SetAlbumDetails', 'albumid', 'albumdetails'),
    'artist': ('AudioLibrary.GetArtistDetails', 'AudioLibrary.SetArtistDetails', 'artistid', 'artistdetails'),
    'song': ('AudioLibrary.GetSongDetails', 'AudioLibrary.SetSongDetails', 'songid', 'songdetails'),
}
REFRESH = {'movie': ('VideoLibrary.RefreshMovie', 'movieid'),
           'tvshow': ('VideoLibrary.RefreshTVShow', 'tvshowid'),
           'episode': ('VideoLibrary.RefreshEpisode', 'episodeid')}
NOTIFY = {'movie': 'VideoLibrary.OnUpdate', 'tvshow': 'VideoLibrary.OnUpdate', 'episode': 'VideoLibrary.OnUpdate'}
REFRESH_WAIT_S = 90


def art_label(arttype):
    sid = ART_LABELS.get(arttype)
    return _tr(sid) if sid else BACK_LABELS.get(arttype) or arttype.title()


# ---- Choose Art -------------------------------------------------------------------------------

def current_art(media, dbid):
    get, _, idkey, key = RPC[media]
    return rpc(get, {idkey: dbid, 'properties': ['art']}).get(key, {}).get('art') or {}


def offered(media, dbid, arttype, season=None, showid=None):
    """[(url, preview)] the scraper offered for `arttype`, read from Kodi's database."""
    if media == 'movie':
        rows = kodidb.query('MyVideos', 'select c08, c20 from movie where idMovie=?', (dbid,))
    elif media == 'tvshow':
        rows = kodidb.query('MyVideos', 'select c06, c11 from tvshow where idShow=?', (dbid,))
    elif media == 'season':
        rows = kodidb.query('MyVideos', 'select c06, c11 from tvshow where idShow=?', (showid,))
    elif media == 'episode':
        rows = kodidb.query('MyVideos', 'select c06, "" from episode where idEpisode=?', (dbid,))
    elif media == 'album':
        rows = kodidb.query('MyMusic', 'select strImage, "" from album where idAlbum=?', (dbid,))
    elif media == 'artist':
        rows = kodidb.query('MyMusic', 'select strImage, strImage from artist where idArtist=?', (dbid,))
    else:
        rows = []
    if not rows:
        return []
    thumbs, fanart = rows[0]
    if media == 'episode' and arttype == 'thumb':             # an episode's choices are plain thumbs
        found = artchoice.parse_thumbs(thumbs)
        return [(u, p) for _, u, p in found]
    if media == 'album' and arttype == 'thumb':
        return [(u, p) for _, u, p in artchoice.parse_thumbs(thumbs)]
    if media == 'artist' and arttype == 'thumb':
        return [(u, p) for k, u, p in artchoice.parse_thumbs(thumbs)]
    return artchoice.candidates(arttype, thumbs, fanart, season=season if media == 'season' else None)


def choose_art(media, dbid, title='', season=None, showid=None):
    """Kodi's Choose Art: pick the art type, then one of the current image, the scraper's
    offers, a file you browse to, or none. Returns True when something changed."""
    types = ART_TYPES[media]
    current = current_art(media, dbid)
    arttype = types[0]
    if len(types) > 1:
        items = []
        for t in types:
            li = xbmcgui.ListItem(art_label(t))
            if current.get(t):
                li.setArt({'thumb': current[t]})
            items.append(li)
        i = xbmcgui.Dialog().select(f'{_tr(S.CHOOSE_ART)}  ·  {title}' if title else _tr(S.M_ART_TYPE), items,
                                    useDetails=True)
        if i < 0:
            return False
        arttype = types[i]
    return _pick_image(media, dbid, arttype, current, title, season, showid)


def _pick_image(media, dbid, arttype, current, title, season, showid):
    label = art_label(arttype)
    choices = []                                   # (kind, url): kind is keep, set, browse or remove
    items = []
    now = current.get(arttype)
    if now:
        li = xbmcgui.ListItem(_tr(S.M_CURRENT))
        li.setArt({'thumb': now})
        items.append(li)
        choices.append(('keep', now))
    for n, (url, preview) in enumerate(offered(media, dbid, arttype, season, showid), start=1):
        if url == now:
            continue
        li = xbmcgui.ListItem(f'{label} {n}', url.split('://', 1)[-1].split('/', 1)[0])
        li.setArt({'thumb': preview or url})
        items.append(li)
        choices.append(('set', url))
    items.append(xbmcgui.ListItem(_tr(S.BROWSE_ART)))
    choices.append(('browse', ''))
    if now:
        items.append(xbmcgui.ListItem(_tr(S.REMOVE_ART)))
        choices.append(('remove', ''))
    i = xbmcgui.Dialog().select(_tr(S.M_ART_PICK).format(label.lower()), items, useDetails=True)
    if i < 0:
        return False
    kind, url = choices[i]
    if kind == 'keep':
        return False
    if kind == 'browse':
        url = xbmcgui.Dialog().browse(2, _tr(S.BROWSE_ART), 'files', '.jpg|.jpeg|.png|.webp|.tbn', False, False, '')
        if not url:
            return False
    return set_art(media, dbid, arttype, url if kind != 'remove' else None)


def set_art(media, dbid, arttype, url):
    """Store `url` as the art (None removes it) through Kodi's JSON-RPC."""
    _, setter, idkey, _ = RPC[media]
    result = rpc(setter, {idkey: dbid, 'art': {arttype: url}})
    if result == 'OK':
        xbmcgui.Dialog().notification('KScape', _tr(S.M_ART_UPDATED if url else S.M_REMOVED),
                                      xbmcgui.NOTIFICATION_INFO, 2500, False)
        return True
    return False


# ---- Refresh ----------------------------------------------------------------------------------

class _Waiter(xbmc.Monitor):
    def __init__(self, method):
        super().__init__()
        self.method = method
        self.seen = False

    def onNotification(self, sender, method, data):
        if method == self.method:
            self.seen = True


def refresh(media, dbid, title=''):
    """Kodi's Refresh: ask, then have the scraper reload the item's information (Kodi keeps its
    own NFO-first behaviour). Returns True once Kodi reports the item updated."""
    if media not in REFRESH:
        xbmcgui.Dialog().ok(_tr(S.REFRESH), _tr(S.M_REFRESH_MUSIC))
        return False
    if not xbmcgui.Dialog().yesno(_tr(S.REFRESH), _tr(S.M_REFRESH_ASK).format(title), yeslabel=_tr(S.REFRESH)):
        return False
    method, idkey = REFRESH[media]
    waiter = _Waiter(NOTIFY[media])
    if rpc(method, {idkey: dbid, 'ignorenfo': False}) != 'OK':
        return False
    xbmcgui.Dialog().notification('KScape', _tr(S.M_REFRESHING), xbmcgui.NOTIFICATION_INFO, 2500, False)
    waited = 0.0
    while not waiter.seen and waited < REFRESH_WAIT_S:
        if waiter.waitForAbort(0.2):
            return False
        waited += 0.2
    done = waiter.seen
    xbmcgui.Dialog().notification('KScape', _tr(S.M_REFRESHED if done else S.M_REFRESH_FAILED),
                                  xbmcgui.NOTIFICATION_INFO if done else xbmcgui.NOTIFICATION_WARNING, 3000, False)
    return done


# ---- Play Extra -------------------------------------------------------------------------------

def _listing(directory):
    return rpc('Files.GetDirectory', {'directory': directory, 'media': 'files'}).get('files', [])


def find_extras(details):
    """The movie's extras: [{'category', 'label', 'file'}], trailer first. See extras.py for the
    naming followed; Kodi 21 'Extras' assets of the movie are included."""
    out = []
    if details.get('trailer'):
        out.append({'category': S.X_TRAILER, 'label': _tr(S.X_TRAILER), 'file': details['trailer']})
    path = details.get('file') or ''
    if path and not path.startswith(('stack://', 'bluray://', 'plugin://', 'videodb://')):
        folder = path.rsplit('/', 1)[0] + '/' if '/' in path else ''
        if folder:
            entries = []
            for e in _listing(folder):
                is_dir = e.get('filetype') == 'directory'
                children = []
                if is_dir and extras.folder_category(e.get('label')):
                    children = [(c.get('label') or '', c.get('file') or '') for c in _listing(e['file'])
                                if c.get('filetype') != 'directory']
                entries.append((e.get('label') or '', e.get('file') or '', is_dir, children))
            out += extras.classify(entries, path)
    for name, file in kodidb.query(
            'MyVideos', 'select t.name, p.strPath || f.strFilename from videoversion v '
                        'join files f on f.idFile = v.idFile join path p on p.idPath = f.idPath '
                        'left join videoversiontype t on t.id = v.idType '
                        'where v.idMedia = ? and v.media_type = "movie" and v.itemType = 1', (details.get('movieid'),)):
        out.append({'category': S.X_OTHER, 'label': name or _tr(S.X_OTHER), 'file': file})
    seen, unique = set(), []
    for e in out:
        if e['file'] not in seen:
            seen.add(e['file'])
            unique.append(e)
    return unique


MANAGE = 'manage'


def pick_extra(items):
    """Kodi's selection dialog over the extras, then Add or Manage Extras…. Returns the extra
    chosen, MANAGE, or None. With no extras the dialog says so and offers just the last entry."""
    labels = [f'{_tr(e["category"])}  ·  {e["label"]}' if e['label'] != _tr(e['category']) else _tr(e['category'])
              for e in items]
    labels.append(f'[COLOR kscape_text_dim]{_tr(S.M_MANAGE_EXTRAS)}[/COLOR]' if items else _tr(S.M_MANAGE_EXTRAS))
    heading = _tr(S.PLAY_EXTRA) if items else f'{_tr(S.PLAY_EXTRA)}  ·  {_tr(S.M_NO_EXTRAS)}'
    i = xbmcgui.Dialog().select(heading, labels)
    if i < 0:
        return None
    return items[i] if i < len(items) else MANAGE


def manage_extras(details):
    """Kodi's own extras manager for a movie (add an extra from a file, rename, remove, choose its
    art): Kodi 21 opens it from the movie's information dialog (Extras button), so that dialog is
    opened - invisibly, see skin.kscape's DialogVideoInfo.xml - and told to press Extras; it is
    closed again when the manager is. Returns when everything is closed."""
    import threading
    movieid = details.get('movieid')
    if not movieid:
        return
    li = xbmcgui.ListItem(details.get('title') or '', path=details.get('file') or '')
    tag = li.getVideoInfoTag()
    tag.setDbId(int(movieid))
    tag.setMediaType('movie')
    tag.setTitle(details.get('title') or '')
    if details.get('art'):
        li.setArt(details['art'])
    home = xbmcgui.Window(10000)
    home.setProperty('kscape.infoaction', 'extras')
    opened = []

    def watch():
        mon = xbmc.Monitor()
        waited = 0.0
        while waited < 8.0 and not xbmc.getCondVisibility('Window.IsActive(managevideoextras)'):
            if mon.waitForAbort(0.1):
                return
            waited += 0.1
        opened.append(xbmc.getCondVisibility('Window.IsActive(managevideoextras)'))
        while xbmc.getCondVisibility('Window.IsActive(managevideoextras)'):
            if mon.waitForAbort(0.2):
                return
        xbmc.executebuiltin('Dialog.Close(movieinformation,true)')

    threading.Thread(target=watch, daemon=True).start()
    try:
        xbmcgui.Dialog().info(li)
    finally:
        home.clearProperty('kscape.infoaction')
    if not opened or not opened[0]:
        xbmcgui.Dialog().notification('KScape', _tr(S.M_MANAGE_FAILED), xbmcgui.NOTIFICATION_WARNING, 4000, False)


def play_file(file, title=''):
    rpc('Player.Open', {'item': {'file': file}})


# ---- watched state and music queue ------------------------------------------------------------

def set_watched(media, dbid, watched):
    """Mark a movie, show or episode watched or unwatched through Kodi (the resume point goes too)."""
    _, setter, idkey, _ = RPC[media]
    params = {idkey: dbid, 'playcount': 1 if watched else 0}
    if media in ('movie', 'episode'):
        params['resume'] = {'position': 0, 'total': 0}
    rpc(setter, params)


def rate(media, dbid, current=0, title=''):
    """Your rating, 1 to 10 (or none), as Kodi's own rating dialog offers it. Returns the new
    rating (0: cleared) or None when cancelled."""
    labels = [_tr(S.M_RATE_CLEAR)] + [f'{n}  {"★" * n}' for n in range(1, 11)]
    i = xbmcgui.Dialog().select(f'{_tr(S.M_RATE_HEAD)}  ·  {title}' if title else _tr(S.M_RATE_HEAD), labels,
                                preselect=int(current or 0))
    if i < 0:
        return None
    _, setter, idkey, _ = RPC[media]
    rpc(setter, {idkey: dbid, 'userrating': i})
    return i


def queue_songs(songids, play_next=False):
    """Add songs to Kodi's music queue; Play Next puts them right after the playing song."""
    position = None
    if play_next:
        players = rpc('Player.GetActivePlayers', {})
        audio = [p for p in players if p.get('type') == 'audio'] if isinstance(players, list) else []
        if audio:
            props = rpc('Player.GetProperties', {'playerid': audio[0]['playerid'], 'properties': ['position']})
            position = int(props.get('position', -1)) + 1
    for n, sid in enumerate(songids):
        if position is not None:
            rpc('Playlist.Insert', {'playlistid': MUSIC_PLAYLIST, 'position': position + n, 'item': {'songid': sid}})
        else:
            rpc('Playlist.Add', {'playlistid': MUSIC_PLAYLIST, 'item': {'songid': sid}})
