"""Escenario 2 — Mining Race: atomicidad del cierre de ventana bajo concurrencia.

Pregunta clave: cuando N workers encuentran el nonce casi simultáneamente,
¿el sistema garantiza que se sella EXACTAMENTE UN bloque por ventana?

Protocolo del test:
1. Envía una propuesta al API para crear una ventana activa.
2. Espera a que el NCT abra la ventana y publique el desafío en `desafio_activo`.
3. Lanza RACE_CONCURRENT_WORKERS threads, cada uno publica el nonce correcto
   a la cola `respuesta_nonce` con un pequeño jitter (0-100 ms).
4. Espera a que la ventana se cierre.
5. Verifica (vía API o Redis) que:
   - La cadena creció en exactamente 1 bloque.
   - No hay dos bloques con el mismo `voting_window_id`.
   - El `window_sealed:{id}` existe exactamente una vez.

Requisitos:
    kubectl port-forward svc/redis   6379:6379  -n voxchain  (para Redis directo)
    kubectl port-forward svc/rabbitmq 5672:5672 -n voxchain  (para RabbitMQ directo)
    O configurar REDIS_URL / RABBITMQ_URL apuntando al LoadBalancer.

Uso:
    cd tests/stress
    python scenarios/mining_race.py
    python scenarios/mining_race.py --workers 50 --n-zeros 1
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import os
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests

import config as cfg
from helpers.law_generator import UnsignedIdentity, unique_text
from helpers.report import StressReport

# ── Parámetros de la prueba ────────────────────────────────────────────────
DEFAULT_N_ZEROS  = 1   # PoW trivial: garantiza que todos los workers encuentren el nonce
DEFAULT_JITTER_S = 0.1 # máximo jitter entre envíos de nonce (simula llegada concurrente)
WINDOW_WAIT_S    = 60  # máximo tiempo esperando que el NCT abra la ventana
SEAL_WAIT_S      = 30  # máximo tiempo esperando que la ventana se cierre


def _submit_proposal(api_url: str, identity: UnsignedIdentity) -> str:
    """Envía una propuesta y devuelve el law_id."""
    payload = identity.make_proposal(unique_text("race"), action="promulgacion")
    resp = requests.post(f"{api_url}/api/laws", json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()["law_id"]


def _wait_for_active_window(api_url: str, timeout: float) -> dict | None:
    """Espera hasta que el NCT abra una ventana activa y devuelve el desafío."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{api_url}/api/windows", timeout=5)
            if r.ok:
                windows = r.json()
                active = [w for w in windows if w.get("result") is None]
                if active:
                    return active[0]
        except Exception:
            pass
        time.sleep(1)
    return None


