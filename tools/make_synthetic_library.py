"""Grow a Kodi video database to N movies for stress tests (never run this on a real library).

Usage: python3 tools/make_synthetic_library.py <MyVideos131.db copy> <target-count>

New movies clone existing entries: their cast, directors, genres, artwork and stream details are
copied, and each gets a unique title so duplicate merging does not hide it. The clones keep the
original metadata, so the shuffle ranking sees realistic clusters, not random noise.
"""
import sqlite3
import sys

COPY_BY_MEDIA = ['genre_link', 'director_link', 'actor_link', 'writer_link', 'studio_link',
                 'country_link', 'uniqueid', 'rating', 'tag_link']


def columns(db, table):
    return [r[1] for r in db.execute(f'PRAGMA table_info({table})')]


def main(path, target):
    db = sqlite3.connect(path)
    db.isolation_level = None
    db.execute('BEGIN')
    # Only movies Kodi lists (movie_view) that also have a file record, so every clone is valid.
    sources = db.execute('SELECT m.idMovie, m.idFile, m.c00 FROM movie m '
                         'JOIN files f ON f.idFile = m.idFile '
                         'WHERE m.idMovie IN (SELECT idMovie FROM movie_view) '
                         'ORDER BY m.idMovie').fetchall()
    have = len(sources)
    if have == 0:
        sys.exit('no source movies')
    next_movie = db.execute('SELECT MAX(idMovie) FROM movie').fetchone()[0] + 1
    next_file = db.execute('SELECT MAX(idFile) FROM files').fetchone()[0] + 1
    for k in range(target - have):
        src_movie, src_file, title = sources[k % have]
        idmovie, idfile = next_movie + k, next_file + k
        fpath, fname, pc, lp, da = db.execute(
            'SELECT idPath, strFilename, playCount, lastPlayed, dateAdded FROM files WHERE idFile=?',
            (src_file,)).fetchone()
        db.execute('INSERT INTO files (idFile, idPath, strFilename, playCount, lastPlayed, dateAdded) '
                   'VALUES (?,?,?,?,?,?)', (idfile, fpath, f'synthetic_{idmovie:05d}.mkv', 0, None, da))
        cols = columns(db, 'movie')
        values = db.execute('SELECT * FROM movie WHERE idMovie=?', (src_movie,)).fetchone()
        row = dict(zip(cols, values))
        row.update(idMovie=idmovie, idFile=idfile, c00=f'{title} [synthetic {idmovie:05d}]')
        db.execute(f'INSERT INTO movie ({",".join(cols)}) VALUES ({",".join("?" * len(cols))})',
                   [row[c] for c in cols])
        # movie_view only lists files with a videoversion row, so every clone needs one.
        vtype = db.execute('SELECT idType, itemType FROM videoversion WHERE idFile=?',
                           (src_file,)).fetchone() or (0, 0)
        db.execute('INSERT INTO videoversion (idFile, idMedia, media_type, itemType, idType) '
                   "VALUES (?,?,'movie',?,?)", (idfile, idmovie, vtype[1], vtype[0]))
        db.execute("INSERT INTO art (media_id, media_type, type, url) "
                   "SELECT ?, 'movie', type, url FROM art WHERE media_id=? AND media_type='movie'",
                   (idmovie, src_movie))
        for table in COPY_BY_MEDIA:
            # Skip the table's own auto-increment key so SQLite assigns a fresh one.
            tcols = [r[1] for r in db.execute(f'PRAGMA table_info({table})') if not r[5]]
            if 'media_id' not in tcols:
                continue
            sel = ','.join('? ' if c == 'media_id' else c for c in tcols)
            db.execute(f'INSERT INTO {table} ({",".join(tcols)}) SELECT {sel} FROM {table} '
                       f'WHERE media_id=? AND media_type=\'movie\'', (idmovie, src_movie))
        scols = columns(db, 'streamdetails')
        sel = ','.join('? ' if c == 'idFile' else c for c in scols)
        db.execute(f'INSERT INTO streamdetails ({",".join(scols)}) SELECT {sel} FROM streamdetails '
                   f'WHERE idFile=?', (idfile, src_file))
    db.execute('COMMIT')
    total = db.execute('SELECT COUNT(*) FROM movie').fetchone()[0]
    print(f'{path}: {total} movies ({have} source entries cloned)')


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]))
