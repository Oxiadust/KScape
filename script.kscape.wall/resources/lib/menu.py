"""The C (context) menu shared by every KScape view, and the search prompt.

Every menu starts with the actions for the selected item - Add to / Remove from Favourites,
labelled from Kodi's favourites at the moment the menu opens - and Search, followed by the
view's own entries. It is Kodi's select dialog, so it looks like the rest of the skin.
"""
import xbmc
import xbmcaddon
import xbmcgui

ADDON = xbmcaddon.Addon('script.kscape.wall')
S_TITLE = 32020
S_ADD, S_REMOVE, S_SEARCH = 32090, 32091, 32092


def tr(string_id):
    return ADDON.getLocalizedString(string_id)


def show(item, favs, entries, search=True, is_favourite=None):
    """Open the menu. `entries` are the view's own (key, label) pairs. Returns the chosen key:
    'favourite', 'search', one of the entry keys, or None.

    `is_favourite` overrides favs.contains(item) (the wall counts merged duplicate copies)."""
    items = []
    if item is not None and favs is not None and favs.supports(item):
        fav = favs.contains(item) if is_favourite is None else is_favourite
        items.append(('favourite', tr(S_REMOVE if fav else S_ADD)))
    if search:
        items.append(('search', tr(S_SEARCH)))
    items += list(entries)
    if not items:
        return None
    i = xbmcgui.Dialog().select(tr(S_TITLE), [label for _, label in items])
    return items[i][0] if i >= 0 else None


def ask_search(kind, previous=''):
    """Kodi's on-screen keyboard (the skin's DialogKeyboard), scoped by its heading. Returns the
    query, or '' if cancelled."""
    return (xbmcgui.Dialog().input(tr(kind.s_search), previous, type=xbmcgui.INPUT_ALPHANUM) or '').strip()


def search_heading(query, count):
    return tr(32096 if count == 1 else 32097).format(query, count)


def wait_for_dialogs(timeout=3.0):
    """Let closing dialogs finish before a full window opens. Kodi refuses to activate a window
    while a modal dialog is still active (e.g. playing its close animation), and doModal() then
    never returns."""
    mon = xbmc.Monitor()
    waited = 0.0
    while xbmc.getCondVisibility('System.HasActiveModalDialog') and waited < timeout:
        if mon.waitForAbort(0.05):
            break
        waited += 0.05
