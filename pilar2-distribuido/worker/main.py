"""Punto de entrada del worker minero.

Consume rangos de nonces del TrP, mina invocando el minero de Pilar 1 (GPU o
fallback CPU) y publica el nonce ganador a ``respuesta_nonce``. Emite keep-alives
periódicos al TrP. Pensado para correr con ``replicas: 2`` en docker-compose.
"""

from __future__ import annotations

import os
import socket

from common import config
from common.health import start_health_server
from common.logging_setup import setup_logging
from common.messaging import build_rabbitmq
from worker_pkg.miner import _gpu_available, run_miner
from worker_pkg.worker import Worker


def main() -> None:
    log = setup_logging("worker")
    worker_id = os.getenv("WORKER_ID", f"worker-{socket.gethostname()}")
    has_gpu = _gpu_available(os.getenv("MINER_GPU_BIN", ""))
    log.info("iniciando %s (gpu=%s)", worker_id, has_gpu)

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


if __name__ == "__main__":
    main()
