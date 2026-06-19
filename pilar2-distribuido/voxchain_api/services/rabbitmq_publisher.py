"""Service for publishing messages to RabbitMQ."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

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
    ) -> dict:
        """Publish a law proposal to the RabbitMQ queue.

        Replicates the logic from scripts/propose_law.py:
        - Calculate SHA-256 of the text
        - Compress the text
        - Generate law_id if not provided
        - Publish to the 'propuestas' queue
        """
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        text_compressed = compress_text(text)
        text_original_len = len(text)

        law = {
            "law_id": law_id or f"ley-{uuid.uuid4().hex[:8]}",
            "author_pubkey": author_pubkey,
            "text_hash": text_hash,
            "text_compressed": text_compressed,
            "text_original_len": text_original_len,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "action": action,
        }

        self.messaging.publish_proposal(law)
        return law

    def close(self):
        """Close the RabbitMQ connection."""
        self.messaging.close()
