from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone

from common.blockchain.challenge import solve_mini_challenge, prefix_for_zeros
from common.health import start_health_server
from common.metrics import worker_busy, worker_has_gpu, worker_nonces_found_total
from worker_pkg.miner import run_miner
from worker_pkg.pool_worker import PoolWorker
from worker_pkg.pool_coordinator import PoolCoordinator
from worker_pkg.pool_coordinator.server import start_pool_http_server

log = logging.getLogger("voxchain.worker.bully")

ELECTION_EPOCH_SECONDS = 30
LEADER_TIMEOUT = 12.0
HEARTBEAT_INTERVAL = 5.0
ELECTION_N_ZEROS = 2


class PoolBully:
    CANDIDATE = "candidate"
    COORDINATOR = "coordinator"
    MINER = "miner"

    def __init__(self, worker_id: str, pool_id: str, messaging, *,
                 has_gpu: bool = False, capacity: int = 1,
                 address: str = "", signer=None):
        self.worker_id = worker_id
        self.pool_id = pool_id
        self.m = messaging
        self.has_gpu = has_gpu
        self.capacity = capacity
        self.address = address
        self.signer = signer

        self.state = self.CANDIDATE
        self.leader_id = None
        self.leader_address = ""
        self._last_heartbeat = 0.0
        self._last_hb_sent = 0.0
        self._election_in_progress = False
        self._pending_claim = None
        self._election_epoch = 0
        self._election_seed = ""
        self._coordinator = None
        self._pool_worker = None
        self._httpd = None
        self._httpd_thread = None
        self._pw_thread = None
        self._running = True

    def wire(self):
        self.m.on_pool_election(self.pool_id, self._handle_message)

    def stop(self):
        self._running = False
        self._stop_coordinator()
        self._stop_miner()

    def tick(self):
        if not self._running:
            return
        now = time.time()

        if self.state == self.CANDIDATE:
            if self._pending_claim is not None:
                self.m.publish_pool_election(self.pool_id, self._pending_claim)
                self._pending_claim = None
                self._election_in_progress = False
            elif now - self._last_heartbeat >= LEADER_TIMEOUT:
                self._start_election()
        elif self.state == self.COORDINATOR:
            if now - self._last_hb_sent >= HEARTBEAT_INTERVAL:
                self._send_heartbeat()
                self._last_hb_sent = now
            if self._coordinator:
                self._coordinator.tick()
        elif self.state == self.MINER:
            if now - self._last_heartbeat >= LEADER_TIMEOUT * 2:
                log.warning("%s: heartbeat timeout del coordinador %s, re-eleccionando",
                            self.worker_id, self.leader_id)
                self._transition_to(self.CANDIDATE)

    # -- message handling ---------------------------------------------------

    def _handle_message(self, msg: dict):
        msg_type = msg.get("type")
        now = time.time()

        if msg_type == "heartbeat":
            worker_id = msg.get("worker_id", "")
            if worker_id == self.worker_id:
                return
            self._last_heartbeat = now
            self._pending_claim = None
            if self.state == self.CANDIDATE:
                log.info("%s: detectado coordinador %s, uniéndose como miner",
                         self.worker_id, worker_id)
                self._become_miner(worker_id, msg.get("address", ""))

        elif msg_type == "claim":
            candidate_id = msg.get("worker_id", "")
            if candidate_id == self.worker_id:
                if self.state == self.CANDIDATE:
                    self._transition_to(self.COORDINATOR)
                return
            if self.state == self.CANDIDATE and self._verify_claim(msg):
                self._last_heartbeat = now
                self._pending_claim = None
                log.info("%s: %s ganó elección, uniéndose como miner",
                         self.worker_id, candidate_id)
                self._become_miner(candidate_id, msg.get("address", ""))

    # -- election -----------------------------------------------------------

    def _start_election(self):
        if self._election_in_progress:
            return
        self._election_in_progress = True
        self._pending_claim = None
        t = threading.Thread(target=self._solve_pow, daemon=True)
        t.start()

    def _solve_pow(self):
        try:
            self._election_epoch = int(time.time() / ELECTION_EPOCH_SECONDS)
            self._election_seed = f"{self.pool_id}:{self._election_epoch}"
            log.info("%s: elección bully (seed=…%s, %d ceros, epoch=%d)",
                     self.worker_id, self._election_seed[-8:],
                     ELECTION_N_ZEROS, self._election_epoch)

            nonce = solve_mini_challenge(self._election_seed, ELECTION_N_ZEROS)
            if nonce is None:
                log.warning("%s: no se pudo resolver mini-PoW", self.worker_id)
                return

            log.info("%s: mini-PoW resuelto (nonce=%d), esperando tick para publicar",
                     self.worker_id, nonce)
            self._pending_claim = {
                "type": "claim",
                "worker_id": self.worker_id,
                "address": self.address,
                "nonce": nonce,
                "seed": self._election_seed,
                "n_zeros": ELECTION_N_ZEROS,
                "epoch": self._election_epoch,
                "has_gpu": self.has_gpu,
                "capacity": self.capacity,
                "ts": time.time(),
            }
        except Exception:
            log.exception("%s: error resolviendo PoW", self.worker_id)

    @staticmethod
    def _verify_claim(msg: dict) -> bool:
        from common.blockchain.challenge import compute_hash, prefix_for_zeros
        seed = msg.get("seed", "")
        nonce = msg.get("nonce", 0)
        n_zeros = msg.get("n_zeros", ELECTION_N_ZEROS)
        if not seed or nonce < 0:
            return False
        prefix = prefix_for_zeros(n_zeros)
        return compute_hash(seed, nonce).startswith(prefix)

    # -- coordinator --------------------------------------------------------

    def _transition_to(self, new_state: str):
        if new_state == self.state:
            return
        log.info("%s: transición %s → %s", self.worker_id, self.state, new_state)
        old = self.state
        if old == self.COORDINATOR:
            self._stop_coordinator()
        if old == self.MINER:
            self._stop_miner()

        self.state = new_state

        if new_state == self.COORDINATOR:
            self._start_coordinator()
        elif new_state == self.MINER:
            self._start_miner()
        elif new_state == self.CANDIDATE:
            self.leader_id = None
            self.leader_address = ""
            self._last_heartbeat = 0

    def _start_coordinator(self):
        log.info("%s: asumiendo como coordinador del pool %s", self.worker_id, self.pool_id)
        self.leader_id = self.worker_id
        self.leader_address = self.address

        pc = PoolCoordinator(
            self.m,
            pool_id=self.worker_id,
            redis=None,
            mine=run_miner,
            capacity=self.capacity,
            signer=self.signer,
        )
        pc.wire()
        pc.start()
        self._coordinator = pc

        self._httpd = start_pool_http_server(pc, port=self._http_port())
        self._httpd_thread = threading.Thread(
            target=self._httpd.serve_forever, daemon=True
        )
        self._httpd_thread.start()

        self._last_hb_sent = 0
        log.info("%s: coordinador listo en %s", self.worker_id, self.address)

    def _stop_coordinator(self):
        if self._coordinator:
            self._coordinator.stop()
            self._coordinator = None
        if self._httpd:
            self._httpd.shutdown()
            self._httpd = None
        self._httpd_thread = None

    def _send_heartbeat(self):
        self.m.publish_pool_election(self.pool_id, {
            "type": "heartbeat",
            "worker_id": self.worker_id,
            "address": self.address,
            "has_gpu": self.has_gpu,
            "capacity": self.capacity,
            "ts": time.time(),
        })

    # -- miner --------------------------------------------------------------

    def _start_miner(self):
        url = self.leader_address or f"http://{self.leader_id}:{self._http_port()}"
        log.info("%s: uniéndose como miner al coordinador %s", self.worker_id, url)

        pw = PoolWorker(
            url,
            miner_id=self.worker_id,
            capacity=self.capacity,
            has_gpu=self.has_gpu,
            mine=run_miner,
        )
        self._pool_worker = pw
        self._pw_thread = threading.Thread(target=pw.run, daemon=True)
        self._pw_thread.start()

    def _stop_miner(self):
        if self._pool_worker:
            self._pool_worker.stop()
            self._pool_worker = None
        self._pw_thread = None

    def _become_miner(self, leader_id: str, leader_address: str):
        self.leader_id = leader_id
        self.leader_address = leader_address
        self._transition_to(self.MINER)

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _http_port() -> int:
        return int(os.getenv("POOL_HTTP_PORT", "9001"))
