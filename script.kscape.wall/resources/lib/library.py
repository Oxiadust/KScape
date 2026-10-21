"""Kodi video and music library access over in-process JSON-RPC."""
import json
from dataclasses import replace

import xbmc

from .info import DETAILS_PROPERTIES
from .media import ALBUM_PROPERTIES, SHOW_PROPERTIES, Album, Show
from .model import JSONRPC_PROPERTIES, LIGHT_PROPERTIES, MAX_CAST, Movie

SORT = {'method': 'sorttitle', 'order': 'ascending', 'ignorearticle': True}


def rpc(method, params):
    req = {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}
    res = json.loads(xbmc.executeJSONRPC(json.dumps(req)))
    if 'error' in res:
        xbmc.log(f'kscape: {method} failed: {res["error"]}', xbmc.LOGERROR)
        return {}
    return res.get('result') or {}


def library_total():
    """Number of movies in the library (asks for one item and reads the total)."""
    result = rpc('VideoLibrary.GetMovies', {'limits': {'start': 0, 'end': 1}})
    return int((result.get('limits') or {}).get('total') or 0)


def fetch_movies():
    """All library movies in title order (leading articles ignored, as Kodi lists them), without
    cast. Use fetch_cast() for that."""
    result = rpc('VideoLibrary.GetMovies', {'properties': LIGHT_PROPERTIES, 'sort': SORT})
    return [Movie.from_jsonrpc(m) for m in result.get('movies', [])]


def fetch_cast():
    """{movieid: top-billed cast names} for every movie. The slowest library query by far."""
    result = rpc('VideoLibrary.GetMovies', {'properties': ['cast']})
    cast = {}
    for m in result.get('movies', []):
        people = sorted(m.get('cast') or [], key=lambda c: c.get('order', 0))
        cast[int(m['movieid'])] = tuple(c['name'] for c in people[:MAX_CAST] if c.get('name'))
    return cast


def fetch_movie(movieid):
    """One movie with every property, or None if it no longer exists."""
    details = rpc('VideoLibrary.GetMovieDetails', {'movieid': movieid,
                                                   'properties': JSONRPC_PROPERTIES})
    m = details.get('moviedetails')
    return Movie.from_jsonrpc(m) if m else None


def fetch_sets():
    """{setid: {'title', 'poster', 'fanart', 'plot'}} for Kodi's movie sets (Group by Collection)."""
    result = rpc('VideoLibrary.GetMovieSets', {'properties': ['title', 'art', 'plot']})
    sets = {}
    for s in result.get('sets', []):
        art = s.get('art') or {}
        sets[int(s['setid'])] = {'title': s.get('title') or s.get('label') or '',
                                 'poster': art.get('poster') or art.get('thumb') or '',
                                 'fanart': art.get('fanart') or '', 'plot': s.get('plot') or ''}
    return sets


VERSIONS_ROOT = 'videodb://movies/videoversions/'
VERSION_PROPERTIES = ['file', 'streamdetails', 'resume']


def fetch_versions():
    """{movieid: (Version, ...)} for every movie with two or more versions (Kodi 21 versions).

    JSON-RPC has no version API, so this reads Kodi's own library paths: the version types in use,
    then each type's movies. A first pass asks only for ids (cheap even for a large library); the
    second fetches files, stream details and resume points only for the types that hold a movie
    with several versions. Nothing is read from the files themselves."""
    from .versions import Version
    types = rpc('Files.GetDirectory', {'directory': VERSIONS_ROOT, 'media': 'video'}).get('files', [])
    count, types_of = {}, {}
    for t in types:
        listing = rpc('Files.GetDirectory', {'directory': t['file'], 'media': 'video'}).get('files', [])
        for it in listing:
            if it.get('type') == 'movie' and it.get('id'):
                mid = int(it['id'])
                count[mid] = count.get(mid, 0) + 1
                types_of.setdefault(mid, set()).add(t['file'])
    multi = {mid for mid, n in count.items() if n > 1}
    if not multi:
        return {}
    wanted = set().union(*(types_of[m] for m in multi))
    found = {}
    for t in types:
        if t['file'] not in wanted:
            continue
        listing = rpc('Files.GetDirectory', {'directory': t['file'], 'media': 'video',
                                             'properties': VERSION_PROPERTIES}).get('files', [])
        for it in listing:
            if it.get('type') == 'movie' and it.get('id') and int(it['id']) in multi:
                mid = int(it['id'])
                found.setdefault(mid, []).append(Version.from_item(mid, it, t.get('label') or '', t['file']))
    xbmc.log(f'kscape: {len(found)} movies with several versions ({len(types)} version types)', xbmc.LOGINFO)
    return {mid: tuple(vs) for mid, vs in found.items() if len(vs) > 1}


