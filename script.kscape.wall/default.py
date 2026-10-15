"""Entry point: open the cover wall (one instance at a time)."""
import xbmcaddon
import xbmcgui

from resources.lib.window import WallWindow

ADDON = xbmcaddon.Addon()
HOME = xbmcgui.Window(10000)

if __name__ == '__main__' and not HOME.getProperty('kscape.wall.open'):
    HOME.setProperty('kscape.wall.open', '1')
    try:
        window = WallWindow('script-kscape-wall.xml', ADDON.getAddonInfo('path'), 'Default', '1080i')
        window.doModal()
        del window
    finally:
        HOME.clearProperty('kscape.wall.open')