def _wait_for_window_sealed(api_url: str, window_id: str, timeout: float) -> bool:
    """Espera hasta que la ventana quede sellada (result != None)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{api_url}/api/windows", timeout=5)
            if r.ok:
                windows = r.json()
                for w in windows:
                    if w.get("voting_window_id") == window_id:
                        if w.get("result") is not None:
                            return True
        except Exception:
            pass
        time.sleep(1)
    return False


def _publish_nonce_via_rabbitmq(rmq_url: str, payload: dict) -> None:
    """Publica un mensaje a la cola respuesta_nonce via pika."""
    import pika

    params = pika.URLParameters(rmq_url)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    ch.basic_publish(
        exchange="",
        routing_key="respuesta_nonce",
        body=json.dumps(payload),
        properties=pika.BasicProperties(delivery_mode=2),
    )
    conn.close()


def run(n_workers: int, api_url: str, rmq_url: str, n_zeros: int,
        jitter_s: float) -> StressReport:
    report = StressReport("mining_race")
    print(f"\n[race] Iniciando con {n_workers} workers concurrentes, n_zeros={n_zeros}")

    # 1. Propuesta → ventana activa
    identity = UnsignedIdentity()
    print("[race] Enviando propuesta...")
    try:
        law_id = _submit_proposal(api_url, identity)
    except Exception as e:
        print(f"[race] ERROR al enviar propuesta: {e}")
        report.add_check("propuesta_enviada", False, True, False)
        return report

    print(f"[race] Ley {law_id!r} enviada. Esperando ventana...")
    window = _wait_for_active_window(api_url, WINDOW_WAIT_S)
    if not window:
        print("[race] ERROR: no se abrió ventana en el tiempo límite.")
        report.add_check("ventana_abierta", False, True, False)
        return report

    window_id = window["voting_window_id"]
    base = window["partial_hash_base"]
    required_zeros = window.get("n_zeros_required", n_zeros)
    print(f"[race] Ventana activa: {window_id!r} (n_zeros={required_zeros})")

    # 2. Resolver el PoW (con n_zeros=1 es trivial)
    from common.blockchain.challenge import compute_hash, prefix_for_zeros
    prefix = prefix_for_zeros(required_zeros)
    nonce = next(
        n for n in range(10_000_000)
        if compute_hash(base, n).startswith(prefix)
    )
    print(f"[race] Nonce encontrado: {nonce}")

    # 3. N workers publican concurrentemente con jitter
    errors: list[str] = []
    lock = threading.Lock()

    def worker_thread(worker_id: str) -> None:
        time.sleep(random.uniform(0, jitter_s))
        payload = {
            "voting_window_id": window_id,
            "nonce": nonce,
            "winning_node_or_pool": worker_id,
            "block_hash_candidato": compute_hash(base, nonce),
        }
        try:
            _publish_nonce_via_rabbitmq(rmq_url, payload)
        except Exception as e:
            with lock:
                errors.append(f"{worker_id}: {e}")

    t_start = time.time()
    threads = [
        threading.Thread(
            target=worker_thread,
            args=(f"race-worker-{i}",),
            daemon=True,
        )
        for i in range(n_workers)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    t_publish = time.time() - t_start
    print(f"[race] {n_workers} nonces publicados en {t_publish:.2f}s")

    # 4. Esperar cierre de ventana
    sealed = _wait_for_window_sealed(api_url, window_id, SEAL_WAIT_S)

    # 5. Verificar invariantes
    time.sleep(2)  # Dar tiempo al NCT para persistir el bloque
    chain_resp = requests.get(f"{api_url}/api/chain", timeout=10)
    chain = chain_resp.json() if chain_resp.ok else []

    blocks_for_window = [b for b in chain if b.get("voting_window_id") == window_id]
    n_blocks = len(blocks_for_window)

    report.check_eq("ventana_sellada",       sealed, True)
    report.check_eq("bloques_por_ventana",   n_blocks, 1,
                    " (esperado exactamente 1)")
    report.check_lte("errores_de_publicacion", len(errors), 0)
    report.check_lte("tiempo_publicacion_s", t_publish, jitter_s + 1, "s")

    if n_blocks > 1:
        print(f"[race] ALERTA: se crearon {n_blocks} bloques para la misma ventana!")
    elif n_blocks == 1:
        winner = blocks_for_window[0].get("winning_node_or_pool", "?")
        print(f"[race] Bloque sellado correctamente. Ganador: {winner!r}")
    else:
        print("[race] ALERTA: ningún bloque fue sellado.")

    report.extra["window_id"]      = window_id
    report.extra["n_workers"]      = n_workers
    report.extra["nonce"]          = nonce
    report.extra["publish_errors"] = errors
    report.extra["blocks_created"] = n_blocks

    report.print()
    report.save()
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="Mining race — stress test de atomicidad")
    ap.add_argument("--workers",  type=int,   default=cfg.RACE_CONCURRENT_WORKERS)
    ap.add_argument("--api-url",  default=cfg.API_BASE_URL)
    ap.add_argument("--rmq-url",  default=cfg.RABBITMQ_URL)
    ap.add_argument("--n-zeros",  type=int,   default=DEFAULT_N_ZEROS)
    ap.add_argument("--jitter",   type=float, default=DEFAULT_JITTER_S)
    args = ap.parse_args()

    report = run(
        n_workers=args.workers,
        api_url=args.api_url,
        rmq_url=args.rmq_url,
        n_zeros=args.n_zeros,
        jitter_s=args.jitter,
    )
    sys.exit(0 if report.passed() else 1)


if __name__ == "__main__":
    main()
