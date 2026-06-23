"""Tests de comportamiento del NCT (reglas de gobierno AGENT.md 3–4)."""

import hashlib

import pytest

from common.blockchain import validate_chain
from common.blockchain.challenge import build_partial_hash_base
from common.storage import CooldownReason, LawStatus, WindowResult
from nct.coordinator import NCTCoordinator


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def make_nct(bus, store, clock, **kw):
    params = dict(n_zeros=2, window_seconds_promulgacion=60,
                  window_seconds_derogacion=90, cooldown_new=2,
                  cooldown_reproposed=4, clock=clock)
    params.update(kw)
    nct = NCTCoordinator(bus, store, **params)
    nct.wire()
    return nct


def solve(base, n_zeros):
    prefix = "0" * n_zeros
    nonce = 0
    while not hashlib.md5(f"{base}{nonce}".encode()).hexdigest().startswith(prefix):
        nonce += 1
    return nonce


def capture_challenges(bus):
    challenges = []
    bus.on_challenge(challenges.append)
    return challenges


def test_propuesta_abre_ventana_y_publica_desafio(bus, store):
    clock = Clock()
    challenges = capture_challenges(bus)
    make_nct(bus, store, clock)
    bus.publish_proposal({"law_id": "L1", "author_pubkey": "A",
                          "text_hash": "h1", "created_at": "t0"})
    assert len(challenges) == 1
    assert challenges[0]["n_zeros_required"] == 2
    assert challenges[0]["action"] == "promulgacion"
    assert store.get_law("L1")["status"] == LawStatus.IN_WINDOW
    assert store.get_active_window() == challenges[0]["voting_window_id"]


def test_flujo_completo_sella_bloque_con_cadena_valida(bus, store):
    clock = Clock()
    challenges = capture_challenges(bus)
    make_nct(bus, store, clock)
    bus.publish_proposal({"law_id": "L1", "author_pubkey": "A",
                          "text_hash": "h1", "created_at": "t0"})
    ch = challenges[0]
    nonce = solve(ch["partial_hash_base"], ch["n_zeros_required"])
    bus.publish_nonce_response({"voting_window_id": ch["voting_window_id"],
                                "nonce": nonce, "winning_node_or_pool": "pool-X",
                                "block_hash_candidato": "x"})
    assert store.chain_length() == 1
    assert store.get_law("L1")["status"] == LawStatus.PROMULGATED
    assert store.get_active_window() is None
    assert store.get_window(ch["voting_window_id"])["result"] == WindowResult.SUCCESS
    assert validate_chain(store.get_chain()) is True


def test_descarta_nonce_de_otra_ventana(bus, store):
    clock = Clock()
    challenges = capture_challenges(bus)
    make_nct(bus, store, clock)
    bus.publish_proposal({"law_id": "L1", "author_pubkey": "A",
                          "text_hash": "h1", "created_at": "t0"})
    bus.publish_nonce_response({"voting_window_id": "ventana-falsa",
                                "nonce": 0, "winning_node_or_pool": "pool-X"})
    assert store.chain_length() == 0
    assert store.get_active_window() == challenges[0]["voting_window_id"]


def test_descarta_nonce_invalido(bus, store):
    clock = Clock()
    challenges = capture_challenges(bus)
    make_nct(bus, store, clock, n_zeros=5)
    bus.publish_proposal({"law_id": "L1", "author_pubkey": "A",
                          "text_hash": "h1", "created_at": "t0"})
    ch = challenges[0]
    bus.publish_nonce_response({"voting_window_id": ch["voting_window_id"],
                                "nonce": 1, "winning_node_or_pool": "pool-X"})
    assert store.chain_length() == 0


