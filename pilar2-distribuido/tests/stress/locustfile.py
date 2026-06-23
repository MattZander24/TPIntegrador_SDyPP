"""Escenarios de carga HTTP para VoxChain — Locust.

Cómo correr:
    # modo interactivo (dashboard en http://localhost:8089)
    cd tests/stress
    locust -f locustfile.py

    # modo headless contra GKE
    export VOXCHAIN_API_URL=https://<ingress-ip>
    locust -f locustfile.py \
        --headless \
        --users 20 --spawn-rate 2 --run-time 5m \
        --host $VOXCHAIN_API_URL \
        --csv stress-results/load

Clases disponibles (seleccionar con --class-picker o en el UI):
    ProposalUser    — flujo realista: propone leyes a ritmo moderado
    ReaderUser      — martilleo de endpoints de lectura (chain, laws, health)
    PowerUser       — mezcla de escritura + lectura
    FloodUser       — tasa máxima de propuestas (encuentra el límite de saturación)
"""

from __future__ import annotations

import random
import sys
import os

# Permite importar helpers sin instalar el paquete
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from locust import HttpUser, TaskSet, between, constant, events, task

import config as cfg
from helpers.law_generator import IdentityPool, unique_text

# Pool de identidades compartido entre todas las instancias de usuarios.
# Cada identidad tiene su propio author_pubkey → cooldowns independientes.
_IDENTITY_POOL = IdentityPool(n=cfg.NUM_IDENTITIES, signed=cfg.USE_SIGNATURES)
_proposal_seq = 0


def _next_proposal() -> dict:
    global _proposal_seq
    _proposal_seq += 1
    identity = _IDENTITY_POOL.next()
    return identity.make_proposal(
        text=unique_text("load", _proposal_seq),
        action=random.choice(["promulgacion", "promulgacion", "promulgacion"]),
        # promulgacion 3x más frecuente que derogacion (requiere ley previa)
    )


# ── ProposalUser ──────────────────────────────────────────────────────────

class ProposalUser(HttpUser):
    """Usuario realista que propone leyes a ritmo moderado.

    Simula un ciudadano que propone una ley, espera un rato, y lee el estado.
    Peso: escritura 60% / lectura 40%.

    SLO objetivo: P95 < 500 ms, error_rate < 1%.
    """

    wait_time = between(1, 4)
    weight = 3

    @task(3)
    def propose_law(self):
        payload = _next_proposal()
        with self.client.post(
            "/api/laws",
            json=payload,
            catch_response=True,
            name="/api/laws [POST]",
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 429:
                # Cooldown activo — no es un fallo del sistema
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:120]}")

    @task(2)
    def read_chain(self):
        with self.client.get(
            "/api/chain",
            catch_response=True,
            name="/api/chain [GET]",
        ) as resp:
            if resp.ok:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(1)
    def read_laws(self):
        with self.client.get(
            "/api/laws",
            catch_response=True,
            name="/api/laws [GET]",
        ) as resp:
            if resp.ok:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(1)
    def health_check(self):
        with self.client.get(
            "/api/health",
            catch_response=True,
            name="/api/health [GET]",
        ) as resp:
            if resp.ok:
                data = resp.json()
                if data.get("redis") == "error":
                    resp.failure("Redis reporta error en /health")
                else:
                    resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")


# ── ReaderUser ────────────────────────────────────────────────────────────

class ReaderUser(HttpUser):
    """Martillea los endpoints de lectura sin proponer nada.

    Simula usuarios que solo consultan el estado de la blockchain.
    Verifica que las lecturas no se degraden bajo carga mixta.
    """

    wait_time = between(0.5, 2)
    weight = 2

    @task(4)
    def get_chain(self):
        self.client.get("/api/chain", name="/api/chain [GET]")

    @task(3)
    def get_laws(self):
        self.client.get("/api/laws", name="/api/laws [GET]")

    @task(2)
    def get_queue(self):
        self.client.get("/api/laws/queue", name="/api/laws/queue [GET]")

    @task(1)
    def get_health(self):
        self.client.get("/api/health", name="/api/health [GET]")


