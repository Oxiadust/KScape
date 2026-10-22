"""A movie's extras: trailers, behind-the-scenes footage, deleted scenes, interviews, featurettes
and the like (pure Python; the listing itself comes from Kodi, see actions.find_extras).

Kodi has no extras list of its own for plain library movies, so KScape follows the naming that
Kodi's media-server neighbours (Jellyfin, Emby, Plex) share:

- a sub-folder of the movie's folder named Extras, Featurettes, Behind The Scenes, Deleted
  Scenes, Interviews, Trailers, Shorts, Scenes or Other holds extras of that kind;
- a video file beside the movie named "<anything>-trailer", "-featurette", "-behindthescenes",
  "-deleted", "-interview", "-short", "-scene" or "-other" is one;
- plus the movie's own trailer link, and Kodi 21 "Extras" assets (read by actions.py).
"""
import re

from . import s as S

VIDEO = ('.mkv', '.mp4', '.m4v', '.avi', '.mov', '.wmv', '.ts', '.m2ts', '.mpg', '.mpeg', '.webm', '.iso', '.flv')

FOLDERS = {
    'extras': S.X_OTHER, 'extra': S.X_OTHER, 'other': S.X_OTHER,
    'featurettes': S.X_FEATURETTE, 'featurette': S.X_FEATURETTE,
    'behind the scenes': S.X_BEHIND, 'behindthescenes': S.X_BEHIND,
    'deleted scenes': S.X_DELETED, 'deletedscenes': S.X_DELETED,
    'interviews': S.X_INTERVIEW, 'interview': S.X_INTERVIEW,
    'trailers': S.X_TRAILER, 'trailer': S.X_TRAILER,
    'shorts': S.X_SHORT, 'short': S.X_SHORT,
    'scenes': S.X_SCENE,
}
SUFFIXES = {
    'trailer': S.X_TRAILER, 'featurette': S.X_FEATURETTE, 'behindthescenes': S.X_BEHIND,
    'deleted': S.X_DELETED, 'deletedscene': S.X_DELETED, 'interview': S.X_INTERVIEW,
    'short': S.X_SHORT, 'scene': S.X_SCENE, 'other': S.X_OTHER, 'extra': S.X_OTHER,
}
ORDER = (S.X_TRAILER, S.X_FEATURETTE, S.X_BEHIND, S.X_DELETED, S.X_INTERVIEW, S.X_SHORT, S.X_SCENE, S.X_OTHER)


def is_video(name):
    return name.lower().endswith(VIDEO)


def folder_category(name):
    """The extras category of a sub-folder name (None: not an extras folder)."""
    return FOLDERS.get(re.sub(r'\s+', ' ', (name or '').strip().lower()))


def suffix_category(filename):
    """The category a file name's '-trailer' style suffix gives (None: no suffix)."""
    stem = re.sub(r'\.[A-Za-z0-9]{2,4}$', '', filename or '')
    m = re.search(r'[-_. ]([A-Za-z]+)$', stem)
    return SUFFIXES.get(m.group(1).lower()) if m else None


def title_of(filename):
    """A readable title from a file name: no extension, no category suffix, no separators."""
    stem = re.sub(r'\.[A-Za-z0-9]{2,4}$', '', filename or '')
    m = re.search(r'[-_. ]([A-Za-z]+)$', stem)
    if m and m.group(1).lower() in SUFFIXES:
        stem = stem[:m.start()]
    return re.sub(r'[_.]+', ' ', stem).strip() or filename


def classify(entries, main_file=''):
    """Extras from a folder listing. `entries` are (name, path, is_dir, children) where children
    (for a folder) is a list of (name, path) of the folder's files. Returns
    [{'category', 'label', 'file'}] in category order."""
    found = []
    main = (main_file or '').replace('\\', '/').rsplit('/', 1)[-1]
    for name, path, is_dir, children in entries:
        if is_dir:
            cat = folder_category(name)
            if cat is None:
                continue
            for child, cpath in children or ():
                if is_video(child):
                    found.append({'category': cat, 'label': title_of(child), 'file': cpath})
        elif is_video(name) and name != main:
            cat = suffix_category(name)
            if cat is not None:
                found.append({'category': cat, 'label': title_of(name), 'file': path})
    found.sort(key=lambda e: (ORDER.index(e['category']), e['label'].lower()))
    return found
