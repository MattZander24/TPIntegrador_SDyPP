"""Tests de la sucesión del NCT (failover por lease Redis, AGENT.md 4).

El Bully-por-esfuerzo PoW se eliminó del NCT (los nodos son homogéneos en GCP,
sin ventaja de cómputo entre ellos). La elección se resuelve vía Redis:
elect_acquire_leadership + dead_threshold.
"""

import pytest

from nct.coordinator import NCTCoordinator


def test_standby_ignora_propuestas_cuando_no_es_leader(bus, store):
    """NCT con is_leader=False no procesa propuestas."""
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
    assert law["status"] in ("in_window", "promulgated")


def test_takeover_redis_completo(bus, store):
    """Escenario completo: primario cae → standby adquiere lease → procesa leyes."""
    from common.blockchain import validate_chain
    from common.storage import LawStatus

    # Fase 1: NCT primario procesa una ley (ventana expira negativa → descartada)
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
    assert store.get_law("L-vieja")["status"] == LawStatus.DISCARDED

    # Fase 2: caída del primario — standby adquiere el lease vía Redis
    store.clear_leadership()
    won = store.try_acquire_leadership("nct-nuevo", ttl=20)
    assert won is True
    assert store.get_leader() == "nct-nuevo"

    # Fase 3: nuevo líder procesa otra ley
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

    resolver = lambda b: store.get_window(b.voting_window_id)["partial_hash_base"]
    assert validate_chain(store.get_chain(), base_resolver=resolver) is True


def test_elect_acquire_leadership_respeta_dead_threshold(store):
    """elect_acquire_leadership adquiere el lease si el TTL del holder es bajo."""
    store.try_acquire_leadership("nct-muerto", ttl=3)

    # TTL bajo (< dead_threshold=6) → puede adquirir
    won = store.elect_acquire_leadership("nct-nuevo", ttl=20, dead_threshold=6)
    assert won is True
    assert store.get_leader() == "nct-nuevo"


def test_elect_acquire_leadership_bloquea_si_lider_vivo(store):
    """elect_acquire_leadership falla si el holder tiene TTL alto (lider vivo)."""
    store.try_acquire_leadership("nct-vivo", ttl=20)

    # TTL alto (> dead_threshold=6) → no puede adquirir
    won = store.elect_acquire_leadership("nct-otro", ttl=20, dead_threshold=6)
    assert won is False
    assert store.get_leader() == "nct-vivo"
