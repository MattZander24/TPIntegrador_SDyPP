"""Service for reading state from Redis."""

from __future__ import annotations

from typing import Optional

from common.storage.redis_store import VoxChainStore, connect_redis
from voxchain_api.config import config


class RedisReader:
    """Wrapper around VoxChainStore for API layer."""

    def __init__(self):
        self.store = VoxChainStore(connect_redis(config.REDIS_URL))

    def ping(self) -> bool:
        return self.store.ping()

    def get_chain(self) -> list[dict]:
        """Get all blocks in the chain."""
        blocks = self.store.get_chain()
        return [b.to_dict() for b in blocks]

    def get_block(self, block_hash: str) -> Optional[dict]:
        """Get a specific block by hash."""
        block = self.store.get_block(block_hash)
        return block.to_dict() if block else None

    def get_laws(self, status: Optional[str] = None) -> list[dict]:
        """Get all laws, optionally filtered by status."""
        if status:
            # Get all laws and filter by status
            # Note: Redis doesn't have a direct index on status, so we scan
            # In production, you'd want a separate index
            all_laws = []
            for law_id in self.store.queued_law_ids():
                law = self.store.get_law(law_id)
                if law and law.get("status") == status:
                    all_laws.append(law)
            # Also check promulgated/repealed laws (not in queue)
            # For simplicity, we'll return queued laws for now
            # A full implementation would scan all law:* keys
            return all_laws
        else:
            return self.store.queued_laws()

    def get_law(self, law_id: str) -> Optional[dict]:
        """Get a specific law by ID."""
        return self.store.get_law(law_id)

    def get_active_window(self) -> Optional[dict]:
        """Get the currently active voting window."""
        window_id = self.store.get_active_window()
        if window_id:
            return self.store.get_window(window_id)
        return None

    def get_window(self, voting_window_id: str) -> Optional[dict]:
        """Get a specific window by ID."""
        return self.store.get_window(voting_window_id)

    def chain_length(self) -> int:
        """Get the current length of the chain."""
        return self.store.chain_length()

    def current_window_number(self) -> int:
        """Get the current window number."""
        return self.store.current_window_number()
