"""Cliente de estado de VoxChain sobre Redis (AGENT.md 7).

Expone ``VoxChainStore``, que persiste leyes, ventanas, bloques, cooldowns, la
cadena y el estado de la ventana activa con claves namespaced.
"""

from .redis_store import (
    VoxChainStore,
    LawStatus,
    WindowResult,
    CooldownReason,
    connect_redis,
)

__all__ = [
    "VoxChainStore",
    "LawStatus",
    "WindowResult",
    "CooldownReason",
    "connect_redis",
]
