"""Tests de la sucesión del NCT por esfuerzo (Bully mejorado, AGENT.md 4)."""

import pytest

from nct.bully import elect_new_nct, solve_mini_challenge


def test_solve_mini_challenge_devuelve_nonce_valido():
    from common.blockchain.challenge import compute_hash
    seed = "ultimo-bloque-hash::epoca-1"
    nonce = solve_mini_challenge(seed, 2)
    assert nonce is not None
    assert compute_hash(seed, nonce).startswith("00")


def test_elige_al_que_llego_primero_no_por_id():
    seed = "seed-eleccion"
    n = 2
    n1 = solve_mini_challenge(seed, n)
    # Dos candidatos con la misma (válida) solución; gana el de menor arrived_at
    candidatos = [
        {"candidate_id": "Z-nodo", "nonce": n1, "arrived_at": 10.0},
        {"candidate_id": "A-nodo", "nonce": n1, "arrived_at": 20.0},
    ]
    # Aunque "A-nodo" tendría menor ID alfabético, gana "Z-nodo" por esfuerzo/tiempo
    assert elect_new_nct(candidatos, seed, n) == "Z-nodo"


def test_descarta_candidatos_con_solucion_invalida():
    seed = "seed-eleccion"
    n = 3
    valido = solve_mini_challenge(seed, n)
    candidatos = [
        {"candidate_id": "tramposo", "nonce": 0, "arrived_at": 1.0},
        {"candidate_id": "honesto", "nonce": valido, "arrived_at": 5.0},
    ]
    assert elect_new_nct(candidatos, seed, n) == "honesto"


def test_sin_candidatos_validos_devuelve_none():
    assert elect_new_nct([], "seed", 2) is None


@pytest.mark.xfail(reason="PENDIENTE: coordinación distribuida de la elección "
                          "(heartbeat de caída + anuncio de candidatura + toma de "
                          "mando sobre RabbitMQ). Las piezas de PoW ya están; falta "
                          "el cableado de red. AGENT.md 4.", strict=True)
def test_takeover_distribuido_completo():
    # Escenario objetivo (aún no implementado):
    #   1) el NCT activo deja de emitir heartbeats,
    #   2) los nodos detectan la caída y resuelven el mini-desafío,
    #   3) el primero en resolver anuncia y asume como NCT,
    #   4) arranca una ventana NUEVA (la anterior se pierde, AGENT.md 4).
    from nct.bully import run_distributed_election  # noqa: F401  (no existe aún)
    raise AssertionError("no implementado")
