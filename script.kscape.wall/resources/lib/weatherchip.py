"""The temperature Home shows after the time (Window(Home).Property(kscape.weather)).

Kodi's Weather.Temperature is always in Kodi's own unit (Settings > Interface > Regional), and the
weather add-on writes Current.Temperature in that unit too: the unit chosen in the add-on's own
settings only shows in its own window. So the service publishes the add-on's own reading
(Current.TemperatureAddon, in its unit) when the add-on is set to a unit, and follows Kodi's
setting when the add-on says "app" (or is another add-on, or has no reading yet). Empty until
the weather has been fetched.
"""
import xbmc
import xbmcaddon
import xbmcgui

HOME = xbmcgui.Window(10000)
WEATHER = xbmcgui.Window(12600)
PROP = 'kscape.weather'


def text():
    if not xbmc.getCondVisibility('Weather.IsFetched'):
        return ''
    plugin = xbmc.getInfoLabel('Weather.Plugin')
    if plugin == 'weather.openmeteo':
        try:
            unit = xbmcaddon.Addon(plugin).getSetting('unittemp')
            reading = WEATHER.getProperty('Current.TemperatureAddon')
            if unit and unit != 'app' and reading:
                return f'{round(float(reading)):d}{unit}'
        except (RuntimeError, ValueError):
            pass
    return xbmc.getInfoLabel('Weather.Temperature')


def publish():
    now = text()
    if HOME.getProperty(PROP) != now:
        HOME.setProperty(PROP, now)
