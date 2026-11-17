"""The feed: a small local web server (stdlib only).

    GET  /                      the feed page
    GET  /api/reels             every reel with its verdict
    POST /api/pick              {"id": ..., "pick": "want"|"tried"|"dismissed"|null}
    GET  /media/<id>/<file>     video, poster and frames (Range requests for seeking)
"""

import json
import mimetypes
import re
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path

from .store import PICKS, Store

_MEDIA = re.compile(r"^/media/([A-Za-z0-9_-]+)/((?:frames/)?[A-Za-z0-9_.-]+)$")


def reels_json(store: Store) -> list[dict]:
    out = []
    for meta in store.all():
        item = {k: meta.get(k) for k in (
            "id", "url", "author", "caption", "posted", "saved_at", "added", "status", "error",
            "kind", "video", "poster", "frames", "duration", "pick", "likes",
            "author_id", "collections", "quick")}
        item["verdict"] = store.verdict(meta["id"])
        out.append(item)
    return out


def page() -> bytes:
    return resources.files(__package__).joinpath("feed.html").read_bytes()


def make_handler(store: Store):
    class Handler(BaseHTTPRequestHandler):
        server_version = "reel-triage"

        def log_message(self, fmt, *args):  # quiet
            pass

        def _send(self, status, body: bytes, ctype: str, extra: dict | None = None):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, data, status=HTTPStatus.OK):
            self._send(status, json.dumps(data, ensure_ascii=False).encode(), "application/json")

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                return self._send(HTTPStatus.OK, page(), "text/html; charset=utf-8")
            if path == "/api/reels":
                return self._json(reels_json(store))
            match = _MEDIA.match(path)
            if match and store.exists(match.group(1)):
                return self._file(store.path(match.group(1)) / match.group(2))
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

        def do_POST(self):
            if self.path != "/api/pick":
                return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                code, pick = body.get("id"), body.get("pick")
                if not isinstance(code, str) or not store.exists(code):
                    raise ValueError("unknown reel")
                if pick not in PICKS and pick is not None:
                    raise ValueError("bad pick")
            except (ValueError, json.JSONDecodeError) as e:
                return self._json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
            store.set_pick(code, pick)
            self._json({"ok": True, "id": code, "pick": pick})

        def _file(self, f: Path):
            if not f.is_file() or ".." in f.parts:
                return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            size = f.stat().st_size
            ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            rng = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range") or "")
            if rng and (rng.group(1) or rng.group(2)):
                if rng.group(1):
                    start = int(rng.group(1))
                    end = int(rng.group(2)) if rng.group(2) else size - 1
                else:  # suffix range: last N bytes
                    start, end = max(0, size - int(rng.group(2))), size - 1
                end = min(end, size - 1)
                if start > end:
                    return self._send(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE, b"", ctype,
                                      {"Content-Range": f"bytes */{size}"})
                with f.open("rb") as fh:
                    fh.seek(start)
                    body = fh.read(end - start + 1)
                return self._send(HTTPStatus.PARTIAL_CONTENT, body, ctype, {
                    "Content-Range": f"bytes {start}-{end}/{size}", "Accept-Ranges": "bytes"})
            self._send(HTTPStatus.OK, f.read_bytes(), ctype, {"Accept-Ranges": "bytes"})

    return Handler


def make_server(store: Store, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(store))


def serve(store: Store, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    httpd = make_server(store, host, port)
    url = f"http://{host}:{httpd.server_port}/"
    print(f"Feed: {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
