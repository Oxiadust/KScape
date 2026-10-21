"""The C (context) menu shared by every KScape view, and the search prompt.

The wall and list views group their menu into sections (show_sections): View Options (View,
Reduce Motion, Automatic Shuffle), Misc Options (Search, Favourites, Filters) and Actions (Undo
Shuffle, Reload Library, Add to / Remove from Favourites - labelled from Kodi's favourites at the
moment the menu opens - Add to Collection, the item's scene entries, and the exit, named for
where it goes). Other views use show(): the item's Favourites entry and Search, then their own.

Both open KScape's menu dialog (script-kscape-menu.xml): a blue panel like the rest of the skin,
headings with a rule between sections, an entry's state (On / Off, the current view) beside it.
"""
import xbmc
import xbmcaddon
import xbmcgui

ADDON = xbmcaddon.Addon('script.kscape.wall')
HOME = xbmcgui.Window(10000)
S_TITLE = 32020
S_ADD, S_REMOVE, S_SEARCH = 32090, 32091, 32092
S_VIEW_OPTIONS, S_MISC_OPTIONS, S_ACTIONS = 32401, 32402, 32403
S_VIEW, S_REDUCE_MOTION, S_AUTO_SHUFFLE = 32404, 32405, 32406
S_EXIT_WALL, S_EXIT_HOME, S_EXIT_COLLECTIONS = 32407, 32408, 32409
S_ON, S_OFF = 32030, 32031
S_COVER_WALL, S_LIST_VIEW = 32070, 32071
PROP_REDUCED = 'kscape.reduced'         # read by the info screen's slide-in animation

LIST = 300                              # not 3: WindowXML takes 2-4 for its sort and view buttons
ROW_H = 58                              # script-kscape-menu.xml
LIST_TOP = 76
PANEL_PAD = 14                          # below the last row
MAX_ROWS = 15
SCREEN_H = 1080
UP_DOWN = (xbmcgui.ACTION_MOVE_UP, xbmcgui.ACTION_MOVE_DOWN, xbmcgui.ACTION_PAGE_UP,
           xbmcgui.ACTION_PAGE_DOWN)
CLOSE = (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_CONTEXT_MENU)


def tr(string_id):
    return ADDON.getLocalizedString(string_id)


def on_off(flag):
    return tr(S_ON if flag else S_OFF)


def toggle(key, label_id, flag):
    """A toggle entry: its label, with On / Off beside it."""
    return (key, tr(label_id), on_off(flag), flag)


def favourite_entries(item, favs, is_favourite=None):
    """Add to / Remove from Favourites for `item`, if Kodi's favourites can hold it.
    `is_favourite` overrides favs.contains(item) (the wall counts merged duplicate copies)."""
    if item is None or favs is None or not favs.supports(item):
        return []
    fav = favs.contains(item) if is_favourite is None else is_favourite
    return [('favourite', tr(S_REMOVE if fav else S_ADD))]


class MenuDialog(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self.title = kwargs['title']
        self.rows = kwargs['rows']               # (key, label, value, on); key None: a heading
        self.choice = None

    def onInit(self):
        self.setProperty('heading', self.title)
        items = []
        for i, (key, label, value, on) in enumerate(self.rows):
            li = xbmcgui.ListItem(label if key else '', value or '', offscreen=True)
            if key is None:
                li.setProperty('heading', label)
                if i:
                    li.setProperty('rule', '1')
            elif on:
                li.setProperty('on', '1')
            items.append(li)
        shown = min(len(self.rows), MAX_ROWS)
        height = LIST_TOP + shown * ROW_H + PANEL_PAD
        ctl = self.getControl(LIST)
        ctl.setHeight(shown * ROW_H)
        self.getControl(110).setHeight(height)
        self.getControl(100).setPosition(560, max(40, (SCREEN_H - height) // 2))
        ctl.addItems(items)
        self.pos = self._entry_from(0, 1)
        ctl.selectItem(self.pos)
        self.setFocusId(LIST)

    def _entry_from(self, i, step):
        """The first entry (not a heading) from row `i` on, going `step`; None if there is none."""
        while 0 <= i < len(self.rows):
            if self.rows[i][0] is not None:
                return i
            i += step
        return None

    def onAction(self, action):
        aid = action.getId()
        if aid in CLOSE:
            self.close()
        elif aid in UP_DOWN:
            ctl = self.getControl(LIST)
            pos = ctl.getSelectedPosition()
            if 0 <= pos < len(self.rows) and self.rows[pos][0] is None:
                step = 1 if pos >= self.pos else -1
                nxt = self._entry_from(pos, step)
                pos = self.pos if nxt is None else nxt
                ctl.selectItem(pos)
            self.pos = pos

    def onClick(self, control_id):
        if control_id != LIST:
            return
        pos = self.getControl(LIST).getSelectedPosition()
        if 0 <= pos < len(self.rows) and self.rows[pos][0] is not None:
            self.choice = self.rows[pos][0]
            self.close()


def _row(entry):
    key, label, value, on = (tuple(entry) + ('', False))[:4]
    return key, label, value, on


def _choose(rows):
    if not any(key is not None for key, *_ in rows):
        return None
    wait_for_dialogs()
    dialog = MenuDialog('script-kscape-menu.xml', ADDON.getAddonInfo('path'), 'Default', '1080i',
                        title=tr(S_TITLE), rows=rows)
    dialog.doModal()
    choice = dialog.choice
    del dialog
    return choice


def show_sections(sections):
    """Open the sectioned menu. `sections` are (heading string id, entries) pairs; an entry is
    (key, label) or (key, label, value, on), value shown beside the label (on: in amber).
    Empty sections are left out. Returns the chosen key, or None."""
    rows = []
    for heading, entries in sections:
        if entries:
            rows.append((None, tr(heading), '', False))
            rows += [_row(e) for e in entries]
    return _choose(rows)


def show(item, favs, entries, search=True):
    """Open a plain menu: `item`'s Favourites entry, Search, then the view's own (key, label)
    `entries`. Returns the chosen key: 'favourite', 'search', one of the entry keys, or None."""
    items = favourite_entries(item, favs)
    if search:
        items.append(('search', tr(S_SEARCH)))
    items += list(entries)
    return _choose([_row(e) for e in items])


def exit_entry(window):
    """The menu's last entry, named for where closing `window` leads: the view it was opened
    over (a wall, or Collections), or Home."""
    from . import modal
    below = modal.under(window)
    if below is None:
        label = S_EXIT_HOME
    elif type(below).__name__ == 'CollectionsWindow':
        label = S_EXIT_COLLECTIONS
    else:
        label = S_EXIT_WALL
    return ('exit', tr(label))


def reduced_motion():
    return (ADDON.getSettingBool('reduced_motion')
            or xbmc.getCondVisibility('Skin.HasSetting(ReducedMotion)'))


def set_reduced_motion(flag):
    """Reduce Motion from the C menu: KScape's setting, the property its windows read, and the
    skin's own setting (system dialogs slide or just fade by it)."""
    ADDON.setSettingBool('reduced_motion', flag)
    HOME.setProperty(PROP_REDUCED, '1' if flag else '')
    if xbmc.getSkinDir() == 'skin.kscape':
        xbmc.executebuiltin('Skin.SetBool(ReducedMotion)' if flag else 'Skin.Reset(ReducedMotion)')


def set_auto_shuffle(flag):
    ADDON.setSettingBool('auto_shuffle', flag)


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
