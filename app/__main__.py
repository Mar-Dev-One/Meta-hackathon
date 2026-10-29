"""python -m app [--port 8000]: the app on http://127.0.0.1:<port> (app/server.py)."""

import argparse

import uvicorn

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--port", type=int, default=8000)
parser.add_argument("--host", default="127.0.0.1", help="127.0.0.1 keeps it on this machine")
args = parser.parse_args()
uvicorn.run("app.server:app", host=args.host, port=args.port)
