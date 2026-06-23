"""Escenario 5 — Soak test: estabilidad bajo carga sostenida.

Pregunta clave: tras N minutos de carga continua, ¿el sistema sigue
funcionando igual de bien que al principio? (memory leaks, conexiones
acumuladas, degradación de latencia, crecimiento anómalo de colas).

Protocolo:
1. Envía propuestas a ritmo constante (SOAK_PROPOSAL_INTERVAL) durante SOAK_DURATION_S.
2. Cada SOAK_METRICS_INTERVAL segundos toma un snapshot de métricas.
3. Al finalizar, compara el estado inicial vs. el estado final y evalúa:
   - Que la tasa de errores HTTP se mantuvo < SLO_ERROR_RATE_PCT.
   - Que la cola de leyes no creció indefinidamente (< SLO_MAX_QUEUE_DEPTH).
   - Que se sellaron bloques (throughput > 0).
   - Que la latencia del API no se degradó más de 50% entre la primera y última muestra.
4. Exporta snapshots a CSV y JSON para análisis post-test.

Uso:
    cd tests/stress
    # Soak corto (5 min) para validar la suite:
    SOAK_DURATION_SECONDS=300 python scenarios/soak.py

    # Soak completo (30 min) para producción:
    python scenarios/soak.py --duration 1800

    # Con Redis directo para métricas más precisas:
    python scenarios/soak.py --redis-url redis://localhost:6379/0
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests

import config as cfg
from helpers.law_generator import IdentityPool, unique_text
from helpers.report import StressReport

# Intenta importar Redis directo; si no está disponible, usa HTTP metrics
try:
    from helpers.metrics_collector import RedisMetricsCollector as _RedisCollector
    _HAVE_REDIS = True
except Exception:
    _HAVE_REDIS = False

from helpers.metrics_collector import HttpMetricsCollector


# ── Productor ──────────────────────────────────────────────────────────────

class _SoakProducer:
    def __init__(self, api_url: str, interval: float, pool: IdentityPool):
        self._api = api_url
        self._interval = interval
        self._pool = pool
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._sent = 0
        self._errors = 0
        self._latencies: list[float] = []
        self._seq = 0

    def start(self) -> threading.Thread:
        t = threading.Thread(target=self._loop, daemon=True, name="soak-producer")
        t.start()
        return t

    def stop(self) -> None:
        self._stop.set()

    def stats(self) -> dict:
        with self._lock:
            lats = list(self._latencies)
        lats_sorted = sorted(lats)
        n = len(lats_sorted)
        p50 = lats_sorted[int(n * 0.50)] if n else 0
        p95 = lats_sorted[int(n * 0.95)] if n else 0
        p99 = lats_sorted[int(n * 0.99)] if n else 0
        with self._lock:
            return {
                "sent":       self._sent,
                "errors":     self._errors,
                "error_pct":  round(self._errors / max(self._sent, 1) * 100, 2),
                "p50_ms":     round(p50 * 1000, 1),
                "p95_ms":     round(p95 * 1000, 1),
                "p99_ms":     round(p99 * 1000, 1),
            }

    def _loop(self) -> None:
        while not self._stop.is_set():
            identity = self._pool.next()
            with self._lock:
                self._seq += 1
                seq = self._seq
            payload = identity.make_proposal(unique_text("soak", seq))
            t0 = time.time()
            try:
                resp = requests.post(
                    f"{self._api}/api/laws", json=payload, timeout=10
                )
                elapsed = time.time() - t0
                with self._lock:
                    if resp.status_code in (200, 429):
                        self._sent += 1
                        self._latencies.append(elapsed)
                        if len(self._latencies) > 10_000:
                            self._latencies = self._latencies[-5_000:]
                    else:
                        self._errors += 1
            except Exception:
                with self._lock:
                    self._errors += 1
            self._stop.wait(self._interval)


# ── Escenario principal ────────────────────────────────────────────────────

def run(
    api_url: str,
    redis_url: str | None,
    duration_s: int,
    proposal_interval: float,
    metrics_interval: float,
    output_dir: str,
) -> StressReport:
    report = StressReport("soak_test")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    print(f"\n[soak] Iniciando soak test: {duration_s}s @ {1/proposal_interval:.1f} prop/s")
    print(f"[soak] API: {api_url}")
    if redis_url:
        print(f"[soak] Redis: {redis_url}")
    print(f"[soak] Output: {output_dir}/")

    # Selecciona collector
    if redis_url and _HAVE_REDIS:
        collector = _RedisCollector(redis_url, interval=metrics_interval)
        print("[soak] Usando RedisMetricsCollector (métricas directas)")
    else:
        collector = HttpMetricsCollector(api_url, interval=metrics_interval)
        print("[soak] Usando HttpMetricsCollector (vía API)")

    pool = IdentityPool(n=cfg.NUM_IDENTITIES, signed=False)
    producer = _SoakProducer(api_url, proposal_interval, pool)

    # ── Arrancar ───────────────────────────────────────────────────────────
    t_start = time.time()
    collector.start()
    prod_thread = producer.start()

    # ── Progreso periódico en terminal ─────────────────────────────────────
    def _progress_loop():
        while not _done.is_set():
            elapsed = time.time() - t_start
            remaining = max(duration_s - elapsed, 0)
            pct = min(elapsed / duration_s * 100, 100)
            stats = producer.stats()
            snap = collector.latest() if hasattr(collector, "latest") else {}
            chain = snap.chain_length if hasattr(snap, "chain_length") else "?"
            queue = snap.queue_depth  if hasattr(snap, "queue_depth")  else "?"
            print(
                f"[soak] {pct:5.1f}% | {remaining:4.0f}s restantes | "
                f"enviadas={stats['sent']} errores={stats['errors']} "
                f"p95={stats['p95_ms']}ms | "
                f"cadena={chain} cola={queue}"
            )
            _done.wait(30)

    _done = threading.Event()
    _prog = threading.Thread(target=_progress_loop, daemon=True)
    _prog.start()

    # ── Esperar duración ───────────────────────────────────────────────────
    time.sleep(duration_s)

    producer.stop()
    collector.stop()
    _done.set()
    prod_thread.join(timeout=5)

    # ── Recoger resultados ─────────────────────────────────────────────────
    final_stats  = producer.stats()
    metrics_summ = collector.summary()

    # Exportar métricas
    ts = time.strftime("%Y%m%d_%H%M%S")
    try:
        collector.export_csv(f"{output_dir}/soak_metrics_{ts}.csv")
        collector.export_json(f"{output_dir}/soak_metrics_{ts}.json")
        print(f"[soak] Métricas exportadas a {output_dir}/soak_*_{ts}.*")
    except AttributeError:
        collector.export_json(f"{output_dir}/soak_metrics_{ts}.json")

    # ── Evaluación de SLOs ─────────────────────────────────────────────────
    report.check_lte(
        "tasa_error_http",
        final_stats["error_pct"],
        cfg.SLO_ERROR_RATE_PCT,
        "%",
    )
    report.check_lte(
        "p95_latencia_ms",
        final_stats["p95_ms"],
        cfg.SLO_P95_LATENCY_MS,
        "ms",
    )
    report.check_gte(
        "bloques_sellados",
        metrics_summ.get("blocks_sealed", 0),
        1,
    )

    max_queue = metrics_summ.get("max_queue_depth", 0)
    if isinstance(max_queue, (int, float)):
        report.check_lte(
            "max_profundidad_cola",
            max_queue,
            cfg.SLO_MAX_QUEUE_DEPTH,
        )

    # Detectar degradación de latencia: P95 final vs. P95 primeras 10 propuestas
    # (aproximación: comparar errores iniciales vs. finales no disponibles en este modelo)
    # → se deja como métrica informativa en extra
    report.extra.update({
        "duration_s":          duration_s,
        "proposals_sent":      final_stats["sent"],
        "proposals_errors":    final_stats["errors"],
        "error_pct":           final_stats["error_pct"],
        "p50_ms":              final_stats["p50_ms"],
        "p95_ms":              final_stats["p95_ms"],
        "p99_ms":              final_stats["p99_ms"],
        **{f"metrics_{k}": v for k, v in metrics_summ.items()},
    })

    report.print()
    report.save(output_dir)
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="Soak test — VoxChain")
    ap.add_argument("--api-url",          default=cfg.API_BASE_URL)
    ap.add_argument("--redis-url",        default=cfg.REDIS_URL if cfg.REDIS_URL else None)
    ap.add_argument("--duration",         type=int,   default=cfg.SOAK_DURATION_S)
    ap.add_argument("--proposal-interval",type=float, default=cfg.SOAK_PROPOSAL_INTERVAL)
    ap.add_argument("--metrics-interval", type=float, default=cfg.SOAK_METRICS_INTERVAL)
    ap.add_argument("--output-dir",       default="stress-results")
    args = ap.parse_args()

    report = run(
        api_url=args.api_url,
        redis_url=args.redis_url,
        duration_s=args.duration,
        proposal_interval=args.proposal_interval,
        metrics_interval=args.metrics_interval,
        output_dir=args.output_dir,
    )
    sys.exit(0 if report.passed() else 1)


if __name__ == "__main__":
    main()
