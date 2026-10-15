"""Drive a running test Kodi (JSON-RPC TCP 9090) through wall navigation checks.

Usage: python3 -I tools/kodi_nav_test.py
Prints the focused window/item after each step so focus behaviour can be checked.
"""
import json
import os
import socket
import time

# Test Kodi listens on 9091 (see kodi_smoke_test.sh); set KSCAPE_RPC_PORT=9090 for a real Kodi.
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


def label(name, key):
    return rpc('XBMC.GetInfoLabels', {'labels': [name]})[name] or f'<{key}>'


def where():
    props = rpc('GUI.GetProperties', {'properties': ['currentwindow', 'currentcontrol']})
    pos = label('Container(50).CurrentItem', 'pos')
    return f"{props['currentwindow']['label']} | {props['currentcontrol']['label']} | item {pos}"


def step(desc, method, repeat=1, settle=0.6):
    t0 = time.time()
    for _ in range(repeat):
        rpc(method)
    sent = time.time() - t0
    time.sleep(settle)
    print(f'{desc:<34} sent {repeat} in {sent:.2f}s -> {where()}')


def main():
    print(f"{'start':<34} -> {where()}")
    step('right', 'Input.Right')
    step('left', 'Input.Left')
    step('up', 'Input.Up')
    step('30x down burst', 'Input.Down', repeat=30, settle=1.5)
    step('11x right burst (row wrap?)', 'Input.Right', repeat=11, settle=1.0)
    rpc('Input.ExecuteAction', {'action': 'screenshot'})
    step('back', 'Input.Back', settle=1.5)
    step('select (reopen Movies)', 'Input.Select', settle=2.5)


if __name__ == '__main__':
    main()