# ── FloodUser ─────────────────────────────────────────────────────────────

class FloodUser(HttpUser):
    """Propone a la máxima tasa posible para encontrar el punto de saturación.

    Usar con pocos usuarios (5-10) para no exceder la capacidad de Redis/RabbitMQ.
    Mide: throughput real del API y tasa de errores bajo saturación.
    """

    wait_time = constant(0.05)  # 20 req/s por usuario
    weight = 1

    @task
    def flood_proposal(self):
        payload = _next_proposal()
        with self.client.post(
            "/api/laws",
            json=payload,
            catch_response=True,
            name="/api/laws [POST flood]",
        ) as resp:
            if resp.status_code in (200, 429):
                resp.success()
            elif resp.status_code == 503:
                resp.failure("API sobrecargada (503)")
            else:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:80]}")


# ── PowerUser ─────────────────────────────────────────────────────────────

class PowerUser(HttpUser):
    """Usuario avanzado: propone, lee y consulta leyes específicas.

    Verifica el pipeline completo desde propuesta hasta visualización.
    """

    wait_time = between(2, 5)
    weight = 2

    def on_start(self):
        self._submitted_law_ids: list[str] = []

    @task(2)
    def propose_and_track(self):
        payload = _next_proposal()
        with self.client.post(
            "/api/laws",
            json=payload,
            catch_response=True,
            name="/api/laws [POST]",
        ) as resp:
            if resp.status_code == 200:
                resp.success()
                try:
                    law_id = resp.json().get("law_id")
                    if law_id:
                        self._submitted_law_ids.append(law_id)
                        # Mantener la lista acotada
                        if len(self._submitted_law_ids) > 20:
                            self._submitted_law_ids.pop(0)
                except Exception:
                    pass
            elif resp.status_code == 429:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(3)
    def poll_submitted_law(self):
        """Lee una ley ya enviada para ver su status (pending → promulgated)."""
        if not self._submitted_law_ids:
            return
        law_id = random.choice(self._submitted_law_ids)
        with self.client.get(
            f"/api/laws/{law_id}",
            catch_response=True,
            name="/api/laws/{id} [GET]",
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(1)
    def get_chain_length(self):
        with self.client.get(
            "/api/chain",
            catch_response=True,
            name="/api/chain [GET]",
        ) as resp:
            if resp.ok:
                chain = resp.json()
                if len(chain) > 10_000:
                    # Detectar crecimiento anómalo
                    resp.failure(f"Cadena anormalmente larga: {len(chain)} bloques")
                else:
                    resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")


# ── Hooks de Locust ───────────────────────────────────────────────────────

@events.quitting.add_listener
def evaluate_slos(environment, **kwargs):
    """Evalúa los SLOs al terminar la prueba y sale con código 1 si fallan."""
    stats = environment.runner.stats.total
    if stats.num_requests == 0:
        print("[SLO] Sin requests registrados.")
        return

    errors = stats.num_failures
    total  = stats.num_requests
    error_pct = errors / total * 100
    p95_ms = stats.get_response_time_percentile(0.95)

    print("\n" + "=" * 55)
    print("EVALUACIÓN DE SLOs")
    print("=" * 55)

    slo_ok = True

    def check(name, value, threshold, unit=""):
        nonlocal slo_ok
        ok = value <= threshold
        icon = "PASS" if ok else "FAIL"
        print(f"  [{icon}] {name}: {value:.2f}{unit} (umbral: {threshold}{unit})")
        if not ok:
            slo_ok = False

    check("Tasa de error",   error_pct,              cfg.SLO_ERROR_RATE_PCT, "%")
    check("P95 latencia",    (p95_ms or 0) / 1000,   cfg.SLO_P95_LATENCY_MS / 1000, "s")

    print("=" * 55)
    print(f"Veredicto: {'PASSED' if slo_ok else 'FAILED'}")

    if not slo_ok:
        environment.process_exit_code = 1
