"""Play a scripted tour of KScape in the isolated test Kodi, for screen recordings.

Usage: start the test Kodi (tools/kodi_smoke_test.sh), wait for the cover wall, start your screen
recording, then run:  python3 -I tools/demo_tour.py
Talks to the test Kodi on JSON-RPC port 9091 (KSCAPE_RPC_PORT to override). About 2 minutes:
Home (artwork, view cards, System and Power menus) -> cover wall (glide, synopsis, shuffle, undo) ->
movie info -> the C menu -> list view (columns, genre regrouping) -> back to the wall and Home.
"""
import json
import os
import socket
import time

PORT = int(os.environ.get('KSCAPE_RPC_PORT', '9091'))


def rpc(method, params=None):
    s = socket.create_connection(('127.0.0.1', PORT), timeout=10)
    s.sendall(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}}).encode())
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
                return msg.get('result', msg.get('error'))
            buf, started = b'', False


def window():
    return rpc('GUI.GetProperties', {'properties': ['currentwindow']})['currentwindow']['id']


def key(name, pause=0.9, times=1):
    for _ in range(times):
        rpc(f'Input.{name}')
        time.sleep(pause)


def say(text):
    print(f'{time.strftime("%H:%M:%S")}  {text}', flush=True)


def to_home():
    """Leave the wall/list through its menu (last entry is Exit) until Home is showing."""
    for _ in range(4):
        if window() == 10000:
            return
        key('ContextMenu', 1.0)
        rpc('Input.ExecuteAction', {'action': 'lastpage'})
        time.sleep(0.4)
        key('Select', 2.5)


def main():
    say('Home: rotating artwork')
    to_home()
    time.sleep(14)                               # at least one crossfade
    say('Home: Movies, Music and TV Shows view cards')
    key('Up', 1.2)
    key('Down', 0.9, times=3)                    # through List / Covers / Favourites, back to the bar
    key('Right', 1.8)                            # Music: its cards include Now Playing
    key('Right', 1.8)                            # TV Shows
    say('Home: System menu')
    key('Right', 1.5)
    key('Up', 1.2)
    key('Right', 1.0, times=3)
    key('Down', 1.5)
    say('Home: Power menu')
    key('Right', 1.5)
    key('Up', 1.2)
    key('Right', 1.0, times=2)
    key('Down', 1.2)
    key('Left', 1.0, times=4)                    # back to Movies
    time.sleep(1.0)

    say('Cover wall: glide')
    key('Select', 4.0)                           # opens the wall
    key('Right', 1.1, times=3)
    key('Down', 1.1)
    key('Right', 1.1, times=2)
    say('Cover wall: synopsis, then related covers shuffle in')
    time.sleep(7.0)
    say('Cover wall: move on and shuffle again, then Back undoes it')
    key('Left', 1.1, times=2)
    key('Up', 1.1)
    time.sleep(7.0)
    key('Back', 4.0)

    say('Movie info')
    key('Select', 3.5)
    key('Down', 1.0, times=2)
    key('Up', 1.0, times=2)
    time.sleep(2.0)
    key('Back', 2.5)

    say('C menu: change view')
    key('ContextMenu', 2.5)                      # Add to Favourites, Search..., List view, ...
    key('Down', 0.8, times=4)
    key('Up', 0.8, times=2)                      # back to "List view"
    say('List view')
    key('Select', 3.5)
    key('Down', 0.9, times=4)
    time.sleep(1.5)
    say('List view: genre column, regroup and step through values')
    key('Right', 1.5)
    key('Down', 2.5)
    key('Down', 2.0, times=2)
    key('Down', 1.2, times=3)
    say('List view: scroll the columns, sort by running time, on to quality')
    key('Right', 1.2, times=4)
    key('Down', 2.0)
    key('Right', 1.2, times=2)
    time.sleep(2.0)
    key('Left', 0.6, times=7)                    # back to the title column
    key('Down', 1.5)
    say('Back to the cover wall')
    key('Back', 4.0)
    say('Home')
    to_home()
    time.sleep(6.0)
    say('done')


if __name__ == '__main__':
    main()
