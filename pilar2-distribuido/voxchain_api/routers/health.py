"""Router for health endpoints."""

from __future__ import annotations

import httpx

from fastapi import APIRouter, Depends

from voxchain_api.config import config
from voxchain_api.models import HealthResponse
from voxchain_api.services.redis_reader import RedisReader

router = APIRouter(prefix="/api/health", tags=["health"])


def get_redis_reader():
    """Dependency injection for RedisReader."""
    return RedisReader()


@router.get("", response_model=HealthResponse)
async def get_health(redis: RedisReader = Depends(get_redis_reader)):
    """Get unified health status of all services."""
    # Check Redis
    redis_status = "ok" if redis.ping() else "error"

    # Check NCT
    nct_status = "ok"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(config.NCT_HEALTH_URL, timeout=2.0)
            nct_status = "ok" if response.status_code == 200 else "error"
    except Exception:
        nct_status = "error"

    return HealthResponse(
        api="ok",
        nct=nct_status,
        redis=redis_status,
    )
