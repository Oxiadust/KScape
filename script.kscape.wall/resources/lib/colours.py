"""KScape's colour theme: a main colour and a highlight colour, chosen from Skin settings.

The skin ships one colour file per pair (skin.kscape/colors, made by tools/gen_colors.py):
defaults.xml is Graphite with Amber, the others are named "<Main> - <Highlight>". Choosing sets Kodi's
own skin colours setting (lookandfeel.skincolors), and Kodi reloads the skin in the new colours.
The choice is mirrored in Skin strings KScapeColourMain / KScapeColourHighlight (localised
names) for Skin settings to show.
"""
import xbmc
import xbmcaddon
import xbmcgui

from .library import rpc

ADDON = xbmcaddon.Addon('script.kscape.wall')
SETTING = 'lookandfeel.skincolors'
DEFAULT_VALUE = 'SKINDEFAULT'
# Keep in step with tools/gen_colors.py (MAINS, HIGHLIGHTS): name -> string id.
MAINS = {'Blue': 32190, 'Crimson': 32191, 'Emerald': 32192, 'Violet': 32193, 'Teal': 32194, 'Graphite': 32195}
HIGHLIGHTS = {'Amber': 32196, 'White': 32197, 'Cyan': 32198, 'Lime': 32199, 'Rose': 32200}
DEFAULT = ('Graphite', 'Amber')
HEADINGS = {'main': 32201, 'highlight': 32202}


def tr(string_id):
    return ADDON.getLocalizedString(string_id)


def parse(value):
    """(main, highlight) from a skin colours value; unknown values count as the default."""
    if value in ('', DEFAULT_VALUE, 'defaults'):
        return DEFAULT
    main, _, highlight = value.partition(' - ')
    return (main, highlight) if main in MAINS and highlight in HIGHLIGHTS else DEFAULT


def value_of(main, highlight):
    return DEFAULT_VALUE if (main, highlight) == DEFAULT else f'{main} - {highlight}'


def current():
    """The theme in use, from Kodi's info label (JSON-RPC's Settings methods are not ready yet
    when the start-up wall runs)."""
    return parse(xbmc.getInfoLabel('Skin.CurrentColourTheme'))


def sync():
    """Show the current choice in Skin settings (also after a change made in Kodi's settings)."""
    main, highlight = current()
    xbmc.executebuiltin(f'Skin.SetString(KScapeColourMain,{tr(MAINS[main])})')
    xbmc.executebuiltin(f'Skin.SetString(KScapeColourHighlight,{tr(HIGHLIGHTS[highlight])})')


def choose(part):
    """Pick the main colour (part 'main') or the highlight colour ('highlight') and apply it."""
    main, highlight = current()
    names = list(MAINS if part == 'main' else HIGHLIGHTS)
    ids = MAINS if part == 'main' else HIGHLIGHTS
    now = main if part == 'main' else highlight
    i = xbmcgui.Dialog().select(tr(HEADINGS.get(part, 32201)), [tr(ids[n]) for n in names],
                                preselect=names.index(now))
    if i < 0 or names[i] == now:
        return
    if part == 'main':
        main = names[i]
    else:
        highlight = names[i]
    xbmc.executebuiltin(f'Skin.SetString(KScapeColourMain,{tr(MAINS[main])})')
    xbmc.executebuiltin(f'Skin.SetString(KScapeColourHighlight,{tr(HIGHLIGHTS[highlight])})')
    rpc('Settings.SetSettingValue', {'setting': SETTING, 'value': value_of(main, highlight)})
