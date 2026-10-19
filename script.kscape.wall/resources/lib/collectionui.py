"""Collections in the views: where they are kept, their names, and the dialogs that change them
(shared by the collections view, the cover wall and the list view). Each library (movies, music,
TV) has its own collections."""
import os

import xbmcaddon
import xbmcgui
import xbmcvfs

from . import collectionmodel as C

ADDON = xbmcaddon.Addon('script.kscape.wall')
FOLDER = xbmcvfs.translatePath('special://profile/addon_data/script.kscape.wall/')
NAMES = {'new': 32151, 'paused': 32152, 'played': 32153, 'scenes': 32210, 'demos': 32211}
S_NEW_COLLECTION = 32158
S_COLLECT = 32164
S_NAME = 32169
S_ADD_HEADING = 32172


def tr(string_id):
    return ADDON.getLocalizedString(string_id)


def store(kind):
    """The user's collections of `kind`: collections.json (movies), collections-music.json,
    collections-tv.json."""
    name = 'collections.json' if kind.name == 'movies' else f'collections-{kind.name}.json'
    return C.Store(os.path.join(FOLDER, name))


def builtins(kind):
    return C.BUILTINS.get(kind.name, C.BUILTIN)


def new_days():
    try:
        days = ADDON.getSettingInt('new_days')
    except Exception:
        days = 0
    return days if days > 0 else C.DEFAULT_NEW_DAYS


def all_collections(kind, st):
    """[(id, name, built in)] in display order: New, Paused, Played (no Paused for music), then
    the user's own."""
    return [(cid, tr(NAMES[cid]), True) for cid in builtins(kind)] + [(c['id'], c['name'], False) for c in st.items]


def name_of(cid, st):
    if cid in NAMES:
        return tr(NAMES[cid])
    c = st.get(cid)
    return c['name'] if c else ''


def members(cid, st, library, shown, days=None):
    """(item, stored key or None) pairs of collection `cid`, in its order. `library` is every
    library entry, `shown` what the views show (duplicates merged or not)."""
    if cid in C.BUILTIN:
        return [(m, None) for m in C.builtin_movies(cid, shown, days or new_days())]
    c = st.get(cid)
    return C.resolve(c['members'], library, shown) if c else []


def ask_name(previous=''):
    """A collection name from Kodi's keyboard, or '' if cancelled."""
    return (xbmcgui.Dialog().input(tr(S_NAME), previous, type=xbmcgui.INPUT_ALPHANUM) or '').strip()


def create(st):
    name = ask_name()
    return st.create(name) if name else None


def keys_of(copies):
    """Member keys of an item's copies (one cover may stand for duplicate movies)."""
    return [C.member_key(c) for c in copies]


def choose(movie, keys, st):
    """Add `movie` (a movie, album or show) to, or take it out of, any of the user's collections
    (a multi-select of them, ticked where it already is, plus New collection…). `keys` are the
    member keys of every copy of it. Returns True when anything changed."""
    st.poll()
    if not st.items:
        cid = create(st)
        if cid:
            st.add(cid, C.member_key(movie))
        return bool(cid)
    options = [c['name'] for c in st.items] + [tr(S_NEW_COLLECTION)]
    before = [i for i, c in enumerate(st.items) if st.contains(c['id'], keys)]
    chosen = xbmcgui.Dialog().multiselect(tr(S_ADD_HEADING).format(movie.title), options, preselect=before)
    if chosen is None:
        return False
    items = list(st.items)
    changed = False
    for i, c in enumerate(items):
        if i in chosen and i not in before:
            st.add(c['id'], C.member_key(movie))
            changed = True
        elif i not in chosen and i in before:
            st.remove(c['id'], keys)
            changed = True
    if len(items) in chosen:
        cid = create(st)
        if cid:
            st.add(cid, C.member_key(movie))
            changed = True
    return changed
