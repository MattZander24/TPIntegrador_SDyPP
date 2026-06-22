"""Servidor HTTP de administración para el worker.

Expone endpoints para hot-switch de modo (pool-miner ↔ standalone ↔ rabbitmq)
sin reiniciar el contenedor.
"""

from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from common.health import json_response

log = logging.getLogger("voxchain.worker.admin")


class AdminHTTPHandler(BaseHTTPRequestHandler):
    manager = None

    def log_message(self, fmt, *args):
        log.debug(fmt, *args)

    def _send_json(self, data, status=200):
        json_response(self, data, status)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/status":
            ctx = self.manager.get_status()
            return self._send_json({
                "mode": ctx["mode"],
                "worker_id": ctx["worker_id"],
                "pool_url": ctx.get("pool_url", ""),
                "rejected_actions": ctx.get("rejected_actions", ""),
                "running": ctx["running"],
            })
        self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return self._send_json({"error": "invalid json"}, 400)

        if parsed.path == "/switch-mode":
            target = payload.get("target", "")
            pool_url = payload.get("pool_url", "")
            rejected_actions = payload.get("rejected_actions", "")
            try:
                result = self.manager.switch_mode(target, pool_url)
                return self._send_json(result)
            except ValueError as e:
                return self._send_json({"error": str(e)}, 400)

        self._send_json({"error": "not found"}, 404)


def start_admin_server(manager, port: int = 9090) -> HTTPServer:
    AdminHTTPHandler.manager = manager
    server = HTTPServer(("0.0.0.0", port), AdminHTTPHandler)
    log.info("admin server escuchando en puerto %d", port)
    return server
