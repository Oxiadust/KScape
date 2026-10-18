"""Kodi's own favourites (favourites.xml), read and changed through JSON-RPC.

KScape keeps no favourites of its own. An item is a favourite when Kodi has the entry Kodi itself
would create for it from its context menu, so favourites added in either place show in both:

  movie    PlayMedia("<file>")                                  type 'media', path = file
  album    ActivateWindow(10502,"musicdb://albums/<id>/",return)  type 'window', window 'music'
  TV show  ActivateWindow(10025,"videodb://tvshows/titles/<id>/",return)  window 'videos'

Favourites.AddFavourite adds the entry, or removes it when it already exists (Kodi 21).
"""
import os

from .media import Album, Show
from .model import Movie


def _norm_window_param(param):
    """'musicdb://albums/5/?x=1' and 'musicdb://albums/5' both -> 'musicdb://albums/5/'."""
    p = (param or '').strip().strip('"').split('?', 1)[0]
    return p if p.endswith('/') else p + '/'


def key_of(item):
    """The favourites entry that marks `item`, as a hashable key, or None if it cannot have one."""
    if isinstance(item, Movie):
        return ('media', item.file) if item.file else None
    if isinstance(item, Album):
        return ('window', f'musicdb://albums/{item.albumid}/')
    if isinstance(item, Show):
        return ('window', f'videodb://tvshows/titles/{item.tvshowid}/')
    return None


def entry_key(fav):
    """Key for one Favourites.GetFavourites entry (see key_of)."""
    if fav.get('type') == 'media' and fav.get('path'):
        return ('media', fav['path'])
    if fav.get('type') == 'window' and fav.get('windowparameter'):
        return ('window', _norm_window_param(fav['windowparameter']))
    return None


def add_params(item):
    """Favourites.AddFavourite parameters for `item`."""
    if isinstance(item, Movie):
        return {'title': item.title, 'type': 'media', 'path': item.file, 'thumbnail': item.poster}
    if isinstance(item, Album):
        title = f'{item.title} - {item.artist}' if item.artist else item.title
        return {'title': title, 'type': 'window', 'window': 'music',
                'windowparameter': key_of(item)[1], 'thumbnail': item.poster}
    return {'title': item.title, 'type': 'window', 'window': 'videos',
            'windowparameter': key_of(item)[1], 'thumbnail': item.poster}


class Favourites:
    """A snapshot of Kodi's favourites, refreshed when favourites.xml changes on disk.

    One instance is shared by the views on screen; `version` goes up whenever the set changes, so
    each view can tell whether it has caught up (compare with the version it last drew)."""

    def __init__(self, rpc, path):
        self.rpc = rpc
        self.path = path
        self.keys = frozenset()
        self.stamp = None
        self.version = 0
        self.refresh()

    def _stamp(self):
        try:
            st = os.stat(self.path)
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def refresh(self):
        self.stamp = self._stamp()
        result = self.rpc('Favourites.GetFavourites', {'properties': ['window', 'windowparameter', 'path']})
        keys = frozenset(k for k in map(entry_key, result.get('favourites') or []) if k)
        if keys != self.keys:
            self.keys = keys
            self.version += 1

    def poll(self):
        """Re-read if favourites.xml changed (e.g. edited from Kodi's own favourites window).
        Returns the current version."""
        if self._stamp() != self.stamp:
            self.refresh()
        return self.version

    def contains(self, item):
        k = key_of(item)
        return k is not None and k in self.keys

    def supports(self, item):
        return key_of(item) is not None

    def toggle(self, item):
        """Add or remove `item`; returns whether it is a favourite afterwards."""
        if not self.supports(item):
            return False
        self.rpc('Favourites.AddFavourite', add_params(item))
        self.refresh()
        return self.contains(item)
