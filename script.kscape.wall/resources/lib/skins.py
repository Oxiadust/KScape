"""Leave kscape for another installed skin (kscape has no Settings screens of its own)."""
import xbmcaddon
import xbmcgui

from .library import rpc

ADDON = xbmcaddon.Addon('script.kscape.wall')


def other_skins():
    result = rpc('Addons.GetAddons', {'type': 'xbmc.gui.skin', 'enabled': True, 'properties': ['name']})
    skins = [(a['addonid'], a.get('name') or a['addonid']) for a in result.get('addons', [])
             if a['addonid'] != 'skin.kscape']
    return sorted(skins, key=lambda s: s[1].lower())


def choose_skin():
    """Ask which skin to switch to. Returns its addon id, or None."""
    skins = other_skins()
    if not skins:
        xbmcgui.Dialog().ok(ADDON.getLocalizedString(32027), ADDON.getLocalizedString(32028))
        return None
    i = xbmcgui.Dialog().select(ADDON.getLocalizedString(32027), [name for _, name in skins])
    return skins[i][0] if i >= 0 else None


def switch_to(skin_id):
    """Kodi loads the skin and asks, in that skin, whether to keep it."""
    rpc('Settings.SetSettingValue', {'setting': 'lookandfeel.skin', 'value': skin_id})
