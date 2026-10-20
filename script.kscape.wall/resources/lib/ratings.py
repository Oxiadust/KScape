"""Rotten Tomatoes scores for movies whose library entry has none: an optional OMDb lookup.

Kodi's TMDB scraper stores TMDB (and optionally IMDb / Trakt) ratings, but no Tomatometer; one
only comes with NFO files or scrapers that write it. When the user enters their own OMDb API key
in the add-on settings, KScape asks OMDb (www.omdbapi.com, by the movie's IMDb id) for the
Tomatometer of the movie being looked at - one movie at a time, never the whole library - and
keeps the answer in the add-on's profile folder (ratings.json) so it is asked once a month at
most. Without a key nothing is ever sent. Kodi's library is never written to.
"""
import json
import os
import threading
import time
import urllib.parse
import urllib.request

import xbmc
import xbmcaddon
import xbmcvfs

ADDON = xbmcaddon.Addon('script.kscape.wall')
PATH = xbmcvfs.translatePath('special://profile/addon_data/script.kscape.wall/ratings.json')
FRESH_S = 30 * 24 * 3600          # a score is asked again after a month
MISSING_S = 7 * 24 * 3600         # "OMDb has none" is believed for a week
TIMEOUT_S = 6

_lock = threading.Lock()
_cache = None
_busy = set()


def _key():
    try:
        return (ADDON.getSettingString('omdb_key') or '').strip()
    except Exception:
        return ''


def _load():
    global _cache
    if _cache is None:
        try:
            with open(PATH) as f:
                _cache = json.load(f)
        except (OSError, ValueError):
            _cache = {}
    return _cache


def _save():
    try:
        os.makedirs(os.path.dirname(PATH), exist_ok=True)
        tmp = PATH + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(_cache, f)
        os.replace(tmp, PATH)
    except OSError:
        pass


def parse_omdb(data):
    """Tomatometer percent from an OMDb answer, 0 when it has none."""
    for r in (data or {}).get('Ratings') or []:
        if r.get('Source') == 'Rotten Tomatoes':
            value = (r.get('Value') or '').rstrip('%')
            if value.isdigit():
                return int(value)
    return 0


def cached(imdb):
    """(percent or 0, still fresh) from the disk cache."""
    with _lock:
        entry = _load().get(imdb)
    if not entry:
        return 0, False
    age = time.time() - entry.get('t', 0)
    return entry.get('rt', 0), age < (FRESH_S if entry.get('rt') else MISSING_S)


def enabled():
    return bool(_key())


def lookup(movie, on_found):
    """The movie's Tomatometer: its library rating when it has one; else the cached OMDb one.
    Asks OMDb in the background when a key is set and nothing fresh is cached, then calls
    on_found(percent) if it found a score. Returns what is known now (0: nothing)."""
    if movie.rt:
        return movie.rt
    imdb = getattr(movie, 'imdb', '')
    if not imdb:
        return 0
    value, fresh = cached(imdb)
    key = _key()
    if fresh or not key:
        return value
    with _lock:
        if imdb in _busy:
            return value
        _busy.add(imdb)

    def fetch():
        found = 0
        try:
            url = 'https://www.omdbapi.com/?' + urllib.parse.urlencode({'i': imdb, 'apikey': key})
            with urllib.request.urlopen(url, timeout=TIMEOUT_S) as res:
                data = json.loads(res.read().decode('utf-8'))
            if data.get('Response') == 'False' and 'key' in (data.get('Error') or '').lower():
                xbmc.log(f'kscape: OMDb refused the API key: {data.get("Error")}', xbmc.LOGWARNING)
                return
            found = parse_omdb(data)
            with _lock:
                _load()[imdb] = {'rt': found, 't': time.time()}
                _save()
        except Exception as e:                       # offline, timeout, bad answer: try later
            xbmc.log(f'kscape: OMDb lookup for {imdb} failed: {e}', xbmc.LOGINFO)
        finally:
            with _lock:
                _busy.discard(imdb)
        if found:
            on_found(found)

    threading.Thread(target=fetch, daemon=True).start()
    return value
