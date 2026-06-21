"""Punto de entrada del Pool Coordinator."""

from __future__ import annotations

from common import config
from common.health import start_health_server
from common.logging_setup import setup_logging
from common.messaging import build_rabbitmq
from common.redis import create_redis
from pool_coordinator import PoolCoordinator
from pool_coordinator.server import start_pool_http_server


def main() -> None:
    log = setup_logging("pool-coordinator")
    log.info("iniciando Pool Coordinator")

    messaging = build_rabbitmq(config.RABBITMQ_URL)
    messaging.connect()

    redis = create_redis(config.REDIS_URL)

    coordinator = PoolCoordinator(
        messaging,
        pool_id=config.POOL_ID,
        redis=redis,
        capacity=config.POOL_CAPACITY,
        lease_ttl=config.LEADER_LEASE_TTL,
        lease_key="pool:leader",
    )
    coordinator.wire()

    httpd = start_pool_http_server(coordinator, port=config.POOL_HTTP_PORT)

    start_health_server(config.HEALTH_PORT, lambda: {
        "pool": "ok",
        "rabbitmq": "ok" if messaging.is_healthy() else "down",
        "redis": "ok",
    })

    try:
        import threading
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        messaging.start_consuming(tick=coordinator.tick, tick_interval=1.0)
    finally:
        httpd.shutdown()
        messaging.close()


if __name__ == "__main__":
    main()