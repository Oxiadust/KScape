"""Movie info screen: a large panel that slides up over the wall or list (WindowXMLDialog).

Shows the poster, a Return / Resume / Play / Trailer menu, and the movie's facts, synopsis,
genres, cast, director and collection. The dialog only reports what was chosen; the caller
closes it and starts playback, so the video never plays underneath an open dialog.

Kodi gives scripts no way to measure text, so the right-hand column is laid out from
estimated line counts (info.estimate_lines); the synopsis scrolls if it is longer than its box.
"""
import xbmcaddon
import xbmcgui

from . import info
from .library import fetch_details

ADDON = xbmcaddon.Addon('script.kscape.wall')
BACK = (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU)
PLAY = (xbmcgui.ACTION_PLAYER_PLAY,)

MENU = 100
SUMMARY = 210
SECTIONS = [  # (heading control, value control, string id, key)
    (220, 221, 32061, 'plot'),
    (230, 231, 32062, 'genre'),
    (240, 241, 32063, 'cast'),
    (250, 251, 32064, 'director'),
    (260, 261, 32065, 'set'),
]

# Layout of the right-hand column, in panel pixels (see script-kscape-info.xml).
TOP, BOTTOM = 88, 954
BODY_PX, LINE_H = 29, 38
TEXT_W = 1150                  # summary and synopsis width
VALUE_W = 910                  # values beside a heading
HEADING_H = 44
SECTION_GAP = 26
ROW_GAP = 18


class DetailsDialog(xbmcgui.WindowXMLDialog):

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self.movie = kwargs['movie']
        self.details = kwargs.get('details') or {}
        self.choice = None

    def onInit(self):
        m, d = self.movie, self.details
        self.setProperty('title', d.get('title') or m.title)
        self.setProperty('poster', m.poster)
        self.setProperty('badge', m.badge)
        self._layout()
        menu = self.getControl(MENU)
        menu.reset()
        items = [('return', ADDON.getLocalizedString(32066), '')]
        resume = ((d.get('resume') or {}).get('position') or m.resume_position or 0)
        if resume > 0:
            items.append(('resume', ADDON.getLocalizedString(32067), info.clock(resume)))
        items.append(('play', ADDON.getLocalizedString(32068), ''))
        if d.get('trailer'):
            items.append(('trailer', ADDON.getLocalizedString(32069), ''))
        listitems = []
        for key, label, label2 in items:
            li = xbmcgui.ListItem(label, label2)
            li.setProperty('action', key)
            listitems.append(li)
        menu.addItems(listitems)
        keys = [k for k, _, _ in items]
        menu.selectItem(keys.index('resume' if 'resume' in keys else 'play'))
        self.setFocusId(MENU)

    def _layout(self):
        d = self.details
        tr = ADDON.getLocalizedString
        values = {
            'plot': d.get('plot') or self.movie.plot,
            'genre': ', '.join(d.get('genre') or sorted(self.movie.genres)),
            'cast': ', '.join(info.cast_names(d) if d else self.movie.cast),
            'director': ', '.join(d.get('director') or sorted(self.movie.directors)),
            'set': d.get('set') or '',
        }
        y = TOP
        summary = info.summary_line(d, tr) if d else ''
        box = self.getControl(SUMMARY)
        if summary:
            lines = min(3, info.estimate_lines(summary, TEXT_W, BODY_PX))
            box.setPosition(box.getX(), y)
            box.setHeight(lines * LINE_H)
            box.setText(summary)
            box.setVisible(True)
            y += lines * LINE_H + SECTION_GAP
        else:
            box.setVisible(False)

        # Rows below the synopsis come first in the budget; the synopsis gets what is left.
        rows = []
        for heading, value, label, key in SECTIONS[1:]:
            text = values[key]
            lines = min(3, info.estimate_lines(text, VALUE_W, BODY_PX)) if text else 0
            rows.append((heading, value, label, text, lines))
        rows_h = sum(max(1, n) * LINE_H + ROW_GAP for *_, text, n in rows if text)

        heading, value, label, key = SECTIONS[0]
        plot = values['plot']
        h_ctl, v_ctl = self.getControl(heading), self.getControl(value)
        if plot:
            room = BOTTOM - y - HEADING_H - SECTION_GAP - rows_h
            lines = max(2, min(info.estimate_lines(plot, TEXT_W, BODY_PX), room // LINE_H))
            h_ctl.setLabel(tr(label))
            h_ctl.setPosition(h_ctl.getX(), y)
            v_ctl.setPosition(v_ctl.getX(), y + HEADING_H)
            v_ctl.setHeight(lines * LINE_H)
            v_ctl.setText(plot)
            y += HEADING_H + lines * LINE_H + SECTION_GAP
        for c in (h_ctl, v_ctl):
            c.setVisible(bool(plot))

        for heading, value, label, text, lines in rows:
            h_ctl, v_ctl = self.getControl(heading), self.getControl(value)
            for c in (h_ctl, v_ctl):
                c.setVisible(bool(text) and y + LINE_H <= BOTTOM)
            if not text:
                continue
            lines = max(1, min(lines, (BOTTOM - y) // LINE_H))
            h_ctl.setLabel(tr(label))
            h_ctl.setPosition(h_ctl.getX(), y)
            v_ctl.setPosition(v_ctl.getX(), y)
            v_ctl.setHeight(lines * LINE_H)
            v_ctl.setText(text)
            y += lines * LINE_H + ROW_GAP

    def onClick(self, control_id):
        if control_id != MENU:
            return
        item = self.getControl(MENU).getSelectedItem()
        key = item.getProperty('action') if item else 'return'
        self.choice = None if key == 'return' else key
        self.close()

    def onAction(self, action):
        aid = action.getId()
        if aid in BACK:
            self.choice = None
            self.close()
        elif aid in PLAY:
            self.choice = 'resume' if self.movie.resume_position > 0 else 'play'
            self.close()


def show_details(movie):
    """Open the info screen for `movie`. Returns (choice, details): choice is 'play', 'resume',
    'trailer' or None for Return/Back; details is the GetMovieDetails dict (or None)."""
    details = fetch_details(movie.movieid)
    dialog = DetailsDialog('script-kscape-info.xml', ADDON.getAddonInfo('path'), 'Default', '1080i',
                           movie=movie, details=details)
    dialog.doModal()
    choice = dialog.choice
    del dialog
    return choice, details
