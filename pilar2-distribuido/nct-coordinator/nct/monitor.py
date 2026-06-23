"""Monitor de heartbeats del NCT y disparador de failover (AGENT.md 4).

Corre en todo NCT que no sea líder. Se suscribe a ``nct.heartbeat`` (topic
exchange) y trackea la frescura del heartbeat del líder. Si no recibe heartbeat
durante ``heartbeat_timeout`` segundos, intenta adquirir el lease de liderazgo
directamente en Redis vía ``elect_acquire_leadership``.

No hay elección distribuida basada en PoW ni cola RabbitMQ de elección:
los NCT son nodos homogéneos en GCP, sin ventaja de cómputo entre ellos.
El arbitraje lo hace Redis atómicamente — quien llega primero tras el timeout
y tiene el TTL más bajo del lease gana, que es equivalente a quien detectó
la caída antes.
"""

from __future__ import annotations

import logging
import time

log = logging.getLogger("voxchain.nct.monitor")


class NCTHeartbeatMonitor:
    """Monitorea heartbeats del NCT activo y hace failover si es necesario.

    Cualquier nodo que no tenga el lease debe instanciar y cablear este monitor.
    Un nodo que arranca como líder pasa ``initial_is_leader=True`` para no
    disparar un failover de inmediato; cuando pierde el liderazgo
    (``step_down`` en el coordinator) llama a ``notify_stepdown()`` para
    activar el monitoreo.
    """

    def __init__(self, messaging, store, *, candidate_id: str,
                 heartbeat_timeout: float,
                 clock=time.time, on_elected=None,
                 initial_is_leader: bool = False,
                 lease_ttl: int = 20,
                 dead_threshold: int = 6):
        self.m = messaging
        self.store = store
        self.candidate_id = candidate_id
        self.heartbeat_timeout = heartbeat_timeout
        self.now = clock
        self.lease_ttl = lease_ttl
        self.dead_threshold = dead_threshold
        self.on_elected = on_elected

        self._last_heartbeat = 0.0
        self._election_in_progress = False
        self._is_leader = initial_is_leader

    def wire(self) -> None:
        self.m.on_heartbeat(self.handle_heartbeat)

    def handle_heartbeat(self, hb: dict) -> None:
        self._last_heartbeat = self.now()
        log.debug("heartbeat recibido de %s", hb.get("nct_id", "?")[:12])

    @property
    def leader_alive(self) -> bool:
        if self._last_heartbeat == 0.0:
            return False
        return (self.now() - self._last_heartbeat) < self.heartbeat_timeout

    def notify_stepdown(self) -> None:
        """El coordinator perdió el liderazgo; el monitor debe empezar a observar."""
        log.info("monitor activado tras step_down (%s): empezando a observar heartbeats",
                 self.candidate_id)
        self._is_leader = False
        self._last_heartbeat = 0.0
        self._election_in_progress = False

    def tick(self) -> None:
        if self._is_leader or self._election_in_progress:
            return
        if self._last_heartbeat == 0.0:
            return
        if self.leader_alive:
            return

        log.warning("heartbeat timeout (%.1fs sin heartbeat), intentando adquirir liderazgo",
                    self.now() - self._last_heartbeat)
        self._election_in_progress = True

        won = self.store.elect_acquire_leadership(
            self.candidate_id,
            ttl=self.lease_ttl,
            dead_threshold=self.dead_threshold,
        )

        if won:
            self._is_leader = True
            log.info("¡%s adquirió el liderazgo del NCT!", self.candidate_id)
            if self.on_elected is not None:
                self.on_elected()
        else:
            log.info("otro nodo adquirió el liderazgo primero")
        self._election_in_progress = False
