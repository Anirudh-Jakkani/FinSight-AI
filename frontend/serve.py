"""Local dev server for the FinSight AI frontend (Phase 6.1).

Why this exists: the FastAPI backend has no CORS middleware (and per this task's
"no backend changes" instruction, none was added). A static page served from any
other origin — a different port, or opened via file:// — would have every fetch()
call to the API silently blocked by the browser's CORS policy, no matter how the
page itself is written. This script sidesteps that without touching any backend
file: it serves the static frontend AND transparently forwards /api/* and /health*
requests to the real FastAPI server, so the browser sees exactly one origin and
CORS never enters the picture. The backend itself (backend/app/*) is untouched —
this is a dev-convenience script that lives entirely in frontend/.

Usage:
    1. Start the real backend as usual: uvicorn app.main:app --reload (port 8000)
    2. python frontend/serve.py
    3. Open http://127.0.0.1:5500
"""
from __future__ import annotations

import http.server
import socketserver
import urllib.error
import urllib.request
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parent
BACKEND_URL = "http://127.0.0.1:8000"
PORT = 5500
PROXY_PREFIXES = ("/api/", "/health")
HOP_BY_HOP_HEADERS = {"host", "content-length", "transfer-encoding", "connection"}


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def _is_proxied(self) -> bool:
        return self.path.startswith(PROXY_PREFIXES)

    def _proxy(self, method: str) -> None:
        url = BACKEND_URL + self.path
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_BY_HOP_HEADERS}

        request = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                self._relay(response.status, response.headers.items(), response.read())
        except urllib.error.HTTPError as exc:
            self._relay(exc.code, exc.headers.items() if exc.headers else [], exc.read())
        except urllib.error.URLError:
            body_bytes = (
                b'{"detail": "Cannot reach the FinSight API at %s. '
                b'Is uvicorn running?"}' % BACKEND_URL.encode()
            )
            self._relay(502, [("Content-Type", "application/json")], body_bytes)

    def _relay(self, status: int, headers, body: bytes) -> None:
        self.send_response(status)
        for key, value in headers:
            if key.lower() in HOP_BY_HOP_HEADERS:
                continue
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._proxy("GET") if self._is_proxied() else super().do_GET()

    def do_POST(self):
        self._proxy("POST")

    def do_PATCH(self):
        self._proxy("PATCH")

    def do_DELETE(self):
        self._proxy("DELETE")

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        pass


if __name__ == "__main__":
    with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), Handler) as httpd:
        print(f"FinSight AI frontend:  http://127.0.0.1:{PORT}")
        print(f"Proxying /api/* and /health* -> {BACKEND_URL}")
        httpd.serve_forever()
