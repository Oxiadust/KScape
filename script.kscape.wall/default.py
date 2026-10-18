"""Entry point.

RunScript(script.kscape.wall)                    movies, in the view last used (wall or list)
RunScript(script.kscape.wall,<kind>)             kind: movies, music or tv; view last used
RunScript(script.kscape.wall,<kind>,<view>)      view: covers, list or favorites
RunScript(script.kscape.wall,music,nowplaying)   Now Playing
RunScript(script.kscape.wall,switchskin)         choose another installed skin and switch to it

One wall at a time: a second request while a wall is open is ignored.
"""
import sys

import xbmcgui

from resources.lib.kinds import KINDS
from resources.lib.skins import choose_skin, switch_to

HOME = xbmcgui.Window(10000)
VIEWS = {'covers': 'wall', 'list': 'list', 'favorites': 'favorites', 'favourites': 'favorites'}


def open_wall(kind, view=None):
    from resources.lib.window import open_wall as run
    if HOME.getProperty('kscape.wall.open'):
        return
    HOME.setProperty('kscape.wall.open', '1')
    skin = None
    try:
        if view == 'favorites':
            skin = run(kind, favourites=True)
        else:
            skin = run(kind, view=view)
    finally:
        HOME.clearProperty('kscape.wall.open')
    if skin:
        switch_to(skin)


def main(args):
    if args == ['switchskin']:
        chosen = choose_skin()
        if chosen:
            switch_to(chosen)
        return
    kind = KINDS.get(args[0] if args else 'movies', KINDS['movies'])
    view = args[1] if len(args) > 1 else None
    if view == 'nowplaying':
        from resources.lib.nowplaying import show_now_playing
        show_now_playing()
        return
    open_wall(kind, VIEWS.get(view))


if __name__ == '__main__':
    main(sys.argv[1:])
