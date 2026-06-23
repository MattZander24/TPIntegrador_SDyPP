"""Service for publishing messages to RabbitMQ."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional

from common.blockchain import ACTION_PROMULGACION, compress_text
from common.messaging import build_rabbitmq
from voxchain_api.config import config


class RabbitMQPublisher:
    """Wrapper around messaging for publishing law proposals."""

    def __init__(self):
        self.messaging = build_rabbitmq(config.RABBITMQ_URL)
        self.messaging.connect()

    def publish_law_proposal(
        self,
        author_pubkey: str,
        text: str,
        action: str = ACTION_PROMULGACION,
        law_id: Optional[str] = None,
        text_hash: Optional[str] = None,
        created_at: Optional[str] = None,
        signature: Optional[str] = None,
    ) -> dict:
        """Publish a law proposal to the RabbitMQ queue.

        Forwards the client-signed fields (text_hash, created_at, signature) so the
        NCT can re-verify the signature authoritatively (A-01). For legacy/unsigned
        proposals these are derived server-side, preserving the previous behaviour.
        """
        text_hash = text_hash or hashlib.sha256(text.encode()).hexdigest()
        text_compressed = compress_text(text)
        text_original_len = len(text)

        law = {
            "law_id": law_id or f"ley-{uuid.uuid4().hex[:8]}",
            "author_pubkey": author_pubkey,
            "text_hash": text_hash,
            "text_compressed": text_compressed,
            "text_original_len": text_original_len,
            "created_at": created_at or datetime.now(timezone.utc).isoformat(),
            "action": action,
            "status": "pending_queue",
        }
        if signature:
            law["signature"] = signature

        self.messaging.publish_proposal(law)
        return law

    def close(self):
        """Close the RabbitMQ connection."""
        self.messaging.close()
