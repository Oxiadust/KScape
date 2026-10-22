"""Extended metadata Kodi's library does not hold: budget, revenue, original language and
production companies of a movie, a person's biography, birth and filmography, a movie's awards.

None of it is built into Kodi (Estuary gets it from the script.embuary.info add-on), so KScape
asks the providers behind Kodi's own scrapers - TMDB (themoviedb.org) and OMDb (omdbapi.com) -
using the user's own free API keys from the add-on settings. One title or person at a time, only
for the screen being looked at, answers kept in the add-on's profile folder (metadata.json) for a
month. Without a key nothing is ever sent, and the screens simply leave those fields out. Kodi's
library is never written to.
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
PATH = xbmcvfs.translatePath('special://profile/addon_data/script.kscape.wall/metadata.json')
FRESH_S = 30 * 24 * 3600
MISSING_S = 24 * 3600              # "provider has nothing" is believed for a day
TIMEOUT_S = 8
TMDB = 'https://api.themoviedb.org/3'
IMAGE = 'https://image.tmdb.org/t/p/w500'

_lock = threading.Lock()
_cache = None
_busy = set()


def key(setting):
    try:
        return (ADDON.getSettingString(setting) or '').strip()
    except Exception:
        return ''


def language_name(code):
    """'French' for 'fre' / 'fr' (Kodi's own language table); the code itself if unknown."""
    try:
        return xbmc.convertLanguage(code, xbmc.ENGLISH_NAME) or code
    except Exception:
        return code


def tmdb_key():
    return key('tmdb_key')


def omdb_key():
    return key('omdb_key')


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


def cached(name):
    """(answer or None, still fresh) for a cache entry."""
    with _lock:
        entry = _load().get(name)
    if not entry:
        return None, False
    age = time.time() - entry.get('t', 0)
    data = entry.get('d')
    return data, age < (FRESH_S if data else MISSING_S)


def _store(name, data):
    with _lock:
        _load()[name] = {'t': time.time(), 'd': data}
        _save()


def _get(url):
    req = urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'KScape'})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return json.loads(r.read().decode('utf-8'))


def tmdb_get(path, **params):
    params['api_key'] = tmdb_key()
    return _get(f'{TMDB}{path}?{urllib.parse.urlencode(params)}')


def request(name, fetch, done):
    """Answer for cache entry `name`: what is cached goes to done(data) at once (from the calling
    thread); when it is stale or missing and a fetch is possible, `fetch()` runs on a worker
    thread and its answer goes to done(data) again. done is never called with None."""
    data, fresh = cached(name)
    if data:
        done(data)
    if fresh:
        return
    with _lock:
        if name in _busy:
            return
        _busy.add(name)

    def work():
        try:
            fresh_data = fetch()
        except Exception as e:                       # offline, bad key, rate limit...
            xbmc.log(f'kscape: metadata {name} failed: {e}', xbmc.LOGINFO)
            fresh_data = None
        finally:
            with _lock:
                _busy.discard(name)
        if fresh_data is not None:
            _store(name, fresh_data)
            if fresh_data and fresh_data != data:
                done(fresh_data)

    threading.Thread(target=work, daemon=True).start()


# ---- pure shaping of provider answers ---------------------------------------------------------

def money(amount):
    """'$150,000,000'; '' when the provider has none (TMDB uses 0 for unknown)."""
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return ''
    return f'${amount:,}' if amount > 0 else ''


def shape_movie(tmdb, omdb=None):
    """The fields the info screen shows, from TMDB's /movie answer (and OMDb's, if asked)."""
    tmdb = tmdb or {}
    omdb = omdb or {}
    awards = (omdb.get('Awards') or '').strip()
    box = (omdb.get('BoxOffice') or '').strip()
    out = {
        'original_title': tmdb.get('original_title') or '',
        'original_language': tmdb.get('original_language') or '',
        'budget': money(tmdb.get('budget')),
        'revenue': money(tmdb.get('revenue')) or ('' if box in ('', 'N/A') else box),
        'companies': [c['name'] for c in tmdb.get('production_companies') or [] if c.get('name')],
        'countries': [c['name'] for c in tmdb.get('production_countries') or [] if c.get('name')],
        'languages': [c.get('english_name') or c.get('name') for c in tmdb.get('spoken_languages') or []
                      if c.get('english_name') or c.get('name')],
        'tagline': tmdb.get('tagline') or '',
        'released': tmdb.get('release_date') or '',
        'awards': '' if awards in ('', 'N/A') else awards,
    }
    return {k: v for k, v in out.items() if v}


