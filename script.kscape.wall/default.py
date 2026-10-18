"""Entry point.

RunScript(script.kscape.wall)                    movies, in the view last used (wall or list)
RunScript(script.kscape.wall,<kind>)             kind: movies, music or tv; view last used
RunScript(script.kscape.wall,<kind>,<view>)      view: covers, list, collections or favorites
RunScript(script.kscape.wall,<kind>,collections) that library's Collections view
RunScript(script.kscape.wall,music,nowplaying)   Now Playing
RunScript(script.kscape.wall,switchskin)         choose another installed skin and switch to it
RunScript(script.kscape.wall,colours,<part>)     part: main or highlight - pick a theme colour

One view at a time: a second request while a view is on screen is ignored; a request made from
Home while views are still open underneath it closes them first (modal.py).
"""
import sys

from resources.lib import modal
from resources.lib.kinds import KINDS
from resources.lib.skins import choose_skin, switch_to

VIEWS = {'covers': 'wall', 'list': 'list', 'favorites': 'favorites', 'favourites': 'favorites',
         'collections': 'collections'}


def run_view(fn):
    """Run `fn` (which opens KScape windows) as the one open view. It returns the skin the user
    chose to switch to, if any."""
    if not modal.claim():
        return
    done = modal.watch()
    skin = None
    try:
        skin = fn()
    finally:
        done.set()
        modal.release()
    if skin:
        switch_to(skin)


def open_view(kind, view=None):
    from resources.lib.window import open_wall
    if view == 'collections':
        from resources.lib.collectionwindow import show_collections
        return show_collections(kind)
    if view == 'favorites':
        return open_wall(kind, favourites=True)
    return open_wall(kind, view=view)


def now_playing():
    from resources.lib.nowplaying import show_now_playing
    show_now_playing()


def main(args):
    if args[:1] == ['colours']:
        from resources.lib import colours
        colours.choose(args[1] if len(args) > 1 else 'main')
        return
    if not args:                         # the start-up wall: show the colour theme in Skin settings
        from resources.lib import colours
        colours.sync()
    if args == ['switchskin']:
        chosen = choose_skin()
        if chosen:
            switch_to(chosen)
        return
    kind = KINDS.get(args[0] if args else 'movies', KINDS['movies'])
    view = args[1] if len(args) > 1 else None
    if view == 'nowplaying':
        run_view(now_playing)
        return
    view = VIEWS.get(view)
    run_view(lambda: open_view(kind, view))


if __name__ == '__main__':
    main(sys.argv[1:])