def fresh_resume(versions, title=''):
    """The versions with their resume points as Kodi has them now (the cached ones may predate
    the last viewing). Kodi keeps one per version (per file); GetMovieDetails reports only the
    default version's, so each version type's listing is asked for this movie alone (a
    smart-playlist filter on the title, checked against the movie id). A merged copy is its own
    library entry: GetMovieDetails."""
    import urllib.parse
    resume = {}
    xsp = json.dumps({'rules': {'and': [{'field': 'title', 'operator': 'is', 'value': [title]}]}, 'type': 'movies'})
    for vtype in {v.vtype for v in versions if v.vtype}:
        listing = rpc('Files.GetDirectory', {'directory': f'{vtype}?xsp={urllib.parse.quote(xsp)}', 'media': 'video',
                                             'properties': ['file', 'resume']}).get('files', [])
        for it in listing:
            resume[(int(it.get('id') or 0), it.get('file'))] = float((it.get('resume') or {}).get('position') or 0)
    out = []
    for v in versions:
        if v.vtype:
            pos = resume.get((v.movieid, v.file), v.resume)
        else:
            d = rpc('VideoLibrary.GetMovieDetails', {'movieid': v.movieid, 'properties': ['resume']})
            pos = float(((d.get('moviedetails') or {}).get('resume') or {}).get('position') or 0)
        out.append(v._replace(resume=pos))
    return tuple(out)


def mark_default(versions, default_file):
    """The versions with Kodi's default one (the file the movie lists) marked."""
    return tuple(v._replace(default=v.file == default_file) for v in versions)


def fetch_details(movieid):
    """Everything the info screen shows, as Kodi returns it, or None if the movie is gone."""
    details = rpc('VideoLibrary.GetMovieDetails', {'movieid': movieid,
                                                   'properties': DETAILS_PROPERTIES})
    return details.get('moviedetails')


def version_settings():
    """(preferred resolution, prefer 3D) from KScape's skin settings (Skin settings → Movie
    versions): the preference is one of versions.PREFERENCES, '4K' when unset."""
    from .versions import PREFERENCES
    pref = xbmc.getInfoLabel('Skin.String(KScapeVersionPreference)') or '4K'
    return (pref if pref in PREFERENCES else '4K'), xbmc.getCondVisibility('Skin.HasSetting(KScapePrefer3D)')


def play_version(version, resume=False):
    """Play one version by its file: Kodi recognises it as that movie and version, and keeps its
    resume point apart from the other versions'."""
    rpc('Player.Open', {'item': {'file': version.file}, 'options': {'resume': bool(resume)}})


def play(movie, resume=None):
    """Play through Kodi's player. By default resumes from the saved bookmark if there is one
    (asked of Kodi, since a view's copy of the movie may predate the last viewing). A movie with
    several versions plays the one the version settings pick (versions.choose) - for Resume, the
    one with a resume point."""
    if getattr(movie, 'versions', ()):
        from .versions import choose
        pref, prefer_3d = version_settings()
        movie = replace(movie, versions=fresh_resume(movie.versions, movie.title))
        if resume is None:
            v = choose(movie.versions, pref, prefer_3d, resume=True)
            resume = v.resume > 0
        else:
            v = choose(movie.versions, pref, prefer_3d, resume=bool(resume))
        play_version(v, resume=bool(resume) and v.resume > 0)
        return
    if resume is None:
        details = rpc('VideoLibrary.GetMovieDetails', {'movieid': movie.movieid,
                                                       'properties': ['resume']})
        resume = ((details.get('moviedetails') or {}).get('resume') or {}).get('position', 0) > 0
    rpc('Player.Open', {'item': {'movieid': movie.movieid}, 'options': {'resume': bool(resume)}})


