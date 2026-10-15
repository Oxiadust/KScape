"""Kodi video library access over in-process JSON-RPC."""
import json

import xbmc

from .model import JSONRPC_PROPERTIES, Movie


def rpc(method, params):
    req = {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}
    res = json.loads(xbmc.executeJSONRPC(json.dumps(req)))
    if 'error' in res:
        xbmc.log(f'kscape: {method} failed: {res["error"]}', xbmc.LOGERROR)
        return {}
    return res.get('result') or {}


def fetch_movies():
    """All library movies in title order (leading articles ignored, as Kodi lists them)."""
    result = rpc('VideoLibrary.GetMovies', {
        'properties': JSONRPC_PROPERTIES,
        'sort': {'method': 'sorttitle', 'order': 'ascending', 'ignorearticle': True},
    })
    return [Movie.from_jsonrpc(m) for m in result.get('movies', [])]


def play(movie):
    """Play through Kodi's player, resuming from the saved bookmark when there is one."""
    rpc('Player.Open', {'item': {'movieid': movie.movieid},
                         'options': {'resume': movie.resume_position > 0}})
