"""Service: plays scenes and Demo Scripts (resources/lib/demoservice.py), and keeps the display &
aspect ratio properties the skin reads current (resources/lib/displayui.py). Starts with Kodi."""
import threading

import xbmc

from resources.lib.demoservice import run

DISPLAY_CHECK_S = 3.0


def follow_display():
    """Publish the display transform at start, then whenever the screen or a display setting
    changes (a resolution change, the settings edited outside KScape's dialogs)."""
    from resources.lib import displayui, versionsui
    versionsui.labels()
    mon = xbmc.Monitor()
    seen = None
    while not mon.abortRequested():
        try:
            now = (displayui.screen(), tuple(sorted(displayui.settings().items())))
            if now != seen:
                seen = now
                displayui.publish()
                displayui.labels()
        except Exception as e:                       # never take the scene service down with it
            xbmc.log(f'kscape: display properties: {e}', xbmc.LOGWARNING)
        if mon.waitForAbort(DISPLAY_CHECK_S):
            break


if __name__ == '__main__':
    threading.Thread(target=follow_display, daemon=True).start()
    run()