TRAILER_WAIT_S = 30.0


def play_trailer(url, title='', poster=''):
    """Play a movie's trailer as Kodi's own info dialog does: through the player, with a list
    item (so the OSD names it), once the info screen has finished closing - opening playback while
    a dialog still plays its close animation can leave Kodi waiting on it. Trailers are often
    YouTube add-on links, which resolve over the network; if nothing plays within TRAILER_WAIT_S
    (and the add-on is not asking something), a notification says so instead of a silent wait."""
    import threading
    import xbmcaddon
    import xbmcgui
    from .menu import wait_for_dialogs
    wait_for_dialogs()
    li = xbmcgui.ListItem(title or url, offscreen=True)
    if title:
        li.getVideoInfoTag().setTitle(title)
    if poster:
        li.setArt({'thumb': poster, 'poster': poster})
    xbmc.Player().play(url, li)

    def watch():
        mon = xbmc.Monitor()
        waited = 0.0
        while waited < TRAILER_WAIT_S:
            if mon.waitForAbort(0.5):
                return
            waited += 0.5
            if xbmc.getCondVisibility('Player.HasVideo'):
                return
            if xbmc.getCondVisibility('Window.IsActive(yesnodialog) | Window.IsActive(okdialog) | '
                                      'Window.IsActive(selectdialog) | Window.IsActive(virtualkeyboard)'):
                waited = 0.0                          # the add-on is asking the user something
        addon = xbmcaddon.Addon('script.kscape.wall')
        xbmc.log(f'kscape: trailer did not start within {TRAILER_WAIT_S:.0f} s: {url}', xbmc.LOGWARNING)
        xbmcgui.Dialog().notification('KScape', addon.getLocalizedString(32365), xbmcgui.NOTIFICATION_WARNING, 6000)
    threading.Thread(target=watch, daemon=True).start()


# ---- music library -------------------------------------------------------------------------

ALBUM_SORT = {'method': 'artist', 'order': 'ascending', 'ignorearticle': True}
MUSIC_PLAYLIST = 0
SONG_PROPERTIES = ['title', 'track', 'disc', 'duration', 'artist', 'file', 'albumid']


def album_total():
    result = rpc('AudioLibrary.GetAlbums', {'limits': {'start': 0, 'end': 1}})
    return int((result.get('limits') or {}).get('total') or 0)


def fetch_albums():
    """All albums by artist (leading "The" ignored), then year and title (see Album.sorttitle)."""
    result = rpc('AudioLibrary.GetAlbums', {'properties': ALBUM_PROPERTIES, 'sort': ALBUM_SORT})
    return sorted((Album.from_jsonrpc(a) for a in result.get('albums', [])), key=lambda a: a.sorttitle)


def fetch_album(albumid):
    details = rpc('AudioLibrary.GetAlbumDetails', {'albumid': albumid, 'properties': ALBUM_PROPERTIES})
    a = details.get('albumdetails')
    return Album.from_jsonrpc(a) if a else None


def fetch_songs(albumid):
    """The album's tracks in disc and track order, as Kodi returns them."""
    result = rpc('AudioLibrary.GetSongs', {'filter': {'albumid': albumid}, 'properties': SONG_PROPERTIES,
                                           'sort': {'method': 'track', 'order': 'ascending'}})
    return sorted(result.get('songs', []), key=lambda s: (s.get('disc') or 0, s.get('track') or 0))


def play_album(albumid, position=0):
    """Queue the whole album in Kodi's music playlist and start at track `position`."""
    rpc('Playlist.Clear', {'playlistid': MUSIC_PLAYLIST})
    rpc('Playlist.Add', {'playlistid': MUSIC_PLAYLIST, 'item': {'albumid': albumid}})
    rpc('Player.Open', {'item': {'playlistid': MUSIC_PLAYLIST, 'position': position}})


# ---- TV library ----------------------------------------------------------------------------

SHOW_SORT = {'method': 'sorttitle', 'order': 'ascending', 'ignorearticle': True}
SEASON_PROPERTIES = ['season', 'episode', 'watchedepisodes', 'art', 'title']
EPISODE_PROPERTIES = ['title', 'season', 'episode', 'runtime', 'plot', 'art', 'playcount', 'resume',
                      'firstaired', 'file']


