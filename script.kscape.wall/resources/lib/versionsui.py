"""Movie versions in KScape's Skin settings: which version Play starts (versions.order)."""
import xbmc
import xbmcaddon
import xbmcgui

from . import versions as V

ADDON = xbmcaddon.Addon('script.kscape.wall')
KEY = 'KScapeVersionPreference'
S_PREF = {'4K': 32372, '1080p': 32373, '720p': 32374, 'SD': 32375, 'default': 32376}
S_HEADING = 32377


def tr(i):
    return ADDON.getLocalizedString(i)


def label(value):
    return tr(S_PREF.get(value, 32372))


def labels():
    value = xbmc.getInfoLabel(f'Skin.String({KEY})') or '4K'
    xbmc.executebuiltin(f'Skin.SetString({KEY}Label,{label(value)})')


def choose():
    value = xbmc.getInfoLabel(f'Skin.String({KEY})') or '4K'
    options = list(V.PREFERENCES)
    i = xbmcgui.Dialog().select(tr(S_HEADING), [label(o) for o in options],
                                preselect=options.index(value) if value in options else 0)
    if i >= 0:
        xbmc.executebuiltin(f'Skin.SetString({KEY},{options[i]})')
        xbmc.executebuiltin(f'Skin.SetString({KEY}Label,{label(options[i])})')


def run(args):
    if args[:1] == ['preference']:
        choose()
    else:
        labels()
