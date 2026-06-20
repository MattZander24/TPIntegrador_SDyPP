"""Métricas Prometheus compartidas entre todos los servicios de VoxChain.

Cada servicio registra sus métricas específicas sobre el registro global.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, registry

REGISTRY = registry.REGISTRY

# ----- NCT -----
nct_proposals_total = Counter(
    "voxchain_nct_proposals_total", "Total de propuestas recibidas",
    namespace="voxchain", subsystem="nct",
)
nct_blocks_sealed_total = Counter(
    "voxchain_nct_blocks_sealed_total", "Bloques sellados",
    namespace="voxchain", subsystem="nct",
)
nct_windows_opened_total = Counter(
    "voxchain_nct_windows_opened_total", "Ventanas de votación abiertas",
    namespace="voxchain", subsystem="nct",
)
nct_windows_closed_total = Counter(
    "voxchain_nct_windows_closed_total", "Ventanas de votación cerradas",
    namespace="voxchain", subsystem="nct",
)
nct_is_leader = Gauge(
    "voxchain_nct_is_leader", "1 si este NCT es el líder actual",
    namespace="voxchain", subsystem="nct",
)

# ----- TrP -----
trp_tasks_published_total = Counter(
    "voxchain_trp_tasks_published_total", "Tareas de minería publicadas",
    namespace="voxchain", subsystem="trp",
)
trp_active_workers = Gauge(
    "voxchain_trp_active_workers",
    "Workers reportando keep-alive actualmente",
    namespace="voxchain", subsystem="trp",
)

# ----- Worker -----
worker_tasks_received_total = Counter(
    "voxchain_worker_tasks_received_total", "Tareas de minería recibidas",
    namespace="voxchain", subsystem="worker",
)
worker_nonces_found_total = Counter(
    "voxchain_worker_nonces_found_total", "Nonces válidos encontrados",
    namespace="voxchain", subsystem="worker",
)
worker_busy = Gauge(
    "voxchain_worker_busy", "1 si el worker está minando actualmente",
    namespace="voxchain", subsystem="worker",
)
worker_has_gpu = Gauge(
    "voxchain_worker_has_gpu", "1 si el worker tiene GPU disponible",
    namespace="voxchain", subsystem="worker",
)

# ----- API -----
api_http_requests_total = Counter(
    "voxchain_api_http_requests_total",
    "Total de requests HTTP por método y ruta",
    namespace="voxchain", subsystem="api",
    labelnames=["method", "path"],
)
api_http_request_duration_seconds = Histogram(
    "voxchain_api_http_request_duration_seconds",
    "Duración de requests HTTP en segundos",
    namespace="voxchain", subsystem="api",
    labelnames=["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
