"""Disk cache of a library list, so opening the wall does not re-query a large library.

Listing 5,000 movies with every property takes ~40 s in Kodi, so the wall shows the cached list
straight away and only re-queries when the library changes (scan, clean, or an edit Kodi
announces while the wall is open), when the movie count differs, or when the cache is older
than MAX_AGE_S. A broken or missing cache is simply ignored.
"""
import json
import os
import time

import xbmcvfs

FOLDER = xbmcvfs.translatePath('special://profile/addon_data/script.kscape.wall/')


def _path(name):
    """One cache per media kind: movies-cache.json, music-cache.json, tv-cache.json."""
    return os.path.join(FOLDER, f'{name}-cache.json')


VERSION = 6                       # 6: movie country, stream facts and ratings (Explore, badges)
MAX_AGE_S = 24 * 3600


def load(expected_total, name='movies'):
    """{'movies': [dict], 'complete': bool, 'stale': bool} or None if unusable.

    `complete` is False when cast had not been fetched yet; `stale` when the cache is older than
    MAX_AGE_S and should be refreshed in the background.
    """
    try:
        with open(_path(name)) as f:
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


def save(total, movies, complete, name='movies'):
    data = {'version': VERSION, 'total': total, 'complete': complete, 'written': time.time(),
            'movies': movies}
    try:
        os.makedirs(FOLDER, exist_ok=True)
        tmp = _path(name) + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(data, f)
        os.replace(tmp, _path(name))
    except OSError:
        pass                          # the cache is an optimisation; a failed write costs nothing


def discard(name='movies'):
    try:
        os.remove(_path(name))
    except OSError:
        pass
