"""Punto de entrada del NCT: cablea Redis + RabbitMQ, health endpoint y loop.

Dos modos de operación:

- ``NCT_MODE=primary`` (default): publica heartbeats, procesa colas de propuestas
  y respuestas. Es el NCT activo.
- ``NCT_MODE=standby``: monitorea heartbeats del líder. Si el líder falla,
  dispara una elección distribuida y asume como líder si gana.

Ejecutar: ``python main.py`` (dentro del contenedor). Toda la configuración
proviene de variables de entorno (ver common/config.py).
"""

from __future__ import annotations

from common import config
from common.health import start_health_server
from common.logging_setup import setup_logging
from common.messaging import build_rabbitmq
from common.storage import VoxChainStore, connect_redis
from nct.coordinator import NCTCoordinator
from nct.monitor import NCTHeartbeatMonitor


def main() -> None:
    log = setup_logging("nct")
    mode = config.get("NCT_MODE", "primary")
    log.info("iniciando NCT (n_zeros=%d, mode=%s, nct_id=%s)",
             config.N_ZEROS, mode, config.NCT_ID)

    store = VoxChainStore(connect_redis(config.REDIS_URL))
    messaging = build_rabbitmq(config.RABBITMQ_URL)
    messaging.connect()

    is_primary = (mode == "primary")
    # El intervalo de heartbeat es el mismo para ambos modos; lo que decide si se
    # publican es `is_leader` (un standby promovido a líder empieza a emitirlos).
    nct = NCTCoordinator(
        messaging, store,
        n_zeros=config.N_ZEROS,
        window_seconds_promulgacion=config.WINDOW_SECONDS_PROMULGACION,
        window_seconds_derogacion=config.WINDOW_SECONDS_DEROGACION,
        cooldown_new=config.COOLDOWN_WINDOWS_NEW,
        cooldown_reproposed=config.COOLDOWN_WINDOWS_REPROPOSED,
        nct_id=config.NCT_ID,
        is_leader=is_primary,
        heartbeat_interval=config.HEARTBEAT_INTERVAL,
    )
    nct.wire()

    if not is_primary:
        monitor = NCTHeartbeatMonitor(
            messaging, store,
            candidate_id=config.NCT_ID,
            election_n_zeros=config.ELECTION_N_ZEROS,
            heartbeat_timeout=config.HEARTBEAT_TIMEOUT,
            on_elected=nct.become_leader,  # ganar la elección abre las colas de trabajo
        )
        monitor.wire()
        log.info("standby: monitoreando heartbeats (timeout=%ds, elección=%d ceros)",
                 config.HEARTBEAT_TIMEOUT, config.ELECTION_N_ZEROS)
    else:
        store.try_acquire_leadership(config.NCT_ID)
        monitor = None

    def health() -> dict:
        h = {
            "nct": "ok",
            "redis": "ok" if store.ping() else "down",
            "rabbitmq": "ok" if messaging.is_healthy() else "down",
            "mode": mode,
        }
        if not is_primary and monitor is not None:
            h["leader_alive"] = str(monitor.leader_alive)
            h["leader"] = store.get_leader() or "none"
        return h

    start_health_server(config.HEALTH_PORT, health)
    log.info("health en :%d/health", config.HEALTH_PORT)

    def composite_tick() -> None:
        nct.tick()
        if monitor is not None:
            monitor.tick()

    try:
        messaging.start_consuming(tick=composite_tick, tick_interval=1.0)
    finally:
        messaging.close()


if __name__ == "__main__":
    main()
