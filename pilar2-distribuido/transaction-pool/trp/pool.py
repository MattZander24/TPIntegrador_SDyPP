"""Transaction Pool: recibe el desafío activo, fragmenta y reparte a los workers.

Suscrito a ``desafio_activo`` (flujo 2). Al recibir un desafío fragmenta el
espacio de nonces y publica cada tramo a ``tareas_trp`` (flujo interno TrP→worker).
Recibe keep-alives de los workers (``keepalive_trp``) para conocer la capacidad
disponible.

Decisión de diseño (AGENT.md 3 + 10): si no hay workers GPU, el TrP **loguea**
la necesidad de reducir complejidad / escalar mineros CPU, pero NO altera la
dificultad: ``n_zeros_required`` lo fija el NCT y el ajuste dinámico por carga de
red está prohibido. El autoescalado real es Pilar 3.
"""

from __future__ import annotations

import logging
import time

from .fragmentation import fragment_range

log = logging.getLogger("voxchain.trp")

# Ventana de frescura de un keep-alive: pasado este tiempo, el worker se
# considera ausente para el cálculo de capacidad.
KEEPALIVE_TTL = 15.0


class TransactionPool:
    def __init__(self, messaging, *, nonce_space: int, fragment_size: int,
                 clock=time.time):
        self.m = messaging
        self.nonce_space = nonce_space
        self.fragment_size = fragment_size
        self.now = clock
        self._workers: dict[str, dict] = {}

    def wire(self) -> None:
        self.m.on_challenge(self.handle_challenge)
        self.m.on_keepalive(self.handle_keepalive)

    # -- capacidad de los workers ------------------------------------------
    def handle_keepalive(self, ka: dict) -> None:
        wid = ka.get("worker_id")
        if not wid:
            return
        self._workers[wid] = {
            "capacity": int(ka.get("capacity", 1)),
            "has_gpu": bool(ka.get("has_gpu", False)),
            "last_seen": self.now(),
        }
        log.debug("keep-alive de %s (gpu=%s)", wid, self._workers[wid]["has_gpu"])

    def _fresh_workers(self) -> list[dict]:
        cutoff = self.now() - KEEPALIVE_TTL
        return [w for w in self._workers.values() if w["last_seen"] >= cutoff]

    def _has_gpu_capacity(self) -> bool:
        return any(w["has_gpu"] for w in self._fresh_workers())

    # -- distribución del desafío ------------------------------------------
    def handle_challenge(self, challenge: dict) -> None:
        wid = challenge.get("voting_window_id")
        workers = self._fresh_workers()
        log.info("desafío %s recibido; %d worker(s) disponibles", wid, len(workers))

        if not self._has_gpu_capacity():
            # No tocamos n_zeros_required (lo fija el NCT, dificultad fija n/n+1).
            # PREGUNTA ABIERTA (AGENT.md 10): el enunciado P5 sugiere "reducir el
            # prefijo" sin GPU; eso contradeciría la dificultad fija de consenso.
            # En Pilar 2 sólo se registra la decisión; el escalado CPU es Pilar 3.
            log.warning("sin workers GPU: se requeriría escalar mineros CPU "
                        "(autoescalado = Pilar 3); dificultad NO se reduce")

        chunks = fragment_range(0, self.nonce_space, self.fragment_size)
        for idx, (rmin, rmax) in enumerate(chunks):
            self.m.publish_task({
                "voting_window_id": wid,
                "law_id": challenge.get("law_id"),
                "action": challenge.get("action"),
                "partial_hash_base": challenge.get("partial_hash_base"),
                "n_zeros_required": challenge.get("n_zeros_required"),
                "range_min": rmin,
                "range_max": rmax,
                "fragment_index": idx,
                "fragment_count": len(chunks),
            })
        log.info("desafío %s fragmentado en %d tareas de %d nonces",
                 wid, len(chunks), self.fragment_size)

    def tick(self) -> None:
        # Limpieza de workers vencidos (sólo para mantener el mapa acotado).
        cutoff = self.now() - KEEPALIVE_TTL
        stale = [w for w, d in self._workers.items() if d["last_seen"] < cutoff]
        for w in stale:
            del self._workers[w]
