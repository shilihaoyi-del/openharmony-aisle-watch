#!/usr/bin/env python3
"""Serve the local SLAM display and atomically written ROS snapshots."""

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
from socketserver import ThreadingMixIn
import time
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/watch": ("watch.html", "text/html; charset=utf-8"),
    "/watch.js": ("watch.js", "text/javascript; charset=utf-8"),
}


def snapshot(path, live=False):
    try:
        data = path.read_bytes()
        state = json.loads(data.decode("utf-8"))
        now = time.time()
        link = state.get("link") or {}
        if not (state.get("map") or link):
            return None
        if live:
            last_scan = state.get("last_scan_at") or 0
            last_link = link.get("updated_ms", 0) / 1000.0
            if not (0 <= now - state["written_at"] < 6 and
                    (0 <= now - last_scan < 6 or 0 <= now - last_link < 6)):
                return None
        return data
    except (OSError, ValueError, KeyError, TypeError):
        return None


class Server(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        route = urlsplit(self.path).path
        if route in STATIC:
            filename, content_type = STATIC[route]
            return self.reply(200, content_type, (ROOT / filename).read_bytes())
        if route == "/api/status":
            data = {"live": snapshot(ROOT / "live.json", live=True) is not None,
                    "recorded": snapshot(ROOT / "recording.json") is not None}
            return self.reply(200, "application/json", json.dumps(data).encode("utf-8"))
        if route in ("/api/live", "/api/recorded"):
            live = route == "/api/live"
            data = snapshot(ROOT / ("live.json" if live else "recording.json"), live=live)
            return self.reply(200, "application/json", data or b"null")
        if route == "/api/watch":
            try:
                data = (ROOT / "watch.json").read_bytes()
            except OSError:
                data = b"null"
            return self.reply(200, "application/json", data)
        return self.reply(404, "text/plain", b"Not found")

    def reply(self, status, content_type, data):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, _format, *_args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    with Server(("127.0.0.1", args.port), Handler) as server:
        print("SLAM display at http://127.0.0.1:%d" % args.port, flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