def show_total():
    result = rpc('VideoLibrary.GetTVShows', {'limits': {'start': 0, 'end': 1}})
    return int((result.get('limits') or {}).get('total') or 0)


def in_progress_shows():
    """Ids of the shows with an episode that has a resume point (Kodi's in-progress shows)."""
    result = rpc('VideoLibrary.GetInProgressTVShows', {})
    return {int(t['tvshowid']) for t in result.get('tvshows', [])}


def fetch_shows():
    result = rpc('VideoLibrary.GetTVShows', {'properties': SHOW_PROPERTIES, 'sort': SHOW_SORT})
    busy = in_progress_shows()
    return [Show.from_jsonrpc(dict(t, inprogress=int(t['tvshowid']) in busy)) for t in result.get('tvshows', [])]


def fetch_show(tvshowid):
    details = rpc('VideoLibrary.GetTVShowDetails', {'tvshowid': tvshowid, 'properties': SHOW_PROPERTIES})
    t = details.get('tvshowdetails')
    return Show.from_jsonrpc(dict(t, inprogress=tvshowid in in_progress_shows())) if t else None


STATUS = {  # method, result key, id key, properties: what built-in collections are worked out from
    'movies': ('VideoLibrary.GetMovies', 'movies', 'movieid', ['playcount', 'lastplayed', 'resume', 'dateadded']),
    'music': ('AudioLibrary.GetAlbums', 'albums', 'albumid', ['playcount', 'lastplayed', 'dateadded']),
    'tv': ('VideoLibrary.GetTVShows', 'tvshows', 'tvshowid', ['playcount', 'lastplayed', 'dateadded',
                                                            'watchedepisodes']),
}


def fetch_status(kind_name):
    """{id: record fields} of play state and dates for every item: one light query, so the
    built-in collections are current even when the rest comes from the disk cache."""
    method, key, idkey, props = STATUS[kind_name]
    out = {}
    busy = in_progress_shows() if kind_name == 'tv' else set()
    for x in rpc(method, {'properties': props}).get(key, []):
        i = int(x[idkey])
        f = {'playcount': int(x.get('playcount') or 0), 'lastplayed': x.get('lastplayed') or '',
             'dateadded': x.get('dateadded') or ''}
        if kind_name == 'movies':
            f['resume_position'] = float((x.get('resume') or {}).get('position') or 0)
        if kind_name == 'tv':
            f['watched'] = int(x.get('watchedepisodes') or 0)
            f['inprogress'] = i in busy
        out[i] = f
    return out


def parent_of(item_type, item_id):
    """The album of a song, or the show of an episode: what a wall shows when one of those
    changes (played, a resume point saved). None for anything else."""
    if item_type == 'song':
        d = rpc('AudioLibrary.GetSongDetails', {'songid': item_id, 'properties': ['albumid']})
        return (d.get('songdetails') or {}).get('albumid') or None
    if item_type == 'episode':
        d = rpc('VideoLibrary.GetEpisodeDetails', {'episodeid': item_id, 'properties': ['tvshowid']})
        return (d.get('episodedetails') or {}).get('tvshowid') or None
    return None


def fetch_seasons(tvshowid):
    result = rpc('VideoLibrary.GetSeasons', {'tvshowid': tvshowid, 'properties': SEASON_PROPERTIES,
                                             'sort': {'method': 'season', 'order': 'ascending'}})
    return result.get('seasons', [])


def fetch_episodes(tvshowid, season):
    result = rpc('VideoLibrary.GetEpisodes', {'tvshowid': tvshowid, 'season': season,
                                              'properties': EPISODE_PROPERTIES,
                                              'sort': {'method': 'episode', 'order': 'ascending'}})
    return result.get('episodes', [])


def play_episode(episodeid, resume=None):
    """Like play(): resumes from Kodi's bookmark unless told otherwise."""
    if resume is None:
        details = rpc('VideoLibrary.GetEpisodeDetails', {'episodeid': episodeid, 'properties': ['resume']})
        resume = ((details.get('episodedetails') or {}).get('resume') or {}).get('position', 0) > 0
    rpc('Player.Open', {'item': {'episodeid': episodeid}, 'options': {'resume': bool(resume)}})
