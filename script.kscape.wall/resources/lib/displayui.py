"""Display & aspect ratio in Kodi: the settings (KScape's Skin settings → Display & aspect ratio),
the stage they give for the current screen (display.py), and the Home window properties the
skin's display transform reads.

Settings are skin strings, so they persist with the skin's other settings:
  KScapeAspect     auto | 16:9 | 21:9 | 2.35 | 2.39 | 2.40
  KScapeScopeRows  auto | 2 | 3            cover wall rows in a CinemaScope band
  KScapeVOffset    px, -300..300           move the interface down (+) or up (-)
  KScapeHOffset    px, -300..300           move it right (+) or left (-)
  KScapeSafeArea   %, 0..10                margin on every side
Changing one shows a preview of the area KScape will use and asks to keep it; without an
answer it goes back after PREVIEW_S, as Kodi does after a resolution change.
"""
import xbmc
import xbmcaddon
import xbmcgui

from . import display as D

ADDON = xbmcaddon.Addon('script.kscape.wall')
HOME = xbmcgui.Window(10000)
KEYS = {'aspect': 'KScapeAspect', 'rows': 'KScapeScopeRows', 'voffset': 'KScapeVOffset',
        'hoffset': 'KScapeHOffset', 'safe': 'KScapeSafeArea'}
PREVIEW_S = 15
S_ASPECT = {'auto': 32380, '16:9': 32381, '21:9': 32382, '2.35': 32383, '2.39': 32384, '2.40': 32385}
S_ROWS = {'auto': 32386, '2': 32387, '3': 32388}
S_HEADING = {'aspect': 32389, 'rows': 32390, 'voffset': 32391, 'hoffset': 32392, 'safe': 32393}
S_KEEP, S_KEEP_TEXT, S_DETECTED, S_PX, S_PERCENT = 32394, 32395, 32396, 32397, 32398


def tr(i):
    return ADDON.getLocalizedString(i)


def _int(text, default=0):
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return default


def settings():
    get = lambda k: xbmc.getInfoLabel(f'Skin.String({KEYS[k]})')
    aspect = get('aspect') if get('aspect') in dict(D.ASPECTS) else 'auto'
    rows = get('rows') if get('rows') in D.ROWS else 'auto'
    return {'aspect': aspect, 'rows': rows, 'voffset': _int(get('voffset')), 'hoffset': _int(get('hoffset')),
            'safe': _int(get('safe'))}


def screen():
    return xbmcgui.getScreenWidth(), xbmcgui.getScreenHeight()


def current(cover_pitch=303, values=None):
    """The stage for the screen Kodi draws on now and the display settings."""
    v = values or settings()
    w, h = screen()
    return D.stage(w, h, v['aspect'], v['rows'], v['voffset'], v['hoffset'], v['safe'], cover_pitch)


def publish(values=None):
    """Set the Home properties the display transform (Includes_Display.xml) follows. Returns the
    stage."""
    st = current(values=values)
    for k, val in D.properties(st).items():
        if HOME.getProperty(k) != val:
            HOME.setProperty(k, val)
    return st


def label(key, value):
    if key == 'aspect':
        return tr(S_ASPECT.get(value, 32380))
    if key == 'rows':
        return tr(S_ROWS.get(value, 32386))
    if key == 'safe':
        return tr(S_PERCENT).format(value)
    return tr(S_PX).format(f'{value:+d}' if value else '0')


def labels():
    """Skin strings the settings window shows as each row's value (KScape…Label)."""
    v = settings()
    for key in KEYS:
        xbmc.executebuiltin(f'Skin.SetString({KEYS[key]}Label,{label(key, v[key])})')


def _choices(key):
    if key == 'aspect':
        return [k for k, _ in D.ASPECTS]
    if key == 'rows':
        return list(D.ROWS)
    if key == 'safe':
        return list(range(0, D.SAFE_MAX + 1))
    return list(range(-D.OFFSET_MAX, D.OFFSET_MAX + 1, D.OFFSET_STEP * 2))


def _set(key, value):
    xbmc.executebuiltin(f'Skin.SetString({KEYS[key]},{value})')


def choose(key):
    """One display setting: pick a value, see it applied, keep it or let it go back."""
    values = settings()
    old = values[key]
    options = _choices(key)
    names = [label(key, o) for o in options]
    if key == 'aspect':
        w, h = screen()
        names[0] = f'{names[0]}  ({tr(S_DETECTED).format(D.detected(w, h), w, h)})'
    pre = options.index(old) if old in options else 0
    i = xbmcgui.Dialog().select(tr(S_HEADING[key]), names, preselect=pre)
    if i < 0 or options[i] == old:
        return
    _set(key, options[i])
    publish(dict(values, **{key: options[i]}))
    if not confirm():
        _set(key, old)
        publish(dict(values, **{key: old}))
    labels()


def confirm():
    """Keep this layout? Back, No or no answer within PREVIEW_S go back."""
    return xbmcgui.Dialog().yesno(tr(S_KEEP), tr(S_KEEP_TEXT).format(PREVIEW_S), autoclose=PREVIEW_S * 1000)


def preview():
    """Preview layout: the area KScape uses with the current settings (the preview window draws
    its edges, centre and safe area) until Back."""
    publish()
    win = Preview('script-kscape-preview.xml', ADDON.getAddonInfo('path'), 'Default', '1080i')
    win.doModal()
    del win


class Preview(xbmcgui.WindowXMLDialog):
    def onInit(self):
        self.setProperty('aspect', label('aspect', settings()['aspect']))
        w, h = screen()
        self.setProperty('screen', f'{w} × {h}')

    def onAction(self, action):
        if action.getId() in (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_SELECT_ITEM):
            self.close()


def run(args):
    """RunScript(script.kscape.wall,display,<aspect|rows|voffset|hoffset|safe|preview|labels>)."""
    what = args[0] if args else 'labels'
    if what == 'preview':
        preview()
    elif what in KEYS:
        choose(what)
    else:
        labels()
    publish()
