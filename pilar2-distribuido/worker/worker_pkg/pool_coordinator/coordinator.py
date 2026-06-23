"""Pool Coordinator embebido: consume desafíos del NCT y los fragmenta.

Un pool es una organización que agrega mineros voluntarios. Desde la perspectiva
del NCT es indistinguible de un worker standalone. Internamente subdivide
el espacio de nonces entre sus miners registrados (HTTP) y su propio auto-miner.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from threading import Lock

from common.blockchain.challenge import prefix_for_zeros
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


def fragment_range(start: int, end: int, fragment_size: int) -> list[tuple[int, int]]:
    if fragment_size <= 0:
        raise ValueError("fragment_size debe ser positivo")
    if end <= start:
        return []
    chunks = []
    cur = start
    while cur < end:
        chunks.append((cur, min(cur + fragment_size, end)))
        cur += fragment_size
    return chunks


class PoolCoordinator:
    def __init__(self, messaging, *, pool_id: str, redis, mine,
                 capacity: int = 1, clock=time.time,
                 keepalive_interval: float = 5.0,
                 lease_ttl: int = 10, lease_key: str = "pool:leader",
                 election_n_zeros: int | None = None,
                 signer=None):
        self.m = messaging
        self.pool_id = pool_id
        self.signer = signer
        self.redis = redis
        self.capacity = capacity
        self.mine = mine
        self.now = clock
        self.keepalive_interval = keepalive_interval
        self.lease_ttl = lease_ttl
        self.lease_key = lease_key
        self._miners: dict[str, dict] = {}
        self._pending_fragments: deque[dict] = deque()
        self._lock = Lock()
        self._solved: set[str] = set()
        self._voting_policy = {"decision": "accept"}
        self._last_keepalive = 0.0
        self._last_lease_renew = 0.0
        self.is_leader = False
        self._miner_counter = 0
        self._running = False
        self._auto_miner_thread: threading.Thread | None = None
        self.nonce_space = int(os.getenv("NONCE_SPACE", "50000000"))
        self.fragment_size = int(os.getenv("FRAGMENT_SIZE", "1000000"))
        self._election_n_zeros = (
            election_n_zeros
            if election_n_zeros is not None
            else int(os.getenv("POOL_ELECTION_N_ZEROS", "2"))
        )
        self._election_thread: threading.Thread | None = None
        self._election_result = False
        self._election_in_progress = False
        pool_is_leader.set(0)

    def wire(self) -> None:
        self.m.on_challenge(self.handle_challenge)

    def try_acquire_leadership(self) -> bool:
        acquired = self.redis.set(self.lease_key, self.pool_id,
                                  nx=True, ex=self.lease_ttl)
        if acquired:
            self.is_leader = True
            pool_is_leader.set(1)
            log.info("pool coordinator %s adquirió liderazgo", self.pool_id)
        return bool(acquired)

    def renew_leadership(self) -> bool:
        pipe = self.redis.pipeline()
        pipe.get(self.lease_key)
        pipe.pttl(self.lease_key)
        current, _ttl = pipe.execute()
        if current is None:
            self.redis.setex(self.lease_key, self.lease_ttl, self.pool_id)
            return True
        if isinstance(current, str):
            same = (current == self.pool_id)
        else:
            same = (current == self.pool_id.encode())
        if same:
            self.redis.setex(self.lease_key, self.lease_ttl, self.pool_id)
            return True
        self.is_leader = False
        pool_is_leader.set(0)
        pool_miners_registered.set(0)
        log.warning("pool coordinator %s perdió liderazgo", self.pool_id)
        return False

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
                if info["last_seen"] >= cutoff]

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
            if not self._pending_fragments:
                return None
            fragment = self._pending_fragments.popleft()
            pool_work_distributed_total.inc()
            return {
                "voting_window_id": fragment["voting_window_id"],
                "law_id": fragment.get("law_id"),
                "action": fragment.get("action"),
                "partial_hash_base": fragment["partial_hash_base"],
                "n_zeros_required": fragment.get("n_zeros_required"),
                "range_min": fragment["range_min"],
                "range_max": fragment["range_max"],
            }

    def _get_auto_miner_fragment(self) -> dict | None:
        with self._lock:
            if not self._pending_fragments:
                return None
            return self._pending_fragments.popleft()

    def submit_result(self, miner_id: str, result: dict) -> bool:
        wid = result.get("voting_window_id")
        nonce = result.get("nonce")
        hash_hex = result.get("block_hash_candidato")
        if not wid or nonce is None:
            return False
        if wid in self._solved:
            return False
        self._solved.add(wid)
        pool_nonces_found_total.inc()
        winner = self.signer.identity(self.pool_id) if self.signer else self.pool_id
        payload = {
            "voting_window_id": wid,
            "nonce": nonce,
            "winning_node_or_pool": winner,
            "block_hash_candidato": hash_hex,
        }
        if self.signer and self.signer.enabled:
            payload["signature"] = self.signer.sign_nonce(wid, nonce, winner)
        self.m.publish_nonce_response(payload)
        log.info("pool %s publicó nonce %d para ventana %s", self.pool_id, nonce, wid)
        return True

    def set_voting_policy(self, policy: dict) -> None:
        decision = policy.get("decision", "accept")
        if decision not in ("accept", "reject"):
            raise ValueError(f"decision inválida: {decision}")
        self._voting_policy = policy
        log.info("pool %s política de voto: %s", self.pool_id, policy)

    def _check_voting_policy(self, challenge: dict) -> bool:
        policy = self._voting_policy
        if policy["decision"] == "accept":
            return True
        if policy.get("action") and challenge.get("action") == policy["action"]:
            return False
        if policy.get("law_id") and challenge.get("law_id") == policy["law_id"]:
            return False
        if "action" not in policy and "law_id" not in policy:
            return False
        return True

    def handle_challenge(self, challenge: dict) -> None:
        if not self._running:
            return
        wid = challenge.get("voting_window_id")
        if not wid or wid in self._solved:
            return
        deadline_str = challenge.get("deadline", "")
        if deadline_str:
            try:
                deadline_ts = datetime.fromisoformat(deadline_str).timestamp()
                if self.now() > deadline_ts:
                    log.info("pool %s ventana %s ya venció, saltando", self.pool_id, wid)
                    return
            except (ValueError, TypeError):
                pass
        if not self._check_voting_policy(challenge):
            log.info("pool %s rechaza ventana %s por política de voto",
                     self.pool_id, wid)
            return
        worker_tasks_received_total.inc()
        worker_busy.set(1)
        chunks = fragment_range(0, self.nonce_space, self.fragment_size)
        log.info("pool %s desafío %s fragmentado en %d tareas",
                 self.pool_id, wid, len(chunks))
        with self._lock:
            for rmin, rmax in chunks:
                self._pending_fragments.append({
                    "voting_window_id": wid,
                    "law_id": challenge.get("law_id"),
                    "action": challenge.get("action"),
                    "partial_hash_base": challenge["partial_hash_base"],
                    "n_zeros_required": challenge.get("n_zeros_required"),
                    "range_min": rmin,
                    "range_max": rmax,
                })

    def _auto_mine_loop(self) -> None:
        while self._running:
            fragment = self._get_auto_miner_fragment()
            if fragment:
                wid = fragment["voting_window_id"]
                base = fragment["partial_hash_base"]
                prefix = prefix_for_zeros(int(fragment.get("n_zeros_required", 4)))
                rmin = fragment["range_min"]
                rmax = fragment["range_max"]
                log.info("pool %s auto-minando ventana %s rango [%d, %d)",
                         self.pool_id, wid, rmin, rmax)
                nonce, hash_hex = self.mine(base, prefix, rmin, rmax)
                if nonce is not None:
                    self.submit_result(self.pool_id, {
                        "voting_window_id": wid,
                        "nonce": nonce,
                        "block_hash_candidato": hash_hex,
                    })
                    log.info("pool %s auto-miner nonce %d para ventana %s",
                             self.pool_id, nonce, wid)
            else:
                time.sleep(0.5)

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

    def start(self) -> None:
        self._running = True
        self._auto_miner_thread = threading.Thread(target=self._auto_mine_loop, daemon=True)
        self._auto_miner_thread.start()

    def stop(self) -> None:
        self._running = False
        if self._auto_miner_thread:
            self._auto_miner_thread.join(timeout=5)
            self._auto_miner_thread = None

    def _run_election(self) -> None:
        from worker_pkg.pool_coordinator.election import run_pool_election
        try:
            won = run_pool_election(
                self.redis,
                self.pool_id,
                n_zeros=self._election_n_zeros,
                lease_key=self.lease_key,
                lease_ttl=self.lease_ttl,
                clock=self.now,
            )
            self._election_result = won
        except Exception:
            log.exception("pool %s: error inesperado durante la elección", self.pool_id)
            self._election_result = False
        finally:
            self._election_in_progress = False

    def _maybe_start_election(self) -> None:
        if self._election_in_progress:
            return
        current_leader = self.redis.get(self.lease_key)
        if current_leader is not None and current_leader != self.pool_id:
            return
        self._election_in_progress = True
        self._election_result = False
        t = threading.Thread(target=self._run_election, daemon=True,
                             name=f"pool-election-{self.pool_id}")
        self._election_thread = t
        t.start()

    def tick(self) -> None:
        now = self.now()
        self._purge_stale_miners()

        # Recoger resultado de elección completada
        if (not self.is_leader
                and self._election_thread is not None
                and not self._election_thread.is_alive()):
            if self._election_result:
                self.is_leader = True
                pool_is_leader.set(1)
                log.info("pool coordinator %s ganó la elección, asumiendo liderazgo",
                         self.pool_id)
            self._election_thread = None

        if now - self._last_lease_renew >= 3.0:
            self._last_lease_renew = now
            if self.is_leader:
                if not self.renew_leadership():
                    return
            else:
                self._maybe_start_election()

        if not self.is_leader:
            return
        if now - self._last_keepalive >= self.keepalive_interval:
            self.emit_keepalive()
            self._last_keepalive = now
