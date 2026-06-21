"""Punto de entrada del worker minero.

Modos:
  - ``rabbitmq`` (default): consume rangos del TrP vía RabbitMQ.
  - ``pool-miner``: se conecta al Pool Coordinator vía HTTP.
"""

from __future__ import annotations

import os
import signal
import socket

from common import config
from common.health import start_health_server
from common.logging_setup import setup_logging
from worker_pkg.miner import _gpu_available, run_miner
from worker_pkg.pool_miner import PoolMiner
from worker_pkg.worker import Worker


def main() -> None:
    signal.signal(signal.SIGTERM, signal.getsignal(signal.SIGINT))
    mode = os.getenv("WORKER_MODE", "rabbitmq")
    log = setup_logging("worker")
    worker_id = os.getenv("WORKER_ID", f"worker-{socket.gethostname()}")
    has_gpu = _gpu_available(os.getenv("MINER_GPU_BIN", ""))
    log.info("iniciando %s modo=%s (gpu=%s)", worker_id, mode, has_gpu)

    if mode == "pool-miner":
        _run_pool_miner(worker_id, has_gpu, log)
    else:
        _run_rabbitmq_worker(worker_id, has_gpu, log)


def _run_rabbitmq_worker(worker_id: str, has_gpu: bool, log) -> None:
    from common.messaging import build_rabbitmq

    messaging = build_rabbitmq(config.RABBITMQ_URL)
    messaging.connect()

    worker = Worker(messaging, worker_id=worker_id, mine=run_miner,
                    capacity=config.get_int("WORKER_CAPACITY", 1), has_gpu=has_gpu)
    worker.wire()

    start_health_server(config.HEALTH_PORT, lambda: {
        "worker": "ok",
        "rabbitmq": "ok" if messaging.is_healthy() else "down",
    })

    try:
        messaging.start_consuming(tick=worker.tick, tick_interval=1.0)
    finally:
        messaging.close()


def _run_pool_miner(worker_id: str, has_gpu: bool, log) -> None:
    start_health_server(config.HEALTH_PORT, lambda: {
        "miner": "ok",
        "mode": "pool-miner",
    })

    miner = PoolMiner(
        config.POOL_COORDINATOR_URL,
        miner_id=worker_id,
        capacity=config.get_int("WORKER_CAPACITY", 1),
        has_gpu=has_gpu,
        mine=run_miner,
    )

    try:
        miner.run()
    except KeyboardInterrupt:
        log.info("pool-miner detenido")


if __name__ == "__main__":
    main()
