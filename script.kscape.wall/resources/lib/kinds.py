"""The three media kinds KScape browses, and what differs between them.

Everything else - the cover wall, list view, favourites, search and the C menu - is shared and
reads its kind-specific parts from here: which library to load, the cover layout, how related
items rank, what the synopsis panel says and what Select does.
"""
import xbmc

from . import geometry as G
from . import library as lib
from . import listmodel as L
from .media import Album, Show
from .model import Movie, merge_duplicates
from .ranking import album_score, score, show_score


class Kind:
    name = ''
    layout = G.POSTER
    wall_xml = 'script-kscape-wall.xml'
    library = 'video'               # Kodi library: 'video' or 'music' (scan/clean notifications)
    item_type = ''                  # JSON-RPC notification item type for one changed item
    record = None
    score_fn = staticmethod(score)
    list_spec = L.MOVIES
    s_empty = 32002                 # "Your ... library is empty"
    s_search = 32093                # search heading
    s_no_match = 32098              # empty search results
    has_extra = False               # a second, slower query fills in more (movie cast)
    merges = False                  # duplicate copies can be shown once

    def total(self):
        raise NotImplementedError

    def fetch_all(self):
        raise NotImplementedError

    def fetch_one(self, key):
        raise NotImplementedError

    def fetch_extra(self):
        return {}

    def with_extra(self, item, extra):
        return item

    def panel(self, item):
        """(title, body) of the synopsis panel beside the focused cover."""
        return item.title, getattr(item, 'plot', '')

    def fallback(self, item):
        """Text drawn on a cover that has no artwork."""
        return f'{item.title}[CR]({item.year})' if item.year else item.title

    def from_cache(self, d):
        return self.record.from_cache(d)

    def activate(self, item, favs):
        """Select on an item. Returns 'search' if the user asked to search from there."""
        raise NotImplementedError

    def play(self, item):
        raise NotImplementedError

    def visible(self, items, merge):
        return merge_duplicates(items) if merge and self.merges else items


class Movies(Kind):
    name = 'movies'
    item_type = 'movie'
    record = Movie
    has_extra = True
    merges = True

    def total(self):
        return lib.library_total()

    def fetch_all(self):
        return lib.fetch_movies()

    def fetch_one(self, key):
        return lib.fetch_movie(key)

    def fetch_extra(self):
        return lib.fetch_cast()

    def with_extra(self, item, extra):
        from dataclasses import replace
        return replace(item, cast=extra.get(item.movieid, ()))

    def activate(self, item, favs):
        from .details import show_details
        choice, details = show_details(item, favs)
        if choice in ('play', 'resume'):
            lib.play(item, resume=choice == 'resume')
        elif choice == 'trailer' and details and details.get('trailer'):
            lib.play_trailer(details['trailer'])
        return 'search' if choice == 'search' else None

    def play(self, item):
        lib.play(item)


class Music(Kind):
    name = 'music'
    layout = G.SQUARE
    wall_xml = 'script-kscape-wall-square.xml'
    library = 'music'
    item_type = 'album'
    record = Album
    score_fn = staticmethod(album_score)
    list_spec = L.MUSIC
    s_empty = 32003
    s_search = 32094
    s_no_match = 32099

    def total(self):
        return lib.album_total()

    def fetch_all(self):
        return lib.fetch_albums()

    def fetch_one(self, key):
        return lib.fetch_album(key)

    def panel(self, item):
        return item.title, item.artist

    def fallback(self, item):
        return f'{item.title}[CR][COLOR FF9AA3B5]{item.artist}[/COLOR]' if item.artist else item.title

    def activate(self, item, favs):
        from .browse import show_album
        choice = show_album(item, favs)
        if choice and choice[0] == 'play':
            lib.play_album(item.albumid, choice[1])
            open_now_playing()
        return 'search' if choice and choice[0] == 'search' else None

    def play(self, item):
        lib.play_album(item.albumid)
        open_now_playing()


class TV(Kind):
    name = 'tv'
    item_type = 'tvshow'
    record = Show
    score_fn = staticmethod(show_score)
    list_spec = L.TV
    s_empty = 32004
    s_search = 32095
    s_no_match = 32100

    def total(self):
        return lib.show_total()

    def fetch_all(self):
        return lib.fetch_shows()

    def fetch_one(self, key):
        return lib.fetch_show(key)

    def activate(self, item, favs):
        from .browse import show_tvshow
        choice = show_tvshow(item, favs)
        if choice and choice[0] == 'episode':
            lib.play_episode(choice[1], resume=choice[2])
        return 'search' if choice and choice[0] == 'search' else None

    def play(self, item):
        """Play: the first unwatched episode (or the first one, if all are watched)."""
        episodes = [e for s in lib.fetch_seasons(item.tvshowid)
                    for e in lib.fetch_episodes(item.tvshowid, s['season'])]
        if not episodes:
            return
        nxt = next((e for e in episodes if not e.get('playcount')), episodes[0])
        lib.play_episode(nxt['episodeid'])


def open_now_playing():
    """Show Now Playing over whatever is open, once Kodi has started the music."""
    mon = xbmc.Monitor()
    for _ in range(40):                       # up to 2 s
        if xbmc.getCondVisibility('Player.HasAudio') or mon.waitForAbort(0.05):
            break
    from .nowplaying import show_now_playing
    show_now_playing()


KINDS = {'movies': Movies(), 'music': Music(), 'tv': TV()}
