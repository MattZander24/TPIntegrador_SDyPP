"""Punto de entrada del Transaction Pool (TrP)."""

from __future__ import annotations

from common import config
from common.health import start_health_server
from common.logging_setup import setup_logging
from common.messaging import build_rabbitmq
from trp.pool import TransactionPool


def main() -> None:
    log = setup_logging("trp")
    log.info("iniciando TrP (nonce_space=%d, fragment_size=%d)",
             config.NONCE_SPACE, config.FRAGMENT_SIZE)

    messaging = build_rabbitmq(config.RABBITMQ_URL)
    messaging.connect()

    trp = TransactionPool(messaging, nonce_space=config.NONCE_SPACE,
                          fragment_size=config.FRAGMENT_SIZE)
    trp.wire()

    start_health_server(config.HEALTH_PORT, lambda: {
        "transaction_pool": "ok",
        "rabbitmq": "ok" if messaging.is_healthy() else "down",
    })

    try:
        messaging.start_consuming(tick=trp.tick, tick_interval=1.0)
    finally:
        messaging.close()


if __name__ == "__main__":
    main()
