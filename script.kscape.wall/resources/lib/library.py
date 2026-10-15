"""Kodi video library access over in-process JSON-RPC."""
import json

import xbmc

from .info import DETAILS_PROPERTIES
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
