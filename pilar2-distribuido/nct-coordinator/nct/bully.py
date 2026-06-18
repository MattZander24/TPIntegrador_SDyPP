"""Sucesión del NCT por esfuerzo: Bully mejorado (AGENT.md 1.1 y 4).

Si el NCT cae, los nodos candidatos resuelven un mini-desafío de PoW y el primero
en resolverlo asume como nuevo NCT (no por mayor ID). Cualquier nodo puede
postularse. La ventana en curso **se pierde**: no se persiste para recuperarla;
el nuevo NCT siempre arranca con una ventana nueva.
"""

from __future__ import annotations

import logging
import time

from common.blockchain.challenge import compute_hash, prefix_for_zeros, verify_nonce

log = logging.getLogger("voxchain.nct.bully")


def solve_mini_challenge(seed: str, n_zeros: int, max_iter: int = 10_000_000) -> int | None:
    """Resuelve el mini-desafío de elección: nonce con ``n_zeros`` ceros sobre ``seed``.

    El ``seed`` lo comparten todos los candidatos (p. ej. el hash del último
    bloque + una época de elección), de modo que la competencia sea justa.
    """
    prefix = prefix_for_zeros(n_zeros)
    for nonce in range(max_iter):
        if compute_hash(seed, nonce).startswith(prefix):
            return nonce
    return None


def elect_new_nct(candidate_solutions: list[dict], seed: str, n_zeros: int) -> str | None:
    """Elige al nuevo NCT: el candidato con solución válida que llegó primero.

    ``candidate_solutions`` es una lista de ``{"candidate_id", "nonce",
    "arrived_at"}`` recibidas tras la caída. Gana el de menor ``arrived_at`` entre
    los que presentan un nonce válido para el mini-desafío. No se decide por ID
    (esa es justamente la mejora sobre el Bully clásico).
    """
    valid = [
        c for c in candidate_solutions
        if compute_hash(seed, int(c["nonce"])).startswith(prefix_for_zeros(n_zeros))
    ]
    if not valid:
        return None
    winner = min(valid, key=lambda c: c["arrived_at"])
    return winner["candidate_id"]


def run_distributed_election(
    seed: str,
    n_zeros: int,
    candidate_id: str,
    messaging,
    store,
    *,
    clock=time.time,
) -> bool:
    """Participa en la elección distribuida del NCT.

    Resuelve el mini-desafío de PoW localmente. Si encuentra solución, la publica
    a la cola ``nct_election``. Si recibe un claim válido de otro candidato antes
    de resolver, se retira.

    Devuelve ``True`` si este candidato ganó la elección y debe asumir como líder.
    """
    backoff = False

    def handle_claim(claim: dict) -> None:
        nonlocal backoff
        if claim.get("candidate_id") == candidate_id:
            return
        if claim.get("seed") != seed:
            return
        if claim.get("n_zeros") != n_zeros:
            return
        ok, _ = verify_nonce(seed, int(claim["nonce"]), n_zeros)
        if ok:
            log.info("otro candidato %s encontró nonce antes; nos retiramos",
                     claim["candidate_id"][:12])
            backoff = True

    messaging.on_election_claim(handle_claim)

    log.info("resolviendo mini-desafío (seed=%s..., %d ceros)", seed[:12], n_zeros)
    nonce = solve_mini_challenge(seed, n_zeros)

    if nonce is None:
        log.warning("no se pudo resolver el mini-desafío")
        return False

    if backoff:
        log.info("nos retiramos de la elección (otro candidato ganó)")
        return False

    log.info("mini-desafío resuelto (nonce=%d), publicando claim", nonce)
    messaging.publish_election_claim({
        "candidate_id": candidate_id,
        "nonce": nonce,
        "seed": seed,
        "n_zeros": n_zeros,
        "ts": clock(),
    })

    if backoff:
        log.info("otro candidato se adelantó justo antes de nuestro claim")
        return False

    won = store.try_acquire_leadership(candidate_id)
    if won:
        log.info("¡GANAMOS la elección! Somos el nuevo NCT")
    else:
        log.info("otro candidato ya adquirió el liderazgo")
    return won
