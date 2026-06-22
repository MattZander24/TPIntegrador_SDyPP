"""Pool Miner: worker que se conecta al Pool Coordinator vía HTTP.

No utiliza RabbitMQ directamente. Recibe sub-rangos del coordinator,
los mina y devuelve resultados.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.request
import urllib.error

log = logging.getLogger("voxchain.miner")


class PoolMiner:
    def __init__(self, coordinator_url: str, *, miner_id: str = "",
                 capacity: int = 1, has_gpu: bool = False,
                 mine, clock=time.time, heartbeat_interval: float = 10.0):
        self.url = coordinator_url.rstrip("/")
        self.miner_id = miner_id
        self.capacity = capacity
        self.has_gpu = has_gpu
        self.mine = mine
        self.now = clock
        self.heartbeat_interval = heartbeat_interval
        self._registered = False
        self._last_hb = 0.0
        self._running = False

    def stop(self) -> None:
        self._running = False

    def join(self, coordinator_url: str) -> None:
        self.url = coordinator_url.rstrip("/")
        self._registered = False
        self._running = True

    def _post(self, path: str, data: dict) -> dict | None:
        try:
            body = json.dumps(data).encode()
            req = urllib.request.Request(
                f"{self.url}{path}",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except Exception as e:
            log.warning("error en POST %s: %s", path, e)
            return None

    def _get(self, path: str) -> dict | None:
        try:
            req = urllib.request.Request(f"{self.url}{path}", method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 204:
                    return None
                return json.loads(resp.read())
        except Exception as e:
            log.warning("error en GET %s: %s", path, e)
            return None

    def register(self) -> bool:
        resp = self._post("/register", {
            "capacity": self.capacity,
            "has_gpu": self.has_gpu,
        })
        if resp and "miner_id" in resp:
            self.miner_id = resp["miner_id"]
            self._registered = True
            log.info("registrado en pool como %s", self.miner_id)
            return True
        log.warning("no se pudo registrar en pool")
        return False

    def heartbeat(self) -> bool:
        if not self.miner_id:
            return False
        resp = self._post("/heartbeat", {"miner_id": self.miner_id})
        ok = resp and resp.get("ok", False)
        return bool(ok)

    def request_work(self) -> dict | None:
        if not self.miner_id:
            return None
        return self._get(f"/work/next/{self.miner_id}")

    def submit_result(self, voting_window_id: str, nonce: int,
                      block_hash_candidato: str) -> bool:
        if not self.miner_id:
            return False
        resp = self._post("/work/result", {
            "miner_id": self.miner_id,
            "result": {
                "voting_window_id": voting_window_id,
                "nonce": nonce,
                "block_hash_candidato": block_hash_candidato,
            },
        })
        return bool(resp and resp.get("ok", False))

    def run(self) -> None:
        log.info("pool-miner iniciando (coordinator=%s)", self.url)
        self._running = True
        while self._running and not self._registered:
            if self.register():
                break
            log.warning("reintentando registro en 5s...")
            time.sleep(5)

        while self._running:
            now = self.now()
            if now - self._last_hb >= self.heartbeat_interval:
                self._last_hb = now
                self.heartbeat()

            from common.blockchain.challenge import prefix_for_zeros

            task = self.request_work()
            if not task:
                time.sleep(2)
                continue

            wid = task["voting_window_id"]
            base = task["partial_hash_base"]
            prefix = prefix_for_zeros(int(task.get("n_zeros_required", 4)))
            rmin = int(task["range_min"])
            rmax = int(task["range_max"])

            log.info("minando ventana %s rango [%d, %d)", wid, rmin, rmax)
            nonce, hash_hex = self.mine(base, prefix, rmin, rmax)

            if nonce is not None:
                self.submit_result(wid, nonce, hash_hex)
                log.info("nonce %d enviado para ventana %s", nonce, wid)