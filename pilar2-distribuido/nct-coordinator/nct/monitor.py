"""Monitor de heartbeats del NCT y disparador de elección (AGENT.md 4).

Corre en los NCT standby. Se suscribe a ``nct.heartbeat`` (topic exchange) y
trackea la frescura del heartbeat del líder. Si no recibe heartbeat durante
``heartbeat_timeout`` segundos, dispara una elección distribuida via
``run_distributed_election``.
"""

from __future__ import annotations

import logging
import time

from common.blockchain.challenge import verify_nonce
from nct.bully import run_distributed_election

log = logging.getLogger("voxchain.nct.monitor")


class NCTHeartbeatMonitor:
    """Monitorea heartbeats del NCT activo y dispara elección si es necesario."""

    def __init__(self, messaging, store, *, candidate_id: str,
                 election_n_zeros: int, heartbeat_timeout: float,
                 clock=time.time, on_elected=None):
        self.m = messaging
        self.store = store
        self.candidate_id = candidate_id
        self.election_n_zeros = election_n_zeros
        self.heartbeat_timeout = heartbeat_timeout
        self.now = clock
        # Callback que se ejecuta cuando este nodo gana la elección. Es lo que
        # promueve al NCTCoordinator a líder (abriendo sus colas de trabajo).
        self.on_elected = on_elected

        self._last_heartbeat = 0.0
        self._election_in_progress = False
        self._is_leader = False
        self._last_claim = None

    def wire(self) -> None:
        # Un follower consume ``nct.heartbeat`` y ``nct_election`` (y NO las colas
        # de trabajo del NCT, gating del BUG 1). Escuchar la cola de elección
        # desde el arranque deja al standby suscrito a ``nct_election``.
        self.m.on_heartbeat(self.handle_heartbeat)
        self.m.on_election_claim(self.handle_election_claim)

    def handle_heartbeat(self, hb: dict) -> None:
        self._last_heartbeat = self.now()
        nct_id = hb.get("nct_id", "desconocido")
        log.debug("heartbeat recibido de %s", nct_id[:12])

    def handle_election_claim(self, claim: dict) -> None:
        # Registro pasivo de claims de otros candidatos (observabilidad). El
        # backoff fino lo maneja run_distributed_election durante la elección.
        self._last_claim = claim

    @property
    def leader_alive(self) -> bool:
        if self._last_heartbeat == 0.0:
            return False
        return (self.now() - self._last_heartbeat) < self.heartbeat_timeout

    def tick(self) -> None:
        if self._is_leader or self._election_in_progress:
            return
        if self._last_heartbeat == 0.0:
            return
        if self.leader_alive:
            return

        log.warning("heartbeat timeout (%.1fs sin heartbeat), iniciando elección",
                     self.now() - self._last_heartbeat)
        self._election_in_progress = True

        # El seed de la elección es el hash del último bloque (determinístico).
        last_hash = self.store.last_block_hash()
        seed = f"{last_hash}::election-{self.now()}"

        won = run_distributed_election(
            seed=seed,
            n_zeros=self.election_n_zeros,
            candidate_id=self.candidate_id,
            messaging=self.m,
            store=self.store,
            clock=self.now,
        )

        if won:
            self._is_leader = True
            # Promover el coordinator: abre sus colas de trabajo y asume el rol.
            if self.on_elected is not None:
                self.on_elected()
        self._election_in_progress = False
