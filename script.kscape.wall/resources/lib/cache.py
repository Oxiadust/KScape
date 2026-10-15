"""Disk cache of the movie list, so opening the wall does not re-query a large library.

Listing 5,000 movies with every property takes ~40 s in Kodi, so the wall shows the cached list
straight away and only re-queries when the library changes (scan, clean, or an edit Kodi
announces while the wall is open), when the movie count differs, or when the cache is older
than MAX_AGE_S. A broken or missing cache is simply ignored.
"""
import json
import os
import time

import xbmcvfs

PATH = xbmcvfs.translatePath('special://profile/addon_data/script.kscape.wall/movies-cache.json')
VERSION = 2
MAX_AGE_S = 24 * 3600


def load(expected_total):
    """{'movies': [dict], 'complete': bool, 'stale': bool} or None if unusable.

    `complete` is False when cast had not been fetched yet; `stale` when the cache is older than
    MAX_AGE_S and should be refreshed in the background.
    """
    try:
        with open(PATH) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if data.get('version') != VERSION or data.get('total') != expected_total:
        return None
    return {
        'movies': data.get('movies') or [],
        'complete': bool(data.get('complete')),
        'stale': time.time() - data.get('written', 0) > MAX_AGE_S,
    }


def save(total, movies, complete):
    data = {'version': VERSION, 'total': total, 'complete': complete, 'written': time.time(),
            'movies': movies}
    try:
        os.makedirs(os.path.dirname(PATH), exist_ok=True)
        tmp = PATH + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(data, f)
        os.replace(tmp, PATH)
    except OSError:
        pass                          # the cache is an optimisation; a failed write costs nothing


def discard():
    try:
        os.remove(PATH)
    except OSError:
        pass
