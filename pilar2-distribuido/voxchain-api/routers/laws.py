"""Router for laws endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

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
):
    """Propose a new law.

    This endpoint replicates the logic from scripts/propose_law.py:
    - Calculates SHA-256 of the text
    - Compresses the text
    - Generates law_id if not provided
    - Publishes to the RabbitMQ 'propuestas' queue
    """
    law = publisher.publish_law_proposal(
        author_pubkey=proposal.author_pubkey,
        text=proposal.text,
        action=proposal.action,
        law_id=proposal.law_id,
    )
    publisher.close()
    return law
