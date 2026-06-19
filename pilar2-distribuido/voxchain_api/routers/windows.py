"""Router for windows endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from voxchain_api.models import Window
from voxchain_api.services.redis_reader import RedisReader

router = APIRouter(prefix="/api/windows", tags=["windows"])


def get_redis_reader():
    """Dependency injection for RedisReader."""
    return RedisReader()


@router.get("/active", response_model=Window)
async def get_active_window(redis: RedisReader = Depends(get_redis_reader)):
    """Get the currently active voting window."""
    window = redis.get_active_window()
    if not window:
        raise HTTPException(status_code=404, detail="No active window")
    return window


@router.get("/{voting_window_id}", response_model=Window)
async def get_window(
    voting_window_id: str, redis: RedisReader = Depends(get_redis_reader)
):
    """Get a specific window by ID."""
    window = redis.get_window(voting_window_id)
    if not window:
        raise HTTPException(status_code=404, detail="Window not found")
    return window
