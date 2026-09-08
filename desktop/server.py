"""Standalone app backend: reserves a free loopback port and announces it."""
import argparse
import json
import socket
from pathlib import Path
import uvicorn
import app

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--port-file',required=True)
    args=parser.parse_args()
    sock=socket.socket()
    # Stable origin keeps the app's local formula history across launches.
    for preferred in range(8766,8786):
        try:
            sock.bind(('127.0.0.1',preferred))
            break
        except OSError:
            continue
    else:
        sock.bind(('127.0.0.1',0))
    sock.listen(128)
    port=sock.getsockname()[1]
    Path(args.port_file).write_text(json.dumps({'port':port}))
    uvicorn.Server(uvicorn.Config(app.app,log_level='warning',access_log=False)).run(sockets=[sock])
