"""Configuration for voxchain-api service."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Config:
    REDIS_URL: str
    RABBITMQ_URL: str
    NCT_HEALTH_URL: str
    PORT: int = 8000

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            REDIS_URL=os.getenv("REDIS_URL", "redis://redis:6379/0"),
            RABBITMQ_URL=os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/"),
            NCT_HEALTH_URL=os.getenv("NCT_HEALTH_URL", "http://coordinator:8080/health"),
            PORT=int(os.getenv("PORT", "8000")),
        )


config = Config.from_env()
