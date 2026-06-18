"""Tests de la sucesión del NCT por esfuerzo (Bully mejorado, AGENT.md 4)."""

import pytest

from nct.bully import elect_new_nct, run_distributed_election, solve_mini_challenge


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


def test_run_distributed_election_gana_sin_competencia(bus, store):
    """Un candidato solo gana la elección sin competencia."""
    seed = f"{store.last_block_hash()}::election-test"
    won = run_distributed_election(
        seed=seed, n_zeros=2, candidate_id="nct-standby",
        messaging=bus, store=store,
    )
    assert won is True
    assert store.get_leader() == "nct-standby"


def test_run_distributed_election_segundo_candidato_pierde(bus, store):
    """Dos candidatos en el mismo bus: el primero gana, el segundo pierde."""
    seed = f"{store.last_block_hash()}::election-dual"

    # El primer candidato gana
    won_a = run_distributed_election(
        seed=seed, n_zeros=2, candidate_id="nct-A",
        messaging=bus, store=store,
    )
    assert won_a is True
    assert store.get_leader() == "nct-A"

    # El segundo candidato (mismo seed) pierde porque A ya está en Redis
    won_b = run_distributed_election(
        seed=seed, n_zeros=2, candidate_id="nct-B",
        messaging=bus, store=store,
    )
    assert won_b is False
    assert store.get_leader() == "nct-A"


def test_standby_ignora_propuestas_cuando_no_es_leader(bus, store):
    """NCT con is_leader=False no procesa propuestas."""
    from nct.coordinator import NCTCoordinator

    standby = NCTCoordinator(
        bus, store, n_zeros=2, window_seconds_promulgacion=300,
        window_seconds_derogacion=300, cooldown_new=1, cooldown_reproposed=2,
        nct_id="nct-standby", is_leader=False,
    )
    standby.wire()

    bus.publish_proposal({
        "law_id": "L-ignorada", "author_pubkey": "A",
        "text_hash": "ha", "created_at": "t",
    })
    assert store.get_law("L-ignorada") is None or \
           store.get_law("L-ignorada").get("status") == "pending_queue"


def test_standby_procesa_propuestas_tras_ser_leader(bus, store):
    """become_leader() activa el procesamiento de propuestas en un standby."""
    from nct.coordinator import NCTCoordinator

    standby = NCTCoordinator(
        bus, store, n_zeros=2, window_seconds_promulgacion=300,
        window_seconds_derogacion=300, cooldown_new=1, cooldown_reproposed=2,
        nct_id="nct-standby", is_leader=False,
    )
    standby.wire()
    standby.become_leader()

    assert standby.is_leader is True
    bus.publish_proposal({
        "law_id": "L-convertida", "author_pubkey": "B",
        "text_hash": "hb", "created_at": "t",
    })
    law = store.get_law("L-convertida")
    assert law is not None
    # La ley fue procesada: pasó a ventana (sin worker no se promulga)
    assert law["status"] in ("in_window", "promulgated")


def test_takeover_distribuido_completo(bus, store):
    """Escenario completo: primario cae → standby gana elección → procesa leyes."""
    from common.blockchain import validate_chain
    from common.storage import LawStatus
    from nct.coordinator import NCTCoordinator

    # Fase 1: NCT primario procesa una ley (usamos ventana que expira negativa
    # y llamamos check_deadline manualmente para simular el cierre)
    primary = NCTCoordinator(
        bus, store, n_zeros=2, window_seconds_promulgacion=-1,
        window_seconds_derogacion=-1, cooldown_new=1, cooldown_reproposed=2,
        nct_id="nct-primary", is_leader=True,
    )
    primary.wire()
    primary.m.publish_proposal({
        "law_id": "L-vieja", "author_pubkey": "A",
        "text_hash": "ha", "created_at": "t",
    })
    primary.check_deadline()
    # Sin nonce, la ley vence y queda descartada (es correcto: no hay worker)
    assert store.get_law("L-vieja")["status"] == LawStatus.DISCARDED

    store.clear_leadership()  # simula caída del primario

    # Fase 2: standby gana la elección
    seed = f"{store.last_block_hash()}::takeover-test"
    won = run_distributed_election(
        seed=seed, n_zeros=2, candidate_id="nct-nuevo",
        messaging=bus, store=store,
    )
    assert won is True
    assert store.get_leader() == "nct-nuevo"

    # Fase 3: nuevo líder procesa otra ley (también vence por deadline negativo)
    nuevo = NCTCoordinator(
        bus, store, n_zeros=2, window_seconds_promulgacion=-1,
        window_seconds_derogacion=-1, cooldown_new=1, cooldown_reproposed=2,
        nct_id="nct-nuevo", is_leader=True,
    )
    nuevo.wire()
    nuevo.m.publish_proposal({
        "law_id": "L-nueva", "author_pubkey": "C",
        "text_hash": "hc", "created_at": "t",
    })
    nuevo.check_deadline()
    assert store.get_law("L-nueva")["status"] == LawStatus.DISCARDED

    # Cadena: sin soluciones, no hay bloques (lo que es correcto)
    resolver = lambda b: store.get_window(b.voting_window_id)["partial_hash_base"]
    assert validate_chain(store.get_chain(), base_resolver=resolver) is True
