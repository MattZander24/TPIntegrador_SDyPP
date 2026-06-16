"""Endpoint de salud HTTP mínimo por servicio (DOC.md: health JSON, sin GUI).

Levanta un servidor ``http.server`` en un hilo daemon que responde en ``/health``
(y ``/``) con un JSON ``{servicio: status}`` calculado por un callback. Devuelve
200 si todos los componentes están ``ok``, 503 si alguno no.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable


def start_health_server(port: int, status_provider: Callable[[], dict]) -> ThreadingHTTPServer:
    """Arranca el server en un hilo daemon y devuelve la instancia."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path not in ("/health", "/", "/healthz"):
                self.send_response(404)
                self.end_headers()
                return
            status = status_provider()
            all_ok = all(v == "ok" for v in status.values())
            body = json.dumps(status).encode()
            self.send_response(200 if all_ok else 503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # silenciar logs de acceso
            pass

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
