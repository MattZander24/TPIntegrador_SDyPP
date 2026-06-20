"""Lógica del worker: consume un rango asignado, mina y publica el nonce.

Agnóstico del transporte: recibe un ``Messaging`` y una función ``mine`` (por
defecto el puente al minero de Pilar 1). Es idempotente ante reasignación de
rangos: no vuelve a publicar para una ventana que ya resolvió.
"""

from __future__ import annotations

import logging
import time

from common.metrics import worker_busy, worker_has_gpu, worker_nonces_found_total, worker_tasks_received_total
from common.blockchain.challenge import prefix_for_zeros

log = logging.getLogger("voxchain.worker")


class Worker:
    def __init__(self, messaging, *, worker_id: str, mine, capacity: int = 1,
                 has_gpu: bool = False, clock=time.time, keepalive_interval: float = 5.0):
        self.m = messaging
        self.worker_id = worker_id
        self.mine = mine
        self.capacity = capacity
        self.has_gpu = has_gpu
        self.now = clock
        self.keepalive_interval = keepalive_interval
        self._solved: set[str] = set()
        self._last_keepalive = 0.0
        worker_has_gpu.set(1 if has_gpu else 0)

    def wire(self) -> None:
        self.m.on_task(self.handle_task)

    def handle_task(self, task: dict) -> None:
        wid = task.get("voting_window_id")
        if wid in self._solved:
            log.debug("tarea ignorada: ventana %s ya resuelta por este worker", wid)
            return
        worker_tasks_received_total.inc()
        worker_busy.set(1)
        base = task["partial_hash_base"]
        prefix = prefix_for_zeros(int(task["n_zeros_required"]))
        rmin = int(task["range_min"])
        rmax = int(task["range_max"])
        log.info("minando ventana %s rango [%d, %d) prefijo %r",
                 wid, rmin, rmax, prefix)

        nonce, hash_hex = self.mine(base, prefix, rmin, rmax)
        worker_busy.set(0)
        if nonce is None:
            log.info("sin solución en [%d, %d) para %s", rmin, rmax, wid)
            return
        worker_nonces_found_total.inc()

        self._solved.add(wid)
        self.m.publish_nonce_response({
            "voting_window_id": wid,
            "nonce": nonce,
            "winning_node_or_pool": self.worker_id,
            "block_hash_candidato": hash_hex,
        })
        log.info("nonce %d publicado para ventana %s", nonce, wid)

    def emit_keepalive(self) -> None:
        self.m.publish_keepalive({
            "worker_id": self.worker_id,
            "capacity": self.capacity,
            "has_gpu": self.has_gpu,
            "ts": self.now(),
        })

    def tick(self) -> None:
        now = self.now()
        if now - self._last_keepalive >= self.keepalive_interval:
            self.emit_keepalive()
            self._last_keepalive = now
