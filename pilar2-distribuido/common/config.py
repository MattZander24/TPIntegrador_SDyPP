"""Configuración por variables de entorno (DOC.md: cero credenciales en el repo).

Ningún secreto se hardcodea: las URLs de Redis/RabbitMQ y los parámetros de
gobierno se leen del entorno (inyectado por docker-compose / Kubernetes / Vault).
"""

from __future__ import annotations

import os


def get(name: str, default: str) -> str:
    return os.getenv(name, default)


def get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw not in (None, "") else default


# Infraestructura
RABBITMQ_URL = get("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
REDIS_URL = get("REDIS_URL", "redis://redis:6379/0")

# Gobierno (AGENT.md 3): n es parámetro de config; NUNCA ajuste dinámico por carga.
# n = ceros para promulgar; derogar exige n+1 (lo calcula el dominio).
N_ZEROS = get_int("N_ZEROS", 4)

# Duración de ventana por tipo de acción (AGENT.md 3.7), en segundos.
WINDOW_SECONDS_PROMULGACION = get_int("WINDOW_SECONDS_PROMULGACION", 60)
WINDOW_SECONDS_DEROGACION = get_int("WINDOW_SECONDS_DEROGACION", 90)

# Cooldown (AGENT.md 3.4 / 3.5), medido en cantidad de ventanas.
COOLDOWN_WINDOWS_NEW = get_int("COOLDOWN_WINDOWS_NEW", N_ZEROS)
# Reproposición idéntica: estrictamente mayor que el normal.
COOLDOWN_WINDOWS_REPROPOSED = get_int("COOLDOWN_WINDOWS_REPROPOSED", 2 * N_ZEROS)

# Fragmentación del espacio de nonces (TrP). Barrido por Pilar 3 (1%–50%).
NONCE_SPACE = get_int("NONCE_SPACE", 50_000_000)
FRAGMENT_SIZE = get_int("FRAGMENT_SIZE", 1_000_000)

# Health endpoints
HEALTH_PORT = get_int("HEALTH_PORT", 8080)
