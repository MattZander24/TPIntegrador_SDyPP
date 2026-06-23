"""Configuration for voxchain-api service."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(raw: str | None, default: bool) -> bool:
    if raw in (None, ""):
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    REDIS_URL: str
    RABBITMQ_URL: str
    NCT_HEALTH_URL: str
    PORT: int = 8000
    # Firma de propuestas (A-01). Si True, el API rechaza propuestas sin firma
    # válida antes de publicarlas. Debe ir alineado con el flag del NCT.
    REQUIRE_SIGNATURES: bool = False

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            REDIS_URL=os.getenv("REDIS_URL", "redis://redis:6379/0"),
            RABBITMQ_URL=os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/"),
            NCT_HEALTH_URL=os.getenv("NCT_HEALTH_URL", "http://coordinator:8080/health"),
            PORT=int(os.getenv("PORT", "8000")),
            REQUIRE_SIGNATURES=_as_bool(os.getenv("REQUIRE_SIGNATURES"), False),
        )


config = Config.from_env()
