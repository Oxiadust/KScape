"""Service: plays scenes and Demo Scripts (resources/lib/demoservice.py), and keeps the display &
aspect ratio properties the skin reads current (resources/lib/displayui.py). Starts with Kodi."""
import os
import shutil
import threading

import xbmc
import xbmcvfs

from resources.lib.demoservice import run

DISPLAY_CHECK_S = 3.0


def install_splash():
    """Kodi shows special://home/media/splash.png while it starts, before any skin loads: put the
    KScape logo there (next start shows it). Replaces only a splash that is not ours already."""
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', 'media', 'splash.png')
    dest = xbmcvfs.translatePath('special://home/media/splash.png')
    try:
        if os.path.exists(dest) and os.path.getsize(dest) == os.path.getsize(src):
            return
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(src, dest)
    except OSError as e:
        xbmc.log(f'kscape: installing the splash screen: {e}', xbmc.LOGWARNING)


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
    install_splash()
    threading.Thread(target=follow_display, daemon=True).start()
    run()
