"""Punto de entrada del NCT: cablea Redis + RabbitMQ, health endpoint y loop.

Ejecutar: ``python main.py`` (dentro del contenedor). Toda la configuración
proviene de variables de entorno (ver common/config.py); no hay secretos en el
código.
"""

from __future__ import annotations

from common import config
from common.health import start_health_server
from common.logging_setup import setup_logging
from common.messaging import build_rabbitmq
from common.storage import VoxChainStore, connect_redis
from nct.coordinator import NCTCoordinator


def main() -> None:
    log = setup_logging("nct")
    log.info("iniciando NCT (n_zeros=%d)", config.N_ZEROS)

    store = VoxChainStore(connect_redis(config.REDIS_URL))
    messaging = build_rabbitmq(config.RABBITMQ_URL)
    messaging.connect()

    nct = NCTCoordinator(
        messaging, store,
        n_zeros=config.N_ZEROS,
        window_seconds_promulgacion=config.WINDOW_SECONDS_PROMULGACION,
        window_seconds_derogacion=config.WINDOW_SECONDS_DEROGACION,
        cooldown_new=config.COOLDOWN_WINDOWS_NEW,
        cooldown_reproposed=config.COOLDOWN_WINDOWS_REPROPOSED,
    )
    nct.wire()

    def health() -> dict:
        return {
            "nct": "ok",
            "redis": "ok" if store.ping() else "down",
            "rabbitmq": "ok" if messaging.is_healthy() else "down",
        }

    start_health_server(config.HEALTH_PORT, health)
    log.info("health en :%d/health — consumiendo propuestas y respuestas",
             config.HEALTH_PORT)

    try:
        messaging.start_consuming(tick=nct.tick, tick_interval=1.0)
    finally:
        messaging.close()


if __name__ == "__main__":
    main()
