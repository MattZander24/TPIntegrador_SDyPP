"""Servidor HTTP para que los miners se registren y reciban trabajo."""

from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse
import threading

from common.health import json_response

log = logging.getLogger("voxchain.pool.server")


class PoolHTTPHandler(BaseHTTPRequestHandler):
    coordinator = None

    def log_message(self, fmt, *args):
        log.debug(fmt, *args)

    def _send_json(self, data, status=200):
        json_response(self, data, status)

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return self._send_json({"error": "invalid json"}, 400)

        if parsed.path == "/register":
            capacity = int(payload.get("capacity", 1))
            has_gpu = bool(payload.get("has_gpu", False))
            mid = self.coordinator.register_miner(capacity, has_gpu)
            return self._send_json({"miner_id": mid})

        elif parsed.path == "/heartbeat":
            mid = payload.get("miner_id", "")
            ok = self.coordinator.handle_heartbeat(mid)
            return self._send_json({"ok": ok})

        elif parsed.path == "/work/result":
            mid = payload.get("miner_id", "")
            result = payload.get("result", {})
            ok = self.coordinator.submit_result(mid, result)
            return self._send_json({"ok": ok})

        else:
            self._send_json({"error": "not found"}, 404)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/work/next/"):
            mid = parsed.path.split("/work/next/", 1)[-1]
            task = self.coordinator.get_next_task(mid)
            if task is None:
                return self._send_json(None, 204)
            return self._send_json(task)

        elif parsed.path == "/health":
            return self._send_json({
                "pool": "ok",
                "rabbitmq": "ok",
                "miners": len(self.coordinator._miners) if hasattr(self.coordinator, "_miners") else 0,
            })

        else:
            self._send_json({"error": "not found"}, 404)


def start_pool_http_server(coordinator, port: int = 9001) -> HTTPServer:
    PoolHTTPHandler.coordinator = coordinator
    server = HTTPServer(("0.0.0.0", port), PoolHTTPHandler)
    log.info("pool HTTP server escuchando en puerto %d", port)
    return server