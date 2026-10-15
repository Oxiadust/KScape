# Minimal Kodi JSON-RPC client over raw TCP (port 9090). Usage: kscape-rpc.py '<method>' '<json params>'
import json, socket, sys
method = sys.argv[1]; params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
s = socket.create_connection(('127.0.0.1', 9090), timeout=10)
s.sendall(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode())
buf, depth, started = b'', 0, False
while True:
    ch = s.recv(1)
    if not ch: break
    buf += ch
    if ch == b'{': depth += 1; started = True
    elif ch == b'}': depth -= 1
    if started and depth == 0:
        msg = json.loads(buf)
        if msg.get('id') == 1: print(json.dumps(msg)[:2000]); break
        buf, started = b'', False
