"""Time VideoLibrary.GetMovies for each property group against the running test Kodi.

Usage: python3 -u tools/bench_library.py [group ...]    (groups default to all)
Each group is queried on its own connection with a long read timeout, and results print as they
finish, so a slow group does not hide the others.
"""
import json
import socket
import sys
import time

PORT = 9091
SORT = {'method': 'sorttitle', 'order': 'ascending', 'ignorearticle': True}
GROUPS = {
    'none': [],
    'title-year': ['title', 'year'],
    'art': ['art'],
    'genre-director-set-tag': ['genre', 'director', 'setid', 'tag'],
    'cast': ['cast'],
    'streamdetails': ['streamdetails'],
    'plot': ['plot'],
    'resume-playcount': ['resume', 'playcount'],
}


def call(method, params, read_timeout=1800):
    s = socket.create_connection(('127.0.0.1', PORT), timeout=10)
    s.settimeout(read_timeout)
    s.sendall(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode())
    buf, depth, started = b'', 0, False
    while True:
        ch = s.recv(1)
        if not ch:
            raise RuntimeError('connection closed')
        buf += ch
        if ch == b'{':
            depth += 1
            started = True
        elif ch == b'}':
            depth -= 1
        if started and depth == 0:
            msg = json.loads(buf)
            if msg.get('id') == 1:
                s.close()
                return msg
            buf, started = b'', False


def main(names):
    print(f"total movies: {call('VideoLibrary.GetMovies', {'limits': {'start': 0, 'end': 1}})['result']['limits']['total']}")
    for name in names:
        t0 = time.time()
        msg = call('VideoLibrary.GetMovies', {'properties': GROUPS[name], 'sort': SORT})
        dt = time.time() - t0
        n = len(msg.get('result', {}).get('movies', []))
        print(f'{name:24s} {dt:8.2f}s  movies={n}  error={msg.get("error")}')


if __name__ == '__main__':
    main(sys.argv[1:] or list(GROUPS))
