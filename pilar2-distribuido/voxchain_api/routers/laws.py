"""Router for laws endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from common.blockchain import decompress_text
from voxchain_api.models import Law, LawProposalRequest
from voxchain_api.services.rabbitmq_publisher import RabbitMQPublisher
from voxchain_api.services.redis_reader import RedisReader

router = APIRouter(prefix="/api/laws", tags=["laws"])


def get_redis_reader():
    """Dependency injection for RedisReader."""
    return RedisReader()


def get_rabbitmq_publisher():
    """Dependency injection for RabbitMQPublisher."""
    return RabbitMQPublisher()


@router.get("", response_model=list[Law])
async def get_laws(
    status: Optional[str] = Query(None, description="Filter by status"),
    redis: RedisReader = Depends(get_redis_reader),
):
    """Get all laws, optionally filtered by status."""
    laws = redis.get_laws(status=status)
    return laws


@router.get("/next", response_model=Optional[Law])
async def get_next_law(redis: RedisReader = Depends(get_redis_reader)):
    """Get the next law that will enter a voting window (round-robin order)."""
    return redis.get_next_law()


@router.get("/queue", response_model=list[Law])
async def get_law_queue(redis: RedisReader = Depends(get_redis_reader)):
    """Get the full ordered queue of pending laws."""
    return redis.get_queued_laws()


@router.get("/{law_id}/text", response_class=PlainTextResponse)
async def get_law_text(law_id: str, redis: RedisReader = Depends(get_redis_reader)):
    """Get the decompressed text of a law."""
    law = redis.get_law(law_id)
    if not law:
        raise HTTPException(status_code=404, detail="Law not found")
    compressed = law.get("text_compressed")
    if not compressed:
        raise HTTPException(status_code=404, detail="Law text not available")
    return decompress_text(compressed)


@router.get("/{law_id}", response_model=Law)
async def get_law(law_id: str, redis: RedisReader = Depends(get_redis_reader)):
    """Get a specific law by ID."""
    law = redis.get_law(law_id)
    if not law:
        raise HTTPException(status_code=404, detail="Law not found")
    return law


@router.post("", response_model=Law)
async def propose_law(
    proposal: LawProposalRequest,
    publisher: RabbitMQPublisher = Depends(get_rabbitmq_publisher),
    redis: RedisReader = Depends(get_redis_reader),
):
    """Propose a new law.

    This endpoint replicates the logic from scripts/propose_law.py:
    - Calculates SHA-256 of the text
    - Compresses the text
    - Generates law_id if not provided
    - Publishes to the RabbitMQ 'propuestas' queue
    """
    if redis.store.is_in_cooldown(proposal.author_pubkey):
        cd = redis.store.get_cooldown(proposal.author_pubkey)
        current = redis.store.current_window_number()
        until = cd["cooldown_until_window"]
        raise HTTPException(
            status_code=429,
            detail=(
                f"El autor está en cooldown hasta la ventana {until} "
                f"(ventana actual: {current}). "
                f"Debes esperar {int(until) - current} ventana(s) más."
            ),
        )

    law = publisher.publish_law_proposal(
        author_pubkey=proposal.author_pubkey,
        text=proposal.text,
        action=proposal.action,
        law_id=proposal.law_id,
    )
    publisher.close()
    return law
