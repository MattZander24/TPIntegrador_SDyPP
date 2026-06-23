"""Punto de entrada del worker minero.

Modos:
  - ``standalone``: se suscribe al desafío activo del NCT, mina espacio completo.
  - ``pool-coordinator``: fragmenta espacio de nonces, acepta workers HTTP, auto-mina.
  - ``pool-worker``: se conecta a un Pool Coordinator vía HTTP.
  - ``pool-auto``: modo pool con bully election. Compite con otros workers vía
    RabbitMQ; el ganador actúa como coordinator, los demás como miners.

Hot-switch entre modos vía POST /switch-mode en puerto admin (9090).
"""

from __future__ import annotations

import logging
import os
import signal
import socket
import threading

from common import config
from common.health import start_health_server
from common.logging_setup import setup_logging
from common.messaging import build_rabbitmq
from common.redis import create_redis
from worker_pkg.admin_server import start_admin_server
from worker_pkg.identity import WorkerSigner
from worker_pkg.miner import _gpu_available, run_miner
from worker_pkg.pool_worker import PoolWorker
from worker_pkg.pool_coordinator import PoolCoordinator
from worker_pkg.standalone_worker import StandaloneWorker
from worker_pkg.bully import PoolBully

log = logging.getLogger("voxchain.worker")


class WorkerManager:
    """Gestiona el worker activo y permite hot-switch entre modos."""

    def __init__(self, worker_id: str, has_gpu: bool, signer=None):
        self.worker_id = worker_id
        self.has_gpu = has_gpu
        self.signer = signer
        self._messaging = None
        self._worker = None
        self._thread = None
        self._mode = "idle"
        self._pool_url = ""
        self._pool_httpd = None
        self._stop_event = threading.Event()
        self._pool_http_port = int(os.getenv("POOL_HTTP_PORT", "9001"))
        self._bully = None
        self._report_thread = None

    # -- API pública para admin_server --

    def get_status(self) -> dict:
        pool_url = self._pool_url
        if self._mode == "pool-coordinator":
            pool_url = f"http://{self.worker_id}:{self._pool_http_port}"
        bully_state = self._bully.state if self._bully else None
        return {
            "mode": self._mode,
            "worker_id": self.worker_id,
            "pool_url": pool_url,
            "bully_state": bully_state,
            "running": self._thread is not None and self._thread.is_alive(),
        }

    def switch_mode(self, target: str, pool_url: str = "") -> dict:
        if target not in ("pool-worker", "standalone", "pool-coordinator", "pool-auto"):
            raise ValueError(f"modo desconocido: {target}")
        if target == "pool-worker" and not pool_url:
            raise ValueError("pool_url requerido para modo pool-worker")
        log.info("switching mode: %s → %s", self._mode, target)
        self._stop_current()
        if target == "pool-worker":
            self._start_pool_worker(pool_url)
        elif target == "standalone":
            self._start_standalone()
        elif target == "pool-coordinator":
            self._start_pool_coordinator()
        elif target == "pool-auto":
            self._start_pool_auto()
        log.info("modo activo: %s", self._mode)
        return {"ok": True, "mode": self._mode, "pool_url": self._pool_url}

    def _redis_report_loop(self) -> None:
        redis_client = None
        try:
            from common.redis import create_redis
            redis_client = create_redis(config.REDIS_URL)
        except Exception:
            log.warning("No se pudo inicializar cliente de Redis para reporte de estado")

        while not self._stop_event.is_set():
            if redis_client:
                try:
                    status = self.get_status()
                    import json
                    redis_client.set(f"worker:status:{self.worker_id}", json.dumps(status), ex=15)
                except Exception:
                    log.debug("No se pudo escribir estado en Redis", exc_info=True)
            self._stop_event.wait(5.0)

    def start(self, mode: str, pool_url: str = "") -> None:
        self.switch_mode(mode, pool_url)
        if self._report_thread is None:
            self._report_thread = threading.Thread(target=self._redis_report_loop, daemon=True)
            self._report_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._stop_current()
        if self._report_thread:
            self._report_thread.join(timeout=5)
            self._report_thread = None

    # -- interno --

    # -- ConfigMap worker-modes (persistencia de modo entre reinicios) --

    @staticmethod
    def _read_mode_from_configmap(worker_id: str) -> str | None:
        try:
            from kubernetes import config, client
            try:
                config.load_incluster_config()
            except config.ConfigException:
                return None
            v1 = client.CoreV1Api()
            ns = open("/var/run/secrets/kubernetes.io/serviceaccount/namespace").read().strip()
            cm = v1.read_namespaced_config_map("worker-modes", ns)
            return cm.data.get(worker_id)
        except Exception:
            log.debug("no se pudo leer worker-modes ConfigMap", exc_info=True)
            return None

    # -- comandos remotos (RabbitMQ worker.command) --

    def _subscribe_worker_commands(self, messaging) -> None:
        messaging.on_worker_command(self.worker_id, self._handle_command)

    def _handle_command(self, msg: dict) -> None:
        cmd = msg.get("type", "")
        if cmd == "switch_mode":
            target = msg.get("mode", "")
            if target in ("standalone", "pool-worker", "pool-auto", "pool-coordinator"):
                log.info("comando remoto: switch_mode → %s", target)
                pool_url = msg.get("pool_url", "")
                self.switch_mode(target, pool_url)
        elif cmd == "stop":
            log.info("comando remoto: stop")
            self.stop()

    def _stop_current(self) -> None:
        if self._worker:
            self._worker.stop()
            self._worker = None
        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None
        if self._pool_httpd:
            self._pool_httpd.shutdown()
            self._pool_httpd = None
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

    def _run_messaging_loop(self, tick=None):
        try:
            self._messaging.start_consuming(tick=tick, tick_interval=1.0)
        except Exception:
            if not self._stop_event.is_set():
                raise

    def _start_pool_worker(self, pool_url: str) -> None:
        self._mode = "pool-worker"
        self._pool_url = pool_url
        m = self._ensure_messaging()
        self._subscribe_worker_commands(m)
        pw = PoolWorker(
            pool_url,
            miner_id=self.worker_id,
            capacity=config.get_int("WORKER_CAPACITY", 1),
            has_gpu=self.has_gpu,
            mine=run_miner,
        )
        self._worker = pw
        self._thread = threading.Thread(target=pw.run, daemon=True)
        self._thread.start()

    def _start_standalone(self) -> None:
        self._mode = "standalone"
        m = self._ensure_messaging()
        self._subscribe_worker_commands(m)
        sw = StandaloneWorker(
            m,
            worker_id=self.worker_id,
            mine=run_miner,
            signer=self.signer,
        )
        sw.wire()
        self._worker = sw
        self._thread = threading.Thread(
            target=self._run_messaging_loop, daemon=True
        )
        self._thread.start()

    def _start_pool_coordinator(self) -> None:
        self._mode = "pool-coordinator"
        m = self._ensure_messaging()
        self._subscribe_worker_commands(m)
        redis = create_redis(config.REDIS_URL)
        pc = PoolCoordinator(
            m,
            pool_id=self.worker_id,
            redis=redis,
            mine=run_miner,
            capacity=config.get_int("WORKER_CAPACITY", 1),
            signer=self.signer,
        )
        pc.wire()
        pc.start()
        self._worker = pc

        from worker_pkg.pool_coordinator.server import start_pool_http_server
        self._pool_httpd = start_pool_http_server(
            pc, port=config.get_int("POOL_HTTP_PORT", 9001)
        )
        pool_http_thread = threading.Thread(
            target=self._pool_httpd.serve_forever, daemon=True
        )
        pool_http_thread.start()

        self._thread = threading.Thread(
            target=self._run_messaging_loop, args=(pc.tick,), daemon=True
        )
        self._thread.start()

        log.info("pool-coordinator %s iniciado en puerto %d",
                 self.worker_id, config.get_int("POOL_HTTP_PORT", 9001))

    def _start_pool_auto(self) -> None:
        self._mode = "pool-auto"
        m = self._ensure_messaging()
        self._subscribe_worker_commands(m)
        pool_id = os.getenv("POOL_ID", "default")
        address = os.getenv("WORKER_ADDRESS",
                            f"http://{socket.gethostname()}:{self._pool_http_port}")

        bully = PoolBully(
            self.worker_id,
            pool_id,
            m,
            has_gpu=self.has_gpu,
            capacity=config.get_int("WORKER_CAPACITY", 1),
            address=address,
            signer=self.signer,
        )
        bully.wire()
        self._bully = bully

        self._thread = threading.Thread(
            target=self._run_messaging_loop, args=(bully.tick,), daemon=True
        )
        self._thread.start()

        log.info("pool-auto %s iniciado (pool=%s, address=%s)",
                 self.worker_id, pool_id, address)


