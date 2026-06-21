"""Pool Coordinator: consume tareas del TrP y las distribuye a miners conectados.

Un pool es una organización que agrega mineros voluntarios. Desde la perspectiva
del NCT/TrP es indistinguible de un worker standalone. Internamente subdivide
el rango de nonces recibido entre sus miners registrados vía HTTP.
"""

from __future__ import annotations

import json
import logging
import time
from threading import Lock

from common.blockchain.challenge import prefix_for_zeros
from common.messaging.base import QUEUE_TAREAS, QUEUE_KEEPALIVE
from common.metrics import (
    pool_is_leader,
    pool_miners_registered,
    pool_nonces_found_total,
    pool_work_distributed_total,
    worker_busy,
    worker_nonces_found_total,
    worker_tasks_received_total,
)

log = logging.getLogger("voxchain.pool")

KEEPALIVE_TTL = 15.0


class PoolCoordinator:
    def __init__(self, messaging, *, pool_id: str, redis, capacity: int = 1,
                 clock=time.time, keepalive_interval: float = 5.0,
                 lease_ttl: int = 10, lease_key: str = "pool:leader"):
        self.m = messaging
        self.pool_id = pool_id
        self.redis = redis
        self.capacity = capacity
        self.now = clock
        self.keepalive_interval = keepalive_interval
        self.lease_ttl = lease_ttl
        self.lease_key = lease_key
        self._miners: dict[str, dict] = {}
        self._tasks: list[dict] = []
        self._lock = Lock()
        self._solved: set[str] = set()
        self._last_keepalive = 0.0
        self._last_lease_renew = 0.0
        self.is_leader = False
        self._miner_counter = 0
        self._next_miner_idx = 0
        pool_is_leader.set(0)

    def wire(self) -> None:
        self.m.on_task(self.handle_task)

    def try_acquire_leadership(self) -> bool:
        acquired = self.redis.set(self.lease_key, self.pool_id,
                                  nx=True, ex=self.lease_ttl)
        if acquired:
            self.is_leader = True
            pool_is_leader.set(1)
            log.info("pool coordinator %s adquirió liderazgo", self.pool_id)
            self._subscribe_work_queues()
        return bool(acquired)

    def renew_leadership(self) -> bool:
        pipe = self.redis.pipeline()
        pipe.get(self.lease_key)
        pipe.pttl(self.lease_key)
        current, ttl = pipe.execute()
        if current == self.pool_id.encode() if isinstance(current, str) else current:
            self.redis.setex(self.lease_key, self.lease_ttl, self.pool_id)
            return True
        self.is_leader = False
        pool_is_leader.set(0)
        pool_miners_registered.set(0)
        self._unsubscribe_work_queues()
        log.warning("pool coordinator %s perdió liderazgo", self.pool_id)
        return False

    def _subscribe_work_queues(self) -> None:
        self.m.on_task(self.handle_task)

    def _unsubscribe_work_queues(self) -> None:
        self.m.unsubscribe(QUEUE_TAREAS)

    def register_miner(self, capacity: int = 1, has_gpu: bool = False) -> str:
        with self._lock:
            self._miner_counter += 1
            mid = f"{self.pool_id}-miner-{self._miner_counter}"
            self._miners[mid] = {
                "capacity": capacity,
                "has_gpu": has_gpu,
                "last_seen": self.now(),
                "busy": False,
            }
            pool_miners_registered.set(len(self._miners))
            log.info("miner %s registrado (capacity=%d, gpu=%s)", mid, capacity, has_gpu)
            return mid

    def handle_heartbeat(self, miner_id: str) -> bool:
        with self._lock:
            if miner_id in self._miners:
                self._miners[miner_id]["last_seen"] = self.now()
                return True
            return False

    def _fresh_miners(self) -> list[tuple[str, dict]]:
        cutoff = self.now() - KEEPALIVE_TTL
        return [(mid, info) for mid, info in self._miners.items()
                if info["last_seen"] >= cutoff and not info["busy"]]

    def _purge_stale_miners(self) -> None:
        cutoff = self.now() - KEEPALIVE_TTL
        stale = [mid for mid, info in self._miners.items()
                 if info["last_seen"] < cutoff]
        for mid in stale:
            del self._miners[mid]
        pool_miners_registered.set(len(self._miners))
        if stale:
            log.debug("miners stale eliminados: %s", stale)

    def get_next_task(self, miner_id: str) -> dict | None:
        with self._lock:
            if miner_id not in self._miners:
                return None
            if not self._tasks:
                return None
            task = self._tasks[0]
            fresh = self._fresh_miners()
            idx = self._next_miner_idx % len(fresh) if fresh else 0
            self._next_miner_idx += 1
            total = len(fresh)
            if total == 0:
                return None
            task = self._tasks[0]
            space = int(task["range_max"]) - int(task["range_min"])
            chunk = max(1, space // max(total, 1))
            rmin = int(task["range_min"]) + idx * chunk
            rmax = min(int(task["range_min"]) + (idx + 1) * chunk, int(task["range_max"]))
            if rmin >= int(task["range_max"]):
                return None
            self._miners[miner_id]["busy"] = True
            pool_work_distributed_total.inc()
            return {
                "voting_window_id": task["voting_window_id"],
                "law_id": task.get("law_id"),
                "action": task.get("action"),
                "partial_hash_base": task["partial_hash_base"],
                "n_zeros_required": task.get("n_zeros_required"),
                "range_min": rmin,
                "range_max": rmax,
            }

    def submit_result(self, miner_id: str, result: dict) -> bool:
        with self._lock:
            if miner_id in self._miners:
                self._miners[miner_id]["busy"] = False
        wid = result.get("voting_window_id")
        nonce = result.get("nonce")
        hash_hex = result.get("block_hash_candidato")
        if not wid or nonce is None:
            return False
        if wid in self._solved:
            return False
        self._solved.add(wid)
        pool_nonces_found_total.inc()
        self.m.publish_nonce_response({
            "voting_window_id": wid,
            "nonce": nonce,
            "winning_node_or_pool": self.pool_id,
            "block_hash_candidato": hash_hex,
        })
        log.info("pool %s publicó nonce %d para ventana %s", self.pool_id, nonce, wid)
        return True

    def handle_task(self, task: dict) -> None:
        wid = task.get("voting_window_id")
        if wid in self._solved:
            return
        worker_tasks_received_total.inc()
        worker_busy.set(1)
        log.info("pool %s recibió tarea ventana %s rango [%d, %d)",
                 self.pool_id, wid, int(task["range_min"]), int(task["range_max"]))
        with self._lock:
            self._tasks.append(task)

    def emit_keepalive(self) -> None:
        fresh = self._fresh_miners()
        total_capacity = sum(m["capacity"] for _, m in fresh)
        has_gpu = any(m["has_gpu"] for _, m in fresh)
        self.m.publish_keepalive({
            "worker_id": self.pool_id,
            "capacity": max(total_capacity, self.capacity),
            "has_gpu": has_gpu,
            "ts": self.now(),
        })
        log.debug("pool %s keepalive: %d miners, capacity %d, gpu=%s",
                  self.pool_id, len(fresh), total_capacity, has_gpu)

    def tick(self) -> None:
        now = self.now()
        self._purge_stale_miners()
        if now - self._last_lease_renew >= 3.0:
            self._last_lease_renew = now
            if self.is_leader:
                if not self.renew_leadership():
                    return
            else:
                self.try_acquire_leadership()
        if not self.is_leader:
            return
        if now - self._last_keepalive >= self.keepalive_interval:
            self.emit_keepalive()
            self._last_keepalive = now