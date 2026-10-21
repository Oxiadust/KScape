"""Every KScape window and dialog this script has open, and the rule for opening a new view.

A Python window's doModal() only returns when the script closes it. Going to Home without
closing it - the remote's Home key or a long press on Back, often while a movie plays - leaves
the window open underneath Home, invisible. KScape opens one view at a time, so such a window
used to block every later Movies / Music / TV Shows request from Home.

Now a request made from Home while views are still open underneath first asks the script that
owns them to close them (innermost first, as Back would), waits for it, then opens the view.
A request while a KScape view is on screen (a double press) is still ignored.
"""
import threading
import time

import xbmc
import xbmcgui

HOME = xbmcgui.Window(10000)
PROP_OPEN = 'kscape.wall.open'          # time the open views were opened (empty: none)
PROP_ABANDON = 'kscape.wall.abandon'    # set by a new request: close what is open
DOUBLE_PRESS_S = 2.0
WAIT_S = 6.0

_stack = []
_abandoned = threading.Event()          # closing everything: open nothing new


def run(window):
    """window.doModal(), tracked so a later request can close it."""
    if _abandoned.is_set():
        return
    _stack.append(window)
    try:
        window.doModal()
    finally:
        if window in _stack:
            _stack.remove(window)


def under(window):
    """The tracked window `window` was opened over (None: it was opened from Home)."""
    i = _stack.index(window) if window in _stack else 0
    return _stack[i - 1] if i > 0 else None


def abandoned():
    """True once a later request is closing every KScape window (waits should give up)."""
    return _abandoned.is_set()


def close_all():
    """Close every tracked window, innermost first. Windows may define abandon() to close the
    way they do on Back (remembering where they were); otherwise close() is used."""
    _abandoned.set()
    for window in reversed(list(_stack)):
        try:
            getattr(window, 'abandon', window.close)()
        except Exception as e:                       # a window half gone must not stop the rest
            xbmc.log(f'kscape: closing {type(window).__name__} failed: {e}', xbmc.LOGWARNING)


def claim():
    """May this request open a view? True after closing views left open under Home."""
    stamp = HOME.getProperty(PROP_OPEN)
    if stamp:
        try:
            age = time.time() - float(stamp)
        except ValueError:
            age = DOUBLE_PRESS_S
        if not xbmc.getCondVisibility('Window.IsActive(home)') or age < DOUBLE_PRESS_S:
            return False                             # a view is showing, or is just opening
        xbmc.log('kscape: closing views left open under Home', xbmc.LOGINFO)
        HOME.setProperty(PROP_ABANDON, '1')
        mon = xbmc.Monitor()
        waited = 0.0
        while HOME.getProperty(PROP_OPEN) and waited < WAIT_S:
            if mon.waitForAbort(0.05):
                return False
            waited += 0.05
        if HOME.getProperty(PROP_OPEN):
            xbmc.log('kscape: views under Home did not close', xbmc.LOGWARNING)
            return False
    HOME.clearProperty(PROP_ABANDON)
    HOME.setProperty(PROP_OPEN, str(time.time()))
    return True


def release():
    HOME.clearProperty(PROP_OPEN)


def watch():
    """Start the thread that honours a later request's PROP_ABANDON; stop it with the returned
    event once the views are closed."""
    done = threading.Event()

    def loop():
        while not done.wait(0.1):
            if HOME.getProperty(PROP_ABANDON):
                HOME.clearProperty(PROP_ABANDON)
                close_all()

    threading.Thread(target=loop, daemon=True).start()
    return done