def test_descarta_nonce_tardio_post_deadline(bus, store):
    clock = Clock()
    challenges = capture_challenges(bus)
    make_nct(bus, store, clock)
    bus.publish_proposal({"law_id": "L1", "author_pubkey": "A",
                          "text_hash": "h1", "created_at": "t0"})
    ch = challenges[0]
    nonce = solve(ch["partial_hash_base"], ch["n_zeros_required"])
    clock.t += 1000  # pasó el deadline
    bus.publish_nonce_response({"voting_window_id": ch["voting_window_id"],
                                "nonce": nonce, "winning_node_or_pool": "pool-X"})
    assert store.chain_length() == 0


def test_autor_no_puede_ganar_su_propia_ventana(bus, store):
    clock = Clock()
    challenges = capture_challenges(bus)
    make_nct(bus, store, clock)
    bus.publish_proposal({"law_id": "L1", "author_pubkey": "A",
                          "text_hash": "h1", "created_at": "t0"})
    ch = challenges[0]
    nonce = solve(ch["partial_hash_base"], ch["n_zeros_required"])
    bus.publish_nonce_response({"voting_window_id": ch["voting_window_id"],
                                "nonce": nonce, "winning_node_or_pool": "A"})
    assert store.chain_length() == 0


def test_ventana_vencida_descarta_ley_y_no_reencola(bus, store):
    clock = Clock()
    challenges = capture_challenges(bus)
    nct = make_nct(bus, store, clock)
    bus.publish_proposal({"law_id": "L1", "author_pubkey": "A",
                          "text_hash": "h1", "created_at": "t0"})
    ch = challenges[0]
    clock.t += 1000
    nct.check_deadline()
    assert store.get_law("L1")["status"] == LawStatus.DISCARDED
    assert store.get_window(ch["voting_window_id"])["result"] == WindowResult.EXPIRED_PENDING
    assert store.get_active_window() is None
    assert "L1" not in store.queued_law_ids()  # no se reencola
    assert store.is_text_hash_discarded("h1")


def test_cooldown_bloquea_repropuesta_inmediata(bus, store):
    clock = Clock()
    challenges = capture_challenges(bus)
    make_nct(bus, store, clock)
    bus.publish_proposal({"law_id": "L1", "author_pubkey": "A",
                          "text_hash": "h1", "created_at": "t0"})
    # A intenta proponer otra ley estando en cooldown
    bus.publish_proposal({"law_id": "L2", "author_pubkey": "A",
                          "text_hash": "h2", "created_at": "t1"})
    assert store.get_law("L2") is None  # rechazada, ni siquiera se guarda
    assert store.queued_law_ids() == []  # L1 ya está en ventana, L2 rechazada


def test_reproposicion_identica_penaliza_mas_que_una_nueva(bus, store):
    clock = Clock()
    capture_challenges(bus)
    make_nct(bus, store, clock)
    # Descartamos h_repetida para simular una ley previa pendiente
    store.mark_text_hash_discarded("h_repetida")
    # Autor B repropone texto idéntico ya descartado
    bus.publish_proposal({"law_id": "Lrep", "author_pubkey": "B",
                          "text_hash": "h_repetida", "created_at": "t"})
    # Autor C propone texto nuevo
    bus.publish_proposal({"law_id": "Lnew", "author_pubkey": "C",
                          "text_hash": "h_nueva", "created_at": "t"})
    cd_b = store.get_cooldown("B")
    cd_c = store.get_cooldown("C")
    assert cd_b["cooldown_reason"] == CooldownReason.REPROPOSED_IDENTICAL
    assert cd_c["cooldown_reason"] == CooldownReason.PROPOSED_NEW
    assert int(cd_b["cooldown_until_window"]) > int(cd_c["cooldown_until_window"])


