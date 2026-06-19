"""Router for chain endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from voxchain_api.models import Block
from voxchain_api.services.redis_reader import RedisReader

router = APIRouter(prefix="/api/chain", tags=["chain"])


def get_redis_reader():
    """Dependency injection for RedisReader."""
    return RedisReader()


@router.get("", response_model=list[Block])
async def get_chain(redis: RedisReader = Depends(get_redis_reader)):
    """Get all blocks in the chain, in order."""
    chain = redis.get_chain()
    return chain


@router.get("/{block_hash}", response_model=Block)
async def get_block(block_hash: str, redis: RedisReader = Depends(get_redis_reader)):
    """Get a specific block by hash."""
    block = redis.get_block(block_hash)
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")
    return block
