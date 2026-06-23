"""Punto de entrada del NCT: cablea Redis + RabbitMQ, health endpoint y loop.

Dos identidades cosméticas (``NCT_MODE``):

- ``NCT_MODE=primary`` (default): intenta adquirir el lease al arrancar; si lo
  obtiene, es el líder inicial y publica heartbeats.
- ``NCT_MODE=standby``: arranca como follower y monitorea heartbeats.

**Todo nodo que no tenga el lease corre el monitor de heartbeats y participa
en la elección**, independientemente del modo inicial. El comportamiento se
decide por quién tiene el lease, no por el nombre del servicio. Si el primario
pierde el lease (step_down), su monitor se activa y puede promover al ganar la
siguiente elección.

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

    # Si arrancamos como primario, intentamos adquirir el lease. Si ya fue
    # tomado por otro nodo (p. ej. un standby que se promovió mientras este
    # contenedor reiniciaba), arrancamos como follower.
    if is_primary:
        acquired = store.try_acquire_leadership(config.NCT_ID,
                                                ttl=config.LEADER_LEASE_TTL)
        is_leader_now = acquired
        if not acquired:
            log.warning("primary %s no pudo adquirir el lease al arrancar "
                        "(otro nodo ya es líder); arrancando como follower",
                        config.NCT_ID)
    else:
        is_leader_now = False

    # El intervalo de heartbeat es el mismo para ambos modos; lo que decide si
    # se publican es `is_leader` (un follower promovido empieza a emitirlos).
    nct = NCTCoordinator(
        messaging, store,
        n_zeros=config.N_ZEROS,
        window_seconds_promulgacion=config.WINDOW_SECONDS_PROMULGACION,
        window_seconds_derogacion=config.WINDOW_SECONDS_DEROGACION,
        cooldown_new=config.COOLDOWN_WINDOWS_NEW,
        cooldown_reproposed=config.COOLDOWN_WINDOWS_REPROPOSED,
        nct_id=config.NCT_ID,
        is_leader=is_leader_now,
        heartbeat_interval=config.HEARTBEAT_INTERVAL,
        require_signatures=config.REQUIRE_SIGNATURES,
        proposal_max_age=config.PROPOSAL_MAX_AGE_SECONDS,
        # on_stepdown se conecta después de crear el monitor (ver abajo).
    )

    # El monitor vive en TODOS los nodos, no solo en el standby. Un nodo que
    # arranca como líder usa initial_is_leader=True para no disparar elección
    # de inmediato; cuando pierde el lease (step_down), su monitor se activa
    # via notify_stepdown y empieza a observar heartbeats del nuevo líder.
    monitor = NCTHeartbeatMonitor(
        messaging, store,
        candidate_id=config.NCT_ID,
        heartbeat_timeout=config.HEARTBEAT_TIMEOUT,
        on_elected=nct.become_leader,
        initial_is_leader=is_leader_now,
        lease_ttl=config.LEADER_LEASE_TTL,
        dead_threshold=config.LEADER_DEAD_THRESHOLD,
    )
    monitor.wire()

    # Conectar step_down → monitor.notify_stepdown: cuando el coordinator ceda
    # el liderazgo, el monitor empieza a observar heartbeats del nuevo líder.
    nct._on_stepdown = monitor.notify_stepdown
    nct.wire()

    if is_leader_now:
        log.info("arrancando como LÍDER (%s); monitor en standby hasta step_down",
                 config.NCT_ID)
    else:
        log.info("arrancando como FOLLOWER (%s); monitoreando heartbeats (timeout=%ds)",
                 config.NCT_ID, config.HEARTBEAT_TIMEOUT)

    def health() -> dict:
        return {
            "nct": "ok" if nct.is_leader else "standby",
            "redis": "ok" if store.ping() else "down",
            "rabbitmq": "ok" if messaging.is_healthy() else "down",
        }

    start_health_server(config.HEALTH_PORT, health)
    log.info("health en :%d/health", config.HEALTH_PORT)

    def composite_tick() -> None:
        nct.tick()
        monitor.tick()

    try:
        messaging.start_consuming(tick=composite_tick, tick_interval=1.0)
    finally:
        messaging.close()


if __name__ == "__main__":
    main()