def main() -> None:
    signal.signal(signal.SIGTERM, lambda *_: None)
    setup_logging("worker")
    worker_id = os.getenv("WORKER_ID", f"worker-{socket.gethostname()}")
    has_gpu = _gpu_available(os.getenv("MINER_GPU_BIN", ""))

    # Leer modo desde ConfigMap (persistencia), fallback a env var
    mode = WorkerManager._read_mode_from_configmap(worker_id) or os.getenv("WORKER_MODE", "standalone")
    pool_url = os.getenv("POOL_COORDINATOR_URL", "")
    log.info("iniciando %s modo=%s (gpu=%s)", worker_id, mode, has_gpu)

    signer = WorkerSigner.from_env()
    if mode == "pool-auto":
        pool_url = os.getenv("POOL_COORDINATOR_URL",
                             f"http://{worker_id}:{int(os.getenv('POOL_HTTP_PORT', '9001'))}")
    manager = WorkerManager(worker_id, has_gpu, signer=signer)
    manager.start(mode, pool_url)

    admin_port = int(os.getenv("ADMIN_PORT", "9090"))
    httpd = start_admin_server(manager, port=admin_port)
    admin_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    admin_thread.start()

    start_health_server(config.HEALTH_PORT, lambda: {
        "status": "ok",
    })

    signal.pause()
    log.info("deteniendo worker...")
    manager.stop()
    httpd.shutdown()


if __name__ == "__main__":
    main()