def test_derogacion_exige_n_mas_uno_ceros(bus, store):
    clock = Clock()
    challenges = capture_challenges(bus)
    make_nct(bus, store, clock)
    # Promulgar L1 primero
    bus.publish_proposal({"law_id": "L1", "author_pubkey": "A",
                          "text_hash": "h1", "created_at": "t0"})
    ch = challenges[0]
    nonce = solve(ch["partial_hash_base"], ch["n_zeros_required"])
    bus.publish_nonce_response({"voting_window_id": ch["voting_window_id"],
                                "nonce": nonce, "winning_node_or_pool": "pool-X"})
    assert store.get_law("L1")["status"] == LawStatus.PROMULGATED
    # Derogación de L1 por autor B
    bus.publish_proposal({"law_id": "L1", "author_pubkey": "B",
                          "text_hash": "h1", "created_at": "t2",
                          "action": "derogacion"})
    derog_ch = challenges[-1]
    assert derog_ch["action"] == "derogacion"
    assert derog_ch["n_zeros_required"] == 3  # n=2 → n+1
    nonce2 = solve(derog_ch["partial_hash_base"], 3)
    bus.publish_nonce_response({"voting_window_id": derog_ch["voting_window_id"],
                                "nonce": nonce2, "winning_node_or_pool": "pool-Y"})
    assert store.get_law("L1")["status"] == LawStatus.REPEALED
    assert store.chain_length() == 2
    chain = store.get_chain()
    # validación con resolver de base desde la ventana persistida en Redis
    resolver = lambda b: store.get_window(b.voting_window_id)["partial_hash_base"]
    assert validate_chain(chain, base_resolver=resolver) is True


def test_round_robin_entre_dos_autores_en_ventanas_sucesivas(bus, store):
    clock = Clock()
    challenges = capture_challenges(bus)
    nct = make_nct(bus, store, clock, cooldown_new=0)
    # A y B proponen; ventana 1 = A (más antigua)
    bus.publish_proposal({"law_id": "LA1", "author_pubkey": "A",
                          "text_hash": "ha1", "created_at": "t"})
    bus.publish_proposal({"law_id": "LA2", "author_pubkey": "A",
                          "text_hash": "ha2", "created_at": "t"})
    bus.publish_proposal({"law_id": "LB1", "author_pubkey": "B",
                          "text_hash": "hb1", "created_at": "t"})
    assert challenges[0]["law_id"] == "LA1"
    # resolver ventana 1
    ch = challenges[0]
    nonce = solve(ch["partial_hash_base"], ch["n_zeros_required"])
    bus.publish_nonce_response({"voting_window_id": ch["voting_window_id"],
                                "nonce": nonce, "winning_node_or_pool": "p"})
    # ventana 2 debe saltar a B (no a LA2), por round-robin
    assert challenges[1]["law_id"] == "LB1"


def test_seal_aborta_si_cas_falla_sin_fork(bus, store):
    """Si append_block devuelve False (tip cambió), _seal aborta sin fork (A-04).

    Simula el escenario de split-brain: un NCT-B intenta sellar su ventana pero
    NCT-A ya avanzó el tip. El bloque de NCT-B se rechaza, la ley se re-encola
    y la cadena queda intacta.
    """
    from unittest.mock import patch
    from common.blockchain.block import GENESIS_PREVIOUS_HASH

    clock = Clock()
    challenges = capture_challenges(bus)
    nct = make_nct(bus, store, clock)

    # Abrir ventana con L1
    bus.publish_proposal({"law_id": "L1", "author_pubkey": "A",
                          "text_hash": "h1", "created_at": "t0"})
    ch = challenges[0]
    nonce = solve(ch["partial_hash_base"], ch["n_zeros_required"])

    # Forzar que append_block devuelva False (otro NCT se adelantó)
    with patch.object(store, "append_block", return_value=False):
        bus.publish_nonce_response({"voting_window_id": ch["voting_window_id"],
                                    "nonce": nonce, "winning_node_or_pool": "pool-X"})

    # Cadena intacta: no se agregó ningún bloque → no hay fork
    assert store.chain_length() == 0
    # La ley no quedó marcada como promulgada (el sellado fue abortado)
    assert store.get_law("L1")["status"] != LawStatus.PROMULGATED
    # maybe_open_window() re-abre inmediatamente una nueva ventana con L1,
    # así que el NCT no queda con estado colgado del intento fallido
    assert nct._active is not None
    assert nct._active["law_id"] == "L1"
