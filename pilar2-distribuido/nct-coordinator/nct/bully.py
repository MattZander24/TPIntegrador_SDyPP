"""Sucesión del NCT por esfuerzo: Bully mejorado (AGENT.md 1.1 y 4).

Si el NCT cae, los nodos candidatos resuelven un mini-desafío de PoW y el primero
en resolverlo asume como nuevo NCT (no por mayor ID). Cualquier nodo puede
postularse. La ventana en curso **se pierde**: no se persiste para recuperarla;
el nuevo NCT siempre arranca con una ventana nueva.

Estado de implementación
------------------------
Las piezas de PoW de la elección (resolver el mini-desafío y elegir al ganador
por esfuerzo) están implementadas y testeadas acá. La **coordinación distribuida**
completa —detección de caída del NCT por heartbeat, anuncio de candidatura y toma
de mando sobre RabbitMQ— queda PENDIENTE y está cubierta por un test ``xfail``
(ver tests/test_bully.py). Es el último ítem del plan y no bloquea el resto del
Pilar 2.
"""

from __future__ import annotations

from common.blockchain.challenge import compute_hash, prefix_for_zeros


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
