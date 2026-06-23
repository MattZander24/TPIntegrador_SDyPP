"""Métricas Prometheus compartidas entre todos los servicios de VoxChain.

Cada servicio registra sus métricas específicas sobre el registro global.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, registry

REGISTRY = registry.REGISTRY

# ----- NCT -----
nct_proposals_total = Counter(
    "voxchain_nct_proposals_total", "Total de propuestas recibidas",
)
nct_blocks_sealed_total = Counter(
    "voxchain_nct_blocks_sealed_total", "Bloques sellados",
)
nct_windows_opened_total = Counter(
    "voxchain_nct_windows_opened_total", "Ventanas de votación abiertas",
)
nct_windows_closed_total = Counter(
    "voxchain_nct_windows_closed_total", "Ventanas de votación cerradas",
)
nct_is_leader = Gauge(
    "voxchain_nct_is_leader", "1 si este NCT es el líder actual",
)

# ----- TrP -----
trp_tasks_published_total = Counter(
    "voxchain_trp_tasks_published_total", "Tareas de minería publicadas",
)
trp_active_workers = Gauge(
    "voxchain_trp_active_workers",
    "Workers reportando keep-alive actualmente",
)

# ----- Worker -----
worker_tasks_received_total = Counter(
    "voxchain_worker_tasks_received_total", "Tareas de minería recibidas",
)
worker_nonces_found_total = Counter(
    "voxchain_worker_nonces_found_total", "Nonces válidos encontrados",
)
worker_busy = Gauge(
    "voxchain_worker_busy", "1 si el worker está minando actualmente",
)
worker_has_gpu = Gauge(
    "voxchain_worker_has_gpu", "1 si el worker tiene GPU disponible",
)

# ----- API -----
api_http_requests_total = Counter(
    "voxchain_api_http_requests_total",
    "Total de requests HTTP por método y ruta",
    labelnames=["method", "path"],
)
# ----- Pool -----
pool_miners_registered = Gauge(
    "voxchain_pool_miners_registered",
    "Miners registrados actualmente en el pool coordinator",
)
pool_work_distributed_total = Counter(
    "voxchain_pool_work_distributed_total",
    "Sub-tareas de minería distribuidas a miners",
)
pool_nonces_found_total = Counter(
    "voxchain_pool_nonces_found_total",
    "Nonces válidos recibidos de miners del pool",
)
pool_is_leader = Gauge(
    "voxchain_pool_is_leader",
    "1 si este pool coordinator es el líder actual",
)

api_http_request_duration_seconds = Histogram(
    "voxchain_api_http_request_duration_seconds",
    "Duración de requests HTTP en segundos",
    labelnames=["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