def shape_person(data):
    """Biography, birth and filmography from TMDB's /person answer (credits appended)."""
    data = data or {}
    credits = (data.get('combined_credits') or {})
    films = []
    seen = set()
    for c in sorted(credits.get('cast') or [], key=lambda c: -(c.get('popularity') or 0)):
        title = c.get('title') or c.get('name')
        date = c.get('release_date') or c.get('first_air_date') or ''
        if not title or (title, date[:4]) in seen:
            continue
        seen.add((title, date[:4]))
        films.append({'title': title, 'year': date[:4], 'role': c.get('character') or '',
                      'type': c.get('media_type') or ''})
    crew = []
    for c in sorted(credits.get('crew') or [], key=lambda c: -(c.get('popularity') or 0)):
        if c.get('job') not in ('Director', 'Writer', 'Screenplay', 'Producer'):
            continue
        title = c.get('title') or c.get('name')
        date = c.get('release_date') or c.get('first_air_date') or ''
        if title and (title, date[:4]) not in seen:
            seen.add((title, date[:4]))
            crew.append({'title': title, 'year': date[:4], 'role': c.get('job'), 'type': c.get('media_type') or ''})
    profile = data.get('profile_path') or ''
    out = {
        'name': data.get('name') or '',
        'biography': (data.get('biography') or '').strip(),
        'birthday': data.get('birthday') or '',
        'deathday': data.get('deathday') or '',
        'place': data.get('place_of_birth') or '',
        'department': data.get('known_for_department') or '',
        'image': f'{IMAGE}{profile}' if profile else '',
        'also_known_as': [a for a in data.get('also_known_as') or [] if a][:4],
        'filmography': (films + crew)[:60],
    }
    return {k: v for k, v in out.items() if v}


def pick_person(results, name, department=''):
    """The search hit for `name`: an exact (case-insensitive) name match, preferring the
    department the person is credited in here; else the most popular hit."""
    hits = [r for r in results or [] if r.get('id')]
    exact = [r for r in hits if (r.get('name') or '').casefold() == (name or '').casefold()]
    pool = exact or hits
    if department:
        known = [r for r in pool if r.get('known_for_department') == department]
        pool = known or pool
    return max(pool, key=lambda r: r.get('popularity') or 0) if pool else None


# ---- the lookups ------------------------------------------------------------------------------

def movie_extra(tmdb_id, imdb, done):
    """Budget, revenue, companies, original language, tagline, awards for one movie."""
    tk, ok = tmdb_key(), omdb_key()
    if not ((tk and tmdb_id) or (ok and imdb)):
        return

    def fetch():
        tmdb = tmdb_get(f'/movie/{tmdb_id}', language='en-US') if tk and tmdb_id else None
        omdb = _get('https://www.omdbapi.com/?' + urllib.parse.urlencode({'i': imdb, 'apikey': ok})) \
            if ok and imdb else None
        return shape_movie(tmdb, omdb)

    request(f'movie:{tmdb_id or imdb}', fetch, done)


def person(name, department, done):
    """A person's biography and filmography, found by name."""
    if not (tmdb_key() and name):
        return

    def fetch():
        found = tmdb_get('/search/person', query=name).get('results')
        hit = pick_person(found, name, department)
        if not hit:
            return {}
        return shape_person(tmdb_get(f'/person/{hit["id"]}', append_to_response='combined_credits'))

    request(f'person:{name.casefold()}', fetch, done)
