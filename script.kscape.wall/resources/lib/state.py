"""Wall state that survives Kodi restarts, kept in the add-on's profile folder."""
import json
import os

import xbmcvfs

PATH = xbmcvfs.translatePath('special://profile/addon_data/script.kscape.wall/state.json')


def load():
    try:
        with open(PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save(**values):
    state = load()
    state.update(values)
    try:
        os.makedirs(os.path.dirname(PATH), exist_ok=True)
        with open(PATH, 'w') as f:
            json.dump(state, f)
    except OSError:
        pass                      # losing the remembered position is harmless
