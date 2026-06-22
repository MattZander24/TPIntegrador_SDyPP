"""Punto de entrada del worker minero.

Modos:
  - ``rabbitmq`` (default): consume rangos del TrP vía RabbitMQ.
  - ``standalone``: se suscribe al desafío activo del NCT, mina espacio completo.
  - ``pool-miner``: se conecta al Pool Coordinator vía HTTP.

Hot-switch entre modos vía POST /switch-mode en puerto admin (9090).
"""

from __future__ import annotations

import os
import signal
import socket
import threading

from common import config
from common.health import start_health_server
from common.logging_setup import setup_logging
from common.messaging import build_rabbitmq
from worker_pkg.admin_server import start_admin_server
from worker_pkg.miner import _gpu_available, run_miner
from worker_pkg.pool_miner import PoolMiner
from worker_pkg.standalone_worker import StandaloneWorker
from worker_pkg.worker import Worker


class WorkerManager:
    """Gestiona el worker activo y permite hot-switch entre modos."""

    def __init__(self, worker_id: str, has_gpu: bool):
        self.worker_id = worker_id
        self.has_gpu = has_gpu
        self._messaging = None
        self._worker = None
        self._thread = None
        self._mode = "idle"
        self._pool_url = ""
        self._stop_event = threading.Event()

    # -- API pública para admin_server --

    def get_status(self) -> dict:
        return {
            "mode": self._mode,
            "worker_id": self.worker_id,
            "pool_url": self._pool_url,
            "running": self._thread is not None and self._thread.is_alive(),
        }

    def switch_mode(self, target: str, pool_url: str = "") -> dict:
        if target not in ("pool-miner", "standalone", "rabbitmq"):
            raise ValueError(f"modo desconocido: {target}")
        if target == "pool-miner" and not pool_url:
            raise ValueError("pool_url requerido para modo pool-miner")
        log.info("switching mode: %s → %s", self._mode, target)
        self._stop_current()
        if target == "pool-miner":
            self._start_pool_miner(pool_url)
        elif target == "standalone":
            self._start_standalone()
        elif target == "rabbitmq":
            self._start_rabbitmq()
        log.info("modo activo: %s", self._mode)
        return {"ok": True, "mode": self._mode, "pool_url": self._pool_url}

    def start(self, mode: str, pool_url: str = "") -> None:
        self.switch_mode(mode, pool_url)

    def stop(self) -> None:
        self._stop_event.set()
        self._stop_current()

    # -- interno --

    def _stop_current(self) -> None:
        if self._worker:
            self._worker.stop()
            self._worker = None
        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None
        if self._messaging:
            self._messaging.close()
            self._messaging = None
        self._mode = "idle"

    def _ensure_messaging(self):
        if self._messaging is None:
            m = build_rabbitmq(config.RABBITMQ_URL)
            m.connect()
            self._messaging = m
        return self._messaging

    def _run_messaging_loop(self):
        try:
            self._messaging.start_consuming(tick_interval=1.0)
        except Exception:
            if not self._stop_event.is_set():
                raise

    def _start_pool_miner(self, pool_url: str) -> None:
        self._mode = "pool-miner"
        self._pool_url = pool_url
        miner = PoolMiner(
            pool_url,
            miner_id=self.worker_id,
            capacity=config.get_int("WORKER_CAPACITY", 1),
            has_gpu=self.has_gpu,
            mine=run_miner,
        )
        self._worker = miner
        self._thread = threading.Thread(target=miner.run, daemon=True)
        self._thread.start()

    def _start_standalone(self) -> None:
        self._mode = "standalone"
        m = self._ensure_messaging()
        sw = StandaloneWorker(
            m,
            worker_id=self.worker_id,
            mine=run_miner,
        )
        sw.wire()
        self._worker = sw
        self._thread = threading.Thread(
            target=self._run_messaging_loop, daemon=True
        )
        self._thread.start()

    def _start_rabbitmq(self) -> None:
        self._mode = "rabbitmq"
        m = self._ensure_messaging()
        w = Worker(
            m,
            worker_id=self.worker_id,
            mine=run_miner,
            capacity=config.get_int("WORKER_CAPACITY", 1),
            has_gpu=self.has_gpu,
        )
        w.wire()
        self._worker = w
        self._thread = threading.Thread(
            target=self._run_messaging_loop, daemon=True
        )
        self._thread.start()


def main() -> None:
    signal.signal(signal.SIGTERM, lambda *_: None)
    log = setup_logging("worker")
    worker_id = os.getenv("WORKER_ID", f"worker-{socket.gethostname()}")
    has_gpu = _gpu_available(os.getenv("MINER_GPU_BIN", ""))
    mode = os.getenv("WORKER_MODE", "rabbitmq")
    pool_url = os.getenv("POOL_COORDINATOR_URL", "")
    log.info("iniciando %s modo=%s (gpu=%s)", worker_id, mode, has_gpu)

    manager = WorkerManager(worker_id, has_gpu)
    manager.start(mode, pool_url)

    admin_port = int(os.getenv("ADMIN_PORT", "9090"))
    httpd = start_admin_server(manager, port=admin_port)
    admin_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    admin_thread.start()

    start_health_server(config.HEALTH_PORT, lambda: {
        "worker_id": worker_id,
        "mode": manager._mode,
        "status": "ok",
    })

    signal.pause()
    log.info("deteniendo worker...")
    manager.stop()
    httpd.shutdown()


if __name__ == "__main__":
    main()
