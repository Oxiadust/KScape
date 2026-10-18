"""Kodi video and music library access over in-process JSON-RPC."""
import json

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


def fetch_details(movieid):
    """Everything the info screen shows, as Kodi returns it, or None if the movie is gone."""
    details = rpc('VideoLibrary.GetMovieDetails', {'movieid': movieid,
                                                   'properties': DETAILS_PROPERTIES})
    return details.get('moviedetails')


def play(movie, resume=None):
    """Play through Kodi's player. By default resumes from the saved bookmark if there is one
    (asked of Kodi, since a view's copy of the movie may predate the last viewing)."""
    if resume is None:
        details = rpc('VideoLibrary.GetMovieDetails', {'movieid': movie.movieid,
                                                       'properties': ['resume']})
        resume = ((details.get('moviedetails') or {}).get('resume') or {}).get('position', 0) > 0
    rpc('Player.Open', {'item': {'movieid': movie.movieid}, 'options': {'resume': bool(resume)}})


def play_trailer(url):
    xbmc.executebuiltin(f'PlayMedia("{url}")')


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


def fetch_shows():
    result = rpc('VideoLibrary.GetTVShows', {'properties': SHOW_PROPERTIES, 'sort': SHOW_SORT})
    return [Show.from_jsonrpc(t) for t in result.get('tvshows', [])]


def fetch_show(tvshowid):
    details = rpc('VideoLibrary.GetTVShowDetails', {'tvshowid': tvshowid, 'properties': SHOW_PROPERTIES})
    t = details.get('tvshowdetails')
    return Show.from_jsonrpc(t) if t else None


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
