"""Escenario 3 — Failover under load: tolerancia a fallos del NCT bajo carga.

Pregunta clave: cuando el NCT primario cae mientras hay propuestas en vuelo,
¿el standby toma el control en < SLO_FAILOVER_SECS segundos y el sistema
se recupera sin pérdida de consistencia?

Protocolo:
1. Espera warm-up: envía propuestas hasta que se sellen FAILOVER_WARMUP_BLOCKS bloques.
2. Registra el número de bloques y la longitud de la cadena como baseline.
3. Mata el pod del NCT primario (`kubectl delete pod`).
4. Continúa enviando propuestas mientras mide:
   - Cuándo el standby empieza a emitir heartbeats (primer bloque nuevo).
   - Tiempo entre la muerte y el primer bloque sellado por el nuevo líder.
5. Verifica que:
   - El failover ocurrió dentro de SLO_FAILOVER_SECS.
   - La cadena creció al menos 1 bloque después del failover.
   - No hay bloques duplicados (window_id único en la cadena).
   - /api/health reporta nct=ok tras el failover.

Requisitos:
    kubectl configurado con acceso al cluster GKE (gcloud container clusters get-credentials).
    El pod del NCT primario debe tener label app=nct-coordinator,nct-mode=primary
    (configurable con NCT_PRIMARY_LABEL en el entorno).

Uso:
    cd tests/stress
    python scenarios/failover_under_load.py
    python scenarios/failover_under_load.py --warmup-blocks 2 --proposal-interval 1.0
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import os
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests

import config as cfg
from helpers.law_generator import IdentityPool, unique_text
from helpers.report import StressReport


# ── Helpers ────────────────────────────────────────────────────────────────

def _chain_length(api_url: str) -> int:
    try:
        r = requests.get(f"{api_url}/api/chain", timeout=5)
        return len(r.json()) if r.ok else 0
    except Exception:
        return 0


def _health(api_url: str) -> dict:
    try:
        r = requests.get(f"{api_url}/api/health", timeout=5)
        return r.json() if r.ok else {}
    except Exception:
        return {}


def _wait_for_n_blocks(api_url: str, n: int, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _chain_length(api_url) >= n:
            return True
        time.sleep(2)
    return False


def _kill_nct_primary(namespace: str, label: str) -> tuple[bool, str]:
    """Borra el pod del NCT primario usando kubectl y retorna (éxito, output)."""
    cmd = [
        "kubectl", "delete", "pod",
        "-l", label,
        "-n", namespace,
        "--grace-period=0",
        "--force",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        output = result.stdout + result.stderr
        return result.returncode == 0, output.strip()
    except subprocess.TimeoutExpired:
        return False, "kubectl timed out"
    except FileNotFoundError:
        return False, "kubectl no encontrado en PATH"


def _get_chain(api_url: str) -> list:
    try:
        r = requests.get(f"{api_url}/api/chain", timeout=10)
        return r.json() if r.ok else []
    except Exception:
        return []


# ── Productor de propuestas en background ─────────────────────────────────

class ProposalProducer:
    """Envía propuestas en un thread de fondo a ritmo constante."""

    def __init__(self, api_url: str, interval_s: float, identity_pool: IdentityPool):
        self._api = api_url
        self._interval = interval_s
        self._pool = identity_pool
        self._stop = threading.Event()
        self._sent = 0
        self._errors = 0
        self._seq = 0
        self._lock = threading.Lock()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="proposal-producer"
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=self._interval + 2)

    def stats(self) -> tuple[int, int]:
        with self._lock:
            return self._sent, self._errors

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                identity = self._pool.next()
                with self._lock:
                    self._seq += 1
                    seq = self._seq
                payload = identity.make_proposal(
                    text=unique_text("failover", seq),
                    action="promulgacion",
                )
                resp = requests.post(
                    f"{self._api}/api/laws", json=payload, timeout=8
                )
                with self._lock:
                    if resp.status_code in (200, 429):
                        self._sent += 1
                    else:
                        self._errors += 1
            except Exception:
                with self._lock:
                    self._errors += 1
            self._stop.wait(self._interval)


# ── Escenario principal ────────────────────────────────────────────────────

def run(
    api_url: str,
    namespace: str,
    nct_label: str,
    warmup_blocks: int,
    proposal_interval: float,
    recovery_timeout: float,
    failover_slo_s: float,
) -> StressReport:
    report = StressReport("failover_under_load")
    pool = IdentityPool(n=cfg.NUM_IDENTITIES, signed=False)
    producer = ProposalProducer(api_url, proposal_interval, pool)

    # ── Warm-up ────────────────────────────────────────────────────────────
    print(f"\n[failover] Iniciando warm-up: esperando {warmup_blocks} bloques sellados...")
    producer.start()

    ok = _wait_for_n_blocks(api_url, warmup_blocks, timeout=300)
    if not ok:
        producer.stop()
        print("[failover] ERROR: warm-up no completado en 5 min.")
        report.add_check("warmup_completado", False, True, False)
        return report

    baseline_chain = _chain_length(api_url)
    sent_before, err_before = producer.stats()
    print(f"[failover] Warm-up OK. Cadena: {baseline_chain} bloques. "
          f"Propuestas enviadas: {sent_before}")

    # ── Kill NCT primary ───────────────────────────────────────────────────
    print(f"[failover] Matando NCT primario (kubectl -l {nct_label})...")
    t_kill = time.time()
    kill_ok, kill_output = _kill_nct_primary(namespace, nct_label)
    print(f"[failover] kubectl output: {kill_output}")

    if not kill_ok:
        producer.stop()
        print("[failover] ERROR: no se pudo matar el NCT primario.")
        report.add_check("nct_pod_eliminado", False, True, False)
        report.extra["kubectl_output"] = kill_output
        return report

    print(f"[failover] Pod eliminado. Esperando failover (SLO: {failover_slo_s}s)...")

    # ── Detectar failover (primer bloque nuevo post-kill) ──────────────────
    t_failover: float | None = None
    deadline = t_kill + recovery_timeout
    while time.time() < deadline:
        current_len = _chain_length(api_url)
        if current_len > baseline_chain:
            t_failover = time.time()
            print(f"[failover] ¡Failover detectado! Nuevo bloque en cadena "
                  f"({baseline_chain} → {current_len})")
            break
        health = _health(api_url)
        nct_status = health.get("nct", "?")
        elapsed = time.time() - t_kill
        print(f"[failover] Esperando... {elapsed:.0f}s | nct={nct_status} | "
              f"chain={current_len}")
        time.sleep(3)

    producer.stop()
    sent_after, err_after = producer.stats()

    # ── Verificaciones ─────────────────────────────────────────────────────
    failover_time = (t_failover - t_kill) if t_failover else recovery_timeout + 1
    new_blocks = _chain_length(api_url) - baseline_chain

    # Detectar bloques duplicados (mismo voting_window_id)
    chain = _get_chain(api_url)
    window_ids = [b.get("voting_window_id") for b in chain]
    unique_ids = set(window_ids)
    has_duplicates = len(window_ids) != len(unique_ids)

    # Estado de salud final
    final_health = _health(api_url)
    nct_ok = final_health.get("nct") == "ok"

    report.check_lte("tiempo_failover_s",     failover_time, failover_slo_s, "s")
    report.check_gte("bloques_post_failover",  new_blocks,    1)
    report.check_eq("cadena_sin_duplicados",   not has_duplicates, True)
    report.check_eq("nct_health_ok",           nct_ok, True)
    report.check_lte("errores_propuestas_pct",
                     (err_after - err_before) / max(sent_after - sent_before, 1) * 100,
                     20.0, "%")

    report.extra["baseline_chain_length"] = baseline_chain
    report.extra["final_chain_length"]    = _chain_length(api_url)
    report.extra["new_blocks"]            = new_blocks
    report.extra["failover_time_s"]       = round(failover_time, 2)
    report.extra["proposals_total"]       = sent_after
    report.extra["proposals_errors"]      = err_after
    report.extra["final_health"]          = final_health

    report.print()
    report.save()
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="Failover under load — stress test NCT")
    ap.add_argument("--api-url",          default=cfg.API_BASE_URL)
    ap.add_argument("--namespace",        default=cfg.K8S_NAMESPACE)
    ap.add_argument("--nct-label",        default=cfg.NCT_PRIMARY_LABEL)
    ap.add_argument("--warmup-blocks",    type=int,   default=cfg.FAILOVER_WARMUP_BLOCKS)
    ap.add_argument("--proposal-interval",type=float, default=cfg.FAILOVER_PROPOSAL_INTERVAL_S)
    ap.add_argument("--recovery-timeout", type=float, default=cfg.FAILOVER_RECOVERY_TIMEOUT_S)
    ap.add_argument("--failover-slo",     type=float, default=cfg.SLO_FAILOVER_SECS)
    args = ap.parse_args()

    report = run(
        api_url=args.api_url,
        namespace=args.namespace,
        nct_label=args.nct_label,
        warmup_blocks=args.warmup_blocks,
        proposal_interval=args.proposal_interval,
        recovery_timeout=args.recovery_timeout,
        failover_slo_s=args.failover_slo,
    )
    sys.exit(0 if report.passed() else 1)


if __name__ == "__main__":
    main()
