"""Entry point.

RunScript(script.kscape.wall)             open the cover wall (one instance at a time)
RunScript(script.kscape.wall,switchskin)  choose another installed skin and switch to it
"""
import sys

import xbmcaddon
import xbmcgui

from resources.lib.skins import choose_skin, switch_to
from resources.lib.window import WallWindow

ADDON = xbmcaddon.Addon()
HOME = xbmcgui.Window(10000)


def open_wall():
    if HOME.getProperty('kscape.wall.open'):
        return
    HOME.setProperty('kscape.wall.open', '1')
    skin = None
    try:
        window = WallWindow('script-kscape-wall.xml', ADDON.getAddonInfo('path'), 'Default', '1080i')
        window.doModal()
        skin = window.pending_skin
        del window
    finally:
        HOME.clearProperty('kscape.wall.open')
    if skin:
        switch_to(skin)


if __name__ == '__main__':
    if sys.argv[1:] == ['switchskin']:
        chosen = choose_skin()
        if chosen:
            switch_to(chosen)
    else:
        open_wall()
