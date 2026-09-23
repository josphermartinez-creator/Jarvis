#!/usr/bin/env python3
"""Serve just the player and video, with byte ranges for mobile playback.

The rest of the repository (including .git) is never exposed over HTTP.
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
ROUTES = {
    "/": ("web/stickmen.html", "text/html; charset=utf-8"),
    "/index.html": ("web/stickmen.html", "text/html; charset=utf-8"),
    "/palitos": ("web/stickmen.html", "text/html; charset=utf-8"),
    "/stickmen": ("web/stickmen.html", "text/html; charset=utf-8"),
    "/stickmen/video.mp4": ("exports/palitos-artes-marciales.mp4", "video/mp4"),
    "/stickmen/download": ("exports/palitos-artes-marciales.mp4", "video/mp4"),
    "/stickmen/poster.jpg": ("exports/palitos-artes-marciales.jpg", "image/jpeg"),
    "/jirafa": ("web/giraffe.html", "text/html; charset=utf-8"),
    "/giraffe/video.mp4": ("exports/jirafa-bebe.mp4", "video/mp4"),
    "/giraffe/download": ("exports/jirafa-bebe.mp4", "video/mp4"),
    "/giraffe/poster.jpg": ("exports/jirafa-bebe.jpg", "image/jpeg"),
    "/pollito": ("web/chick.html", "text/html; charset=utf-8"),
    "/chick/video.mp4": ("exports/pollito-comiendo.mp4", "video/mp4"),
    "/chick/download": ("exports/pollito-comiendo.mp4", "video/mp4"),
    "/chick/poster.jpg": ("exports/pollito-comiendo.jpg", "image/jpeg"),
    "/hipopotamo": ("web/hippo.html", "text/html; charset=utf-8"),
    "/hippo/video.mp4": ("exports/hipopotamo-bebe.mp4", "video/mp4"),
    "/hippo/download": ("exports/hipopotamo-bebe.mp4", "video/mp4"),
    "/hippo/poster.jpg": ("exports/hipopotamo-bebe.jpg", "image/jpeg"),
    "/universo": ("web/index.html", "text/html; charset=utf-8"),
    "/video.mp4": ("exports/viaje-infinito.mp4", "video/mp4"),
    "/download": ("exports/viaje-infinito.mp4", "video/mp4"),
    "/poster.jpg": ("exports/viaje-infinito.jpg", "image/jpeg"),
}


class VideoHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.serve(body=False)

    def do_GET(self):
        self.serve(body=True)

    def serve(self, body=True):
        route = urlsplit(self.path).path
        entry = ROUTES.get(route)
        if not entry:
            self.send_error(404)
            return
        relative, media_type = entry
        path = ROOT / relative
        if not path.is_file():
            self.send_error(404, "El video no esta disponible todavia")
            return
        size = path.stat().st_size
        start, end = 0, size - 1
        range_header = self.headers.get("Range")
        if range_header:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
            try:
                if not match or not any(match.groups()):
                    raise ValueError
                first, last = match.groups()
                if first:
                    start = int(first)
                    end = min(int(last), size - 1) if last else size - 1
                else:
                    length = int(last)
                    if length <= 0:
                        raise ValueError
                    start = max(0, size - length)
                if start < 0 or start > end or start >= size:
                    raise ValueError
            except ValueError:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
        self.send_response(206 if range_header else 200)
        self.send_header("Content-Type", media_type)
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-cache" if media_type.startswith("text/") else "public, max-age=3600")
        if range_header:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if route == "/download" or route.endswith("/download"):
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.end_headers()
        if not body:
            return
        try:
            with path.open("rb") as source:
                source.seek(start)
                remaining = end - start + 1
                while remaining:
                    chunk = source.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Normal when the player changes its requested byte range.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("0.0.0.0", args.port), VideoHandler)
    print(f"Video player ready on 0.0.0.0:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
