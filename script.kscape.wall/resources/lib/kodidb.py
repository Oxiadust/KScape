"""Read-only look into Kodi's own library databases, for the few things JSON-RPC does not expose:
the artwork a scraper offered (not only the one chosen) and a movie's extras.

Nothing is ever written here: changes go through JSON-RPC. A database that cannot be opened
(another Kodi version's layout, a locked file) simply yields nothing.
"""
import glob
import os
import re
import sqlite3

import xbmc
import xbmcvfs

DATABASE_DIR = 'special://database'


def db_file(prefix):
    """The newest 'MyVideosNNN.db' / 'MyMusicNN.db' in Kodi's database folder, or ''."""
    folder = xbmcvfs.translatePath(DATABASE_DIR)
    found = glob.glob(os.path.join(folder, f'{prefix}*.db'))

    def version(path):
        m = re.search(r'(\d+)\.db$', path)
        return int(m.group(1)) if m else 0

    return max(found, key=version) if found else ''


def query(prefix, sql, params=()):
    path = db_file(prefix)
    if not path:
        return []
    try:
        con = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=2)
        try:
            return con.execute(sql, params).fetchall()
        finally:
            con.close()
    except sqlite3.Error as e:
        xbmc.log(f'kscape: reading {prefix} database failed: {e}', xbmc.LOGINFO)
        return []
