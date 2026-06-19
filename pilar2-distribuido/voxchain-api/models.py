"""Pydantic response models for voxchain-api."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Law(BaseModel):
    law_id: str
    author_pubkey: str
    text_hash: str
    text_ref: Optional[str] = None
    text_compressed: Optional[str] = None
    text_original_len: Optional[int] = None
    status: str
    action: str
    created_at: str


class Window(BaseModel):
    voting_window_id: str
    law_id: str
    action: str
    n_zeros_required: int
    opened_at: str
    deadline: str
    partial_hash_base: str
    result: Optional[str] = None
    winning_nonce: Optional[int] = None
    winning_node_or_pool: Optional[str] = None


class Block(BaseModel):
    previous_hash: str
    law_id: str
    action: str
    n_zeros_required: int
    nonce: int
    winning_node_or_pool: str
    voting_window_id: str
    block_hash: str
    timestamp: str


class LawProposalRequest(BaseModel):
    law_id: Optional[str] = None
    author_pubkey: str
    text: str
    action: str = "promulgacion"


class HealthResponse(BaseModel):
    api: str
    nct: str
    trp: str
    redis: str


class SSEEvent(BaseModel):
    event_type: str
    data: dict
