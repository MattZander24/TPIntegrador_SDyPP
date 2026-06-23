"""Configuración central de la suite de stress tests.

Todas las variables son sobreescribibles por variables de entorno.  Para
correr contra GKE real, exportar al menos VOXCHAIN_API_URL.  Redis y
RabbitMQ se alcanzan vía `kubectl port-forward` (ver README).

Ejemplo mínimo GKE:
    export VOXCHAIN_API_URL=https://<ingress-ip>
    export REDIS_URL=redis://localhost:6379/0        # kubectl port-forward
    export RABBITMQ_URL=amqp://user:pass@localhost:5672/  # kubectl port-forward
"""

from __future__ import annotations

import os


def _int(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))


def _float(key: str, default: float) -> float:
    return float(os.getenv(key, str(default)))


def _str(key: str, default: str) -> str:
    return os.getenv(key, default)


def _bool(key: str, default: bool) -> bool:
    return os.getenv(key, str(default)).lower() in ("1", "true", "yes")


# ── Endpoints ──────────────────────────────────────────────────────────────
API_BASE_URL     = _str("VOXCHAIN_API_URL",  "http://localhost:8000")
REDIS_URL        = _str("REDIS_URL",          "redis://localhost:6379/0")
RABBITMQ_URL     = _str("RABBITMQ_URL",       "amqp://guest:guest@localhost:5672/")
K8S_NAMESPACE    = _str("K8S_NAMESPACE",      "voxchain")
NCT_PRIMARY_LABEL = _str("NCT_PRIMARY_LABEL", "app=nct-coordinator,nct-mode=primary")

# ── Locust ─────────────────────────────────────────────────────────────────
LOCUST_USERS       = _int("LOCUST_USERS",       20)
LOCUST_SPAWN_RATE  = _int("LOCUST_SPAWN_RATE",   2)
LOCUST_RUN_TIME    = _str("LOCUST_RUN_TIME",    "5m")

# ── SLOs (objetivos de nivel de servicio) ──────────────────────────────────
SLO_P95_LATENCY_MS   = _int("SLO_P95_MS",          500)   # POST /api/laws < 500 ms P95
SLO_ERROR_RATE_PCT   = _float("SLO_ERROR_RATE_PCT",  1.0)  # < 1% errores HTTP
SLO_MAX_QUEUE_DEPTH  = _int("SLO_MAX_QUEUE_DEPTH",  200)   # leyes pendientes < 200
SLO_FAILOVER_SECS    = _int("SLO_FAILOVER_SECS",     30)   # NCT failover < 30s

# ── Parámetros de escenarios ───────────────────────────────────────────────
# Escenario 2 — mining race
RACE_CONCURRENT_WORKERS = _int("RACE_CONCURRENT_WORKERS", 30)

# Escenario 3 — failover under load
FAILOVER_PROPOSAL_INTERVAL_S = _float("FAILOVER_PROPOSAL_INTERVAL", 1.5)
FAILOVER_WARMUP_BLOCKS       = _int("FAILOVER_WARMUP_BLOCKS",        3)
FAILOVER_RECOVERY_TIMEOUT_S  = _int("FAILOVER_RECOVERY_TIMEOUT",    60)

# Escenario 5 — soak
SOAK_DURATION_S        = _int("SOAK_DURATION_SECONDS",   1800)  # 30 min
SOAK_PROPOSAL_INTERVAL = _float("SOAK_PROPOSAL_INTERVAL",  2.0)
SOAK_METRICS_INTERVAL  = _float("SOAK_METRICS_INTERVAL",   10.0)

# ── Firmas ─────────────────────────────────────────────────────────────────
# Si USE_SIGNATURES=true, cada propuesta se firma con ECDSA P-256.
# Requiere que el cluster tenga REQUIRE_SIGNATURES=false (acepta ambas).
# Útil para medir el overhead de firma bajo carga.
USE_SIGNATURES = _bool("USE_SIGNATURES", False)

# Cuántas identidades distintas usa el stress test (evita cooldown cruzado).
NUM_IDENTITIES = _int("NUM_IDENTITIES", 50)
