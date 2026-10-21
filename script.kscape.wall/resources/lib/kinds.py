"""The three media kinds KScape browses, and what differs between them.

Everything else - the cover wall, list view, favourites, search and the C menu - is shared and
reads its kind-specific parts from here: which library to load, the cover layout, how related
items rank, what the synopsis panel says and what Select does.
"""
import xbmc
import xbmcaddon

from . import geometry as G
from . import library as lib
from . import listmodel as L
from .media import Album, Show
from .model import Movie
from .ranking import album_score, score, show_score


class Kind:
    name = ''
    explores = False                # movie info screens offer Explore and the views filter
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
    child_types = ()                # notification item types that change one of ours (a song)
    collections_xml = 'script-kscape-collections.xml'
    s_count, s_count_one = 32154, 32155     # "{} movies", "1 movie" (collections heading)

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

    def carry(self, item, old):
        """`item` re-read from the library, keeping what the slower second query filled into
        `old` (the same item as it was)."""
        return item

    def panel(self, item):
        """(title, body) of the synopsis panel beside the focused cover."""
        return item.title, getattr(item, 'plot', '')

    def cover_badge(self, item, show=True):
        """Badge text on a cover ('' for none)."""
        return item.badge if show else ''

    def fallback(self, item):
        """Text drawn on a cover that has no artwork."""
        return f'{item.title}[CR]({item.year})' if item.year else item.title

    def from_cache(self, d):
        return self.record.from_cache(d)

    def activate(self, item, favs, library=None, page=None, resolver=None):
        """Select on an item. Returns 'search' if the user asked to search from there, or
        ('explore', filter) when they chose an Explore filter on a movie's info screen.
        `library` is what Explore filters (for its counts), `page` the info screen page to open
        on ('explore' or 'scenes')."""
        raise NotImplementedError

    def play(self, item):
        raise NotImplementedError

    def count_text(self, n):
        tr = xbmcaddon.Addon('script.kscape.wall').getLocalizedString
        return tr(self.s_count_one) if n == 1 else tr(self.s_count).format(n)

    def counter(self, shown, total):
        """The item counter: '248 movies', or '42 of 248 movies' when filters or a search
        narrow the view; '' for an empty library."""
        if not total:
            return ''
        if shown == total:
            return self.count_text(total)
        tr = xbmcaddon.Addon('script.kscape.wall').getLocalizedString
        return tr(32410).format(shown, self.count_text(total))


class Movies(Kind):
    name = 'movies'
    explores = True
    item_type = 'movie'
    record = Movie
    has_extra = True

    def total(self):
        return lib.library_total()

    def fetch_all(self):
        return lib.fetch_movies()

    def fetch_one(self, key):
        return lib.fetch_movie(key)

    def fetch_extra(self):
        """{movieid: (cast, versions)}: the top-billed cast, and Kodi's versions of movies that
        have two or more (library.fetch_versions)."""
        cast = lib.fetch_cast()
        try:
            versions = lib.fetch_versions()
        except Exception as e:                      # never lose the cast over a version listing
            xbmc.log(f'kscape: listing movie versions failed: {e}', xbmc.LOGWARNING)
            versions = {}
        return {k: (cast.get(k, ()), versions.get(k, ())) for k in set(cast) | set(versions)}

    def with_extra(self, item, extra):
        from dataclasses import replace
        cast, versions = extra.get(item.movieid, ((), ()))
        return replace(item, cast=cast, versions=lib.mark_default(versions, item.file))

    def cover_badge(self, item, show=True):
        """Every format the movie is available in: '4K · 1080p · 3D' (Skin settings can hide them)."""
        return ' · '.join(item.formats) if show else ''

    def carry(self, item, old):
        from dataclasses import replace
        if old is None:
            return item
        return replace(item, cast=old.cast, versions=lib.mark_default(old.versions, item.file))

    def activate(self, item, favs, library=None, page=None, resolver=None):
        from . import modal
        from . import scenes as S
        from .details import show_details
        focus = None
        while True:
            choice, details, extra = show_details(item, favs, library=library, page=page, focus=focus,
                                                  resolver=resolver)
            if choice == 'scenes':
                # Play the scenes, then come back to the movie's scene list when they are over.
                S.play_scenes(extra['ids'])
                if not S.wait_for_scenes(modal.abandoned):
                    return None
                page, focus = 'scenes', extra.get('focus')
                continue
            break
        if choice in ('play', 'resume'):
            lib.play(item, resume=choice == 'resume')
        elif choice == 'version':
            lib.play_version(extra['version'], resume=extra['resume'])
        elif choice == 'trailer' and details and details.get('trailer'):
            lib.play_trailer(details['trailer'], details.get('title') or item.title, item.poster)
        elif choice == 'explore':
            return 'explore', extra['filter']
        return 'search' if choice == 'search' else None

    def play(self, item):
        lib.play(item)


class Music(Kind):
    name = 'music'
    layout = G.SQUARE
    wall_xml = 'script-kscape-wall-square.xml'
    library = 'music'
    item_type = 'album'
    child_types = ('song',)
    collections_xml = 'script-kscape-collections-square.xml'
    s_count, s_count_one = 32183, 32184
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

    def activate(self, item, favs, library=None, page=None, resolver=None):
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
    child_types = ('episode',)
    s_count, s_count_one = 32185, 32186
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

    def activate(self, item, favs, library=None, page=None, resolver=None):
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
