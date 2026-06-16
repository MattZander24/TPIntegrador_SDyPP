"""Tests de la lógica pura de cola/cooldown del NCT."""

from common.storage import CooldownReason
from nct.queue_logic import classify_proposal, cooldown_until, select_next_law


def _law(law_id, author):
    return {"law_id": law_id, "author_pubkey": author}


def test_round_robin_evita_autor_consecutivo():
    pending = [_law("L1", "A"), _law("L2", "A"), _law("L3", "B")]
    # último autor fue A → debe saltar a la primera ley de otro autor (B)
    assert select_next_law(pending, last_author="A")["law_id"] == "L3"


def test_round_robin_sin_last_author_toma_la_mas_antigua():
    pending = [_law("L1", "A"), _law("L2", "B")]
    assert select_next_law(pending, last_author=None)["law_id"] == "L1"


def test_round_robin_si_solo_queda_el_mismo_autor_usa_la_mas_antigua():
    pending = [_law("L1", "A"), _law("L2", "A")]
    assert select_next_law(pending, last_author="A")["law_id"] == "L1"


def test_select_de_cola_vacia_es_none():
    assert select_next_law([], last_author=None) is None


def test_classify_proposal():
    assert classify_proposal(False) == CooldownReason.PROPOSED_NEW
    assert classify_proposal(True) == CooldownReason.REPROPOSED_IDENTICAL


def test_cooldown_reproposicion_es_mayor_que_nueva():
    nueva = cooldown_until(10, CooldownReason.PROPOSED_NEW,
                           cooldown_new=4, cooldown_reproposed=8)
    repro = cooldown_until(10, CooldownReason.REPROPOSED_IDENTICAL,
                           cooldown_new=4, cooldown_reproposed=8)
    assert nueva == 14
    assert repro == 18
    assert repro > nueva
