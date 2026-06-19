"""Service for reading state from Redis."""

from __future__ import annotations

from typing import Optional

from common.queue import select_next_law
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
        all_laws = self.store.all_laws()
        if status:
            return [law for law in all_laws if law.get("status") == status]
        return all_laws

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

    def get_queued_laws(self) -> list[dict]:
        """Get all queued laws in order (oldest first)."""
        return self.store.queued_laws()

    def get_next_law(self) -> Optional[dict]:
        """Get the next law that will enter a voting window (round-robin)."""
        pending = self.store.queued_laws()
        last_author = self.store.get_last_author()
        return select_next_law(pending, last_author)

    def get_queue_position(self, law_id: str) -> Optional[int]:
        """Get the position of a law in the queue (0-based, None if not queued)."""
        ids = self.store.queued_law_ids()
        try:
            return ids.index(law_id)
        except ValueError:
            return None

    def current_window_number(self) -> int:
        """Get the current window number."""
        return self.store.current_window_number()
