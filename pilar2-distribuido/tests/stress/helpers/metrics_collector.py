"""Recolecta snapshots de estado del sistema durante las pruebas.

Funciona en dos modos:
- Redis directo (default): más rápido, requiere `kubectl port-forward svc/redis`.
- HTTP (fallback): usa los endpoints de la API, no requiere acceso directo a Redis.

Los snapshots se guardan en memoria y se pueden exportar a CSV/JSON al final
de cada escenario para análisis post-test.
"""

from __future__ import annotations

import csv
import json
import time
from dataclasses import asdict, dataclass
from threading import Event, Thread
from typing import List


@dataclass
class Snapshot:
    ts: float
    elapsed_s: float
    chain_length: int
    queue_depth: int
    active_window: str | None
    window_counter: int
    sealed_windows: int
    nct_leader: str | None
    pool_leader: str | None
    redis_used_memory_mb: float


class RedisMetricsCollector:
    """Recolecta métricas directamente desde Redis (requiere conexión directa)."""

    def __init__(self, redis_url: str, interval: float = 5.0):
        import redis as redis_lib
        self._client = redis_lib.from_url(redis_url, decode_responses=True)
        self._interval = interval
        self._snapshots: List[Snapshot] = []
        self._stop = Event()
        self._thread: Thread | None = None
        self._t0: float = 0.0

    def start(self) -> None:
        self._t0 = time.time()
        self._stop.clear()
        self._thread = Thread(target=self._loop, daemon=True, name="metrics-collector")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self._interval + 2)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._snapshots.append(self._take())
            except Exception as exc:
                print(f"[metrics] snapshot error: {exc}")
            self._stop.wait(self._interval)

    def _take(self) -> Snapshot:
        pipe = self._client.pipeline(transaction=False)
        pipe.llen("chain")
        pipe.llen("law_queue")
        pipe.get("active_window")
        pipe.get("window_counter")
        pipe.get("nct:leader")
        pipe.get("pool:leader")
        pipe.info("memory")
        results = pipe.execute()

        chain_len, queue_depth, active_win, win_counter, nct_leader, pool_leader, mem = results

        # Cuenta ventanas selladas activas (TTL positivo)
        sealed = sum(1 for _ in self._client.scan_iter("window_sealed:*"))

        now = time.time()
        return Snapshot(
            ts=now,
            elapsed_s=round(now - self._t0, 1),
            chain_length=int(chain_len or 0),
            queue_depth=int(queue_depth or 0),
            active_window=active_win,
            window_counter=int(win_counter or 0),
            sealed_windows=sealed,
            nct_leader=nct_leader,
            pool_leader=pool_leader,
            redis_used_memory_mb=round(mem.get("used_memory", 0) / 1024 / 1024, 3),
        )

    # ── Acceso a datos ──────────────────────────────────────────────────────

    def snapshots(self) -> List[Snapshot]:
        return list(self._snapshots)

    def latest(self) -> Snapshot | None:
        return self._snapshots[-1] if self._snapshots else None

    def export_csv(self, path: str) -> None:
        if not self._snapshots:
            return
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=asdict(self._snapshots[0]).keys())
            writer.writeheader()
            writer.writerows(asdict(s) for s in self._snapshots)

    def export_json(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump([asdict(s) for s in self._snapshots], f, indent=2)

    def summary(self) -> dict:
        if not self._snapshots:
            return {"error": "no snapshots"}
        first, last = self._snapshots[0], self._snapshots[-1]
        duration = last.ts - first.ts or 1
        blocks = last.chain_length - first.chain_length
        queue_samples = [s.queue_depth for s in self._snapshots]
        mem_samples = [s.redis_used_memory_mb for s in self._snapshots]
        return {
            "duration_seconds": round(duration, 1),
            "blocks_sealed":    blocks,
            "throughput_blocks_per_min": round(blocks / duration * 60, 2),
            "max_queue_depth":  max(queue_samples),
            "avg_queue_depth":  round(sum(queue_samples) / len(queue_samples), 1),
            "final_chain_length": last.chain_length,
            "max_redis_memory_mb": round(max(mem_samples), 2),
            "snapshots_taken":  len(self._snapshots),
        }


class HttpMetricsCollector:
    """Recolecta métricas via la HTTP API (no necesita acceso directo a Redis).

    Menos granular que RedisMetricsCollector, pero funciona desde cualquier
    máquina con acceso al Ingress de GKE sin port-forward.
    """

    def __init__(self, api_base_url: str, interval: float = 10.0):
        import requests
        self._base = api_base_url.rstrip("/")
        self._interval = interval
        self._session = requests.Session()
        self._snapshots: List[dict] = []
        self._stop = Event()
        self._thread: Thread | None = None
        self._t0: float = 0.0

    def start(self) -> None:
        self._t0 = time.time()
        self._stop.clear()
        self._thread = Thread(target=self._loop, daemon=True, name="http-metrics")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self._interval + 2)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._snapshots.append(self._take())
            except Exception as exc:
                print(f"[http-metrics] error: {exc}")
            self._stop.wait(self._interval)

    def _take(self) -> dict:
        now = time.time()
        snap: dict = {"ts": now, "elapsed_s": round(now - self._t0, 1)}
        try:
            r = self._session.get(f"{self._base}/api/chain", timeout=5)
            snap["chain_length"] = len(r.json()) if r.ok else -1
        except Exception:
            snap["chain_length"] = -1
        try:
            r = self._session.get(f"{self._base}/api/laws/queue", timeout=5)
            snap["queue_depth"] = len(r.json()) if r.ok else -1
        except Exception:
            snap["queue_depth"] = -1
        try:
            r = self._session.get(f"{self._base}/api/health", timeout=5)
            h = r.json() if r.ok else {}
            snap["nct_status"] = h.get("nct", "unknown")
            snap["redis_status"] = h.get("redis", "unknown")
        except Exception:
            snap["nct_status"] = "error"
            snap["redis_status"] = "error"
        return snap

    def snapshots(self) -> List[dict]:
        return list(self._snapshots)

    def export_json(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self._snapshots, f, indent=2)

    def summary(self) -> dict:
        if not self._snapshots:
            return {"error": "no snapshots"}
        first, last = self._snapshots[0], self._snapshots[-1]
        duration = (last["ts"] - first["ts"]) or 1
        start_chain = first.get("chain_length", 0)
        end_chain = last.get("chain_length", 0)
        blocks = (end_chain - start_chain) if start_chain >= 0 and end_chain >= 0 else -1
        return {
            "duration_seconds": round(duration, 1),
            "blocks_sealed": blocks,
            "throughput_blocks_per_min": round(blocks / duration * 60, 2) if blocks >= 0 else "n/a",
            "final_chain_length": end_chain,
            "snapshots_taken": len(self._snapshots),
        }
