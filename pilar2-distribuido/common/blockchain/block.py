"""Modelo de bloque de VoxChain (AGENT.md 7.3).

Cada bloque sella el resultado de una ventana de votación resuelta: la ley
afectada, la acción (promulgación/derogación), la dificultad exigida, el nonce
ganador y quién lo encontró. ``block_hash`` se calcula sobre el contenido del
bloque y encadena con ``previous_hash`` el bloque anterior.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

# Campos que entran al cálculo de block_hash, en orden canónico fijo.
# previous_hash entra primero para que el hash dependa del bloque anterior
# (encadenamiento). block_hash NO se incluye a sí mismo.
_HASHED_FIELDS = (
    "previous_hash",
    "law_id",
    "action",
    "n_zeros_required",
    "nonce",
    "winning_node_or_pool",
    "voting_window_id",
    "timestamp",
)

# Hash del "bloque génesis virtual": previous_hash del primer bloque real.
GENESIS_PREVIOUS_HASH = "0" * 64


@dataclass
class Block:
    previous_hash: str
    law_id: str
    action: str
    n_zeros_required: int
    nonce: int
    winning_node_or_pool: str
    voting_window_id: str
    timestamp: str
    block_hash: str = ""

    def compute_block_hash(self) -> str:
        """Hash determinístico del contenido del bloque (sin incluir block_hash)."""
        payload = {k: getattr(self, k) for k in _HASHED_FIELDS}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def is_hash_valid(self) -> bool:
        return bool(self.block_hash) and self.block_hash == self.compute_block_hash()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Block":
        return cls(
            previous_hash=str(data["previous_hash"]),
            law_id=str(data["law_id"]),
            action=str(data["action"]),
            n_zeros_required=int(data["n_zeros_required"]),
            nonce=int(data["nonce"]),
            winning_node_or_pool=str(data["winning_node_or_pool"]),
            voting_window_id=str(data["voting_window_id"]),
            timestamp=str(data["timestamp"]),
            block_hash=str(data.get("block_hash", "")),
        )


def seal_block(*, previous_hash: str, law_id: str, action: str,
               n_zeros_required: int, nonce: int, winning_node_or_pool: str,
               voting_window_id: str, timestamp: str) -> Block:
    """Crea un bloque y le calcula su ``block_hash`` definitivo."""
    block = Block(
        previous_hash=previous_hash,
        law_id=law_id,
        action=action,
        n_zeros_required=n_zeros_required,
        nonce=nonce,
        winning_node_or_pool=winning_node_or_pool,
        voting_window_id=voting_window_id,
        timestamp=timestamp,
    )
    block.block_hash = block.compute_block_hash()
    return block
