"""Elección Bully-by-effort para Pool Coordinator vía Redis.

Protocolo:
1. Todos los candidatos sin líder calculan el mismo seed:
       seed = f"{last_block_hash}:{epoch}"
   donde epoch = floor(time() / ELECTION_EPOCH_SECONDS).
2. Cada candidato resuelve el mini-PoW localmente (sin coordinación).
3. El primero en resolver intenta SET NX ``pool:election:{epoch}``.
   Solo uno puede ganar (Redis garantiza la atomicidad).
4. El ganador adquiere el lease ``pool:leader`` con SET (sin NX, ya
   arbitrado por el PoW + el claim atómico).

Si la época cambia durante el PoW (cómputo muy lento), el candidato
descarta el nonce y la siguiente llamada desde tick() usará la época
actual.
"""

from __future__ import annotations

import logging
import time

from common.blockchain.challenge import solve_mini_challenge

log = logging.getLogger("voxchain.pool.election")

ELECTION_EPOCH_SECONDS = 30


def run_pool_election(
    redis,
    pool_id: str,
    *,
    n_zeros: int = 2,
    lease_key: str = "pool:leader",
    lease_ttl: int = 10,
    epoch_duration: int = ELECTION_EPOCH_SECONDS,
    clock=time.time,
) -> bool:
    """Participa en la elección de Pool Coordinator.

    Devuelve True si este pool ganó y adquirió el liderazgo.
    """
    epoch = int(clock() / epoch_duration)
    election_key = f"pool:election:{epoch}"

    if redis.get(election_key) is not None:
        log.debug("pool %s: elección %d ya resuelta, retirándose", pool_id, epoch)
        return False

    last_hash = (redis.lindex("chain", -1) or "genesis")
    seed = f"{last_hash}:{epoch}"

    log.info("pool %s: resolviendo mini-PoW (seed=…%s, %d ceros, epoch=%d)",
             pool_id, seed[-8:], n_zeros, epoch)

    nonce = solve_mini_challenge(seed, n_zeros)
    if nonce is None:
        log.warning("pool %s: no se pudo resolver el mini-PoW", pool_id)
        return False

    # Si la época cambió durante el cómputo, el claim sería para una época vieja.
    if int(clock() / epoch_duration) != epoch:
        log.info("pool %s: época cambió durante el PoW, abortando", pool_id)
        return False

    # Claim atómico: solo el primero en llegar gana.
    won = bool(redis.set(election_key, pool_id, nx=True, ex=lease_ttl * 3))
    if not won:
        log.info("pool %s: perdió el claim atómico (otro candidato más rápido)", pool_id)
        return False

    redis.set(lease_key, pool_id, ex=lease_ttl)
    log.info("pool %s: ¡GANÓ la elección! (nonce=%d, epoch=%d)", pool_id, nonce, epoch)
    return True
