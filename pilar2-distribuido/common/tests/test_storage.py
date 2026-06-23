"""Tests del cliente de estado sobre Redis (fakeredis)."""

from common.blockchain import ACTION_PROMULGACION, seal_block
from common.blockchain.block import GENESIS_PREVIOUS_HASH
from common.storage import CooldownReason, LawStatus, WindowResult


def test_save_and_get_law(store):
    store.save_law(law_id="L1", author_pubkey="pk1", text_hash="h1",
                   created_at="t0")
    law = store.get_law("L1")
    assert law["author_pubkey"] == "pk1"
    assert law["status"] == LawStatus.PENDING_QUEUE
    assert "text_ref" not in law  # None se omite


def test_set_law_status(store):
    store.save_law(law_id="L1", author_pubkey="pk1", text_hash="h1", created_at="t0")
    store.set_law_status("L1", LawStatus.PROMULGATED)
    assert store.get_law("L1")["status"] == LawStatus.PROMULGATED


def test_law_queue_orden_y_remocion(store):
    for i in range(3):
        store.save_law(law_id=f"L{i}", author_pubkey=f"pk{i}", text_hash="h",
                       created_at="t")
        store.enqueue_law(f"L{i}")
    assert store.queued_law_ids() == ["L0", "L1", "L2"]
    store.remove_from_queue("L1")
    assert store.queued_law_ids() == ["L0", "L2"]
    assert [l["law_id"] for l in store.queued_laws()] == ["L0", "L2"]


def test_window_counter_monotono(store):
    assert store.current_window_number() == 0
    assert store.next_window_number() == 1
    assert store.next_window_number() == 2
    assert store.current_window_number() == 2


def test_window_save_get_result(store):
    store.save_window(voting_window_id="W1", law_id="L1",
                      action=ACTION_PROMULGACION, n_zeros_required=4,
                      opened_at="t0", deadline="t1", partial_hash_base="base")
    w = store.get_window("W1")
    assert w["n_zeros_required"] == "4"
    assert "result" not in w
    store.set_window_result("W1", result=WindowResult.SUCCESS, winning_nonce=99,
                            winning_node_or_pool="pool-A")
    w = store.get_window("W1")
    assert w["result"] == WindowResult.SUCCESS
    assert w["winning_nonce"] == "99"


def test_active_window(store):
    assert store.get_active_window() is None
    store.set_active_window("W1")
    assert store.get_active_window() == "W1"
    store.clear_active_window()
    assert store.get_active_window() is None


def test_cooldown_lifecycle(store):
    store.next_window_number()  # window 1
    store.set_cooldown("pk1", cooldown_until_window=3,
                       reason=CooldownReason.PROPOSED_NEW)
    assert store.is_in_cooldown("pk1") is True  # 1 < 3
    store.next_window_number()  # 2
    store.next_window_number()  # 3
    assert store.is_in_cooldown("pk1") is False  # 3 >= 3
    assert store.get_cooldown("pk1")["cooldown_reason"] == CooldownReason.PROPOSED_NEW


def test_no_cooldown_returns_false(store):
    assert store.is_in_cooldown("desconocido") is False


def test_discarded_text_hashes(store):
    assert store.is_text_hash_discarded("h1") is False
    store.mark_text_hash_discarded("h1")
    assert store.is_text_hash_discarded("h1") is True


def test_append_and_read_chain(store):
    assert store.last_block_hash() == GENESIS_PREVIOUS_HASH
    b1 = seal_block(previous_hash=GENESIS_PREVIOUS_HASH, law_id="L1",
                    action=ACTION_PROMULGACION, n_zeros_required=1, nonce=5,
                    winning_node_or_pool="n1", voting_window_id="W1", timestamp="t1")
    assert store.append_block(b1) is True
    b2 = seal_block(previous_hash=b1.block_hash, law_id="L2",
                    action=ACTION_PROMULGACION, n_zeros_required=1, nonce=6,
                    winning_node_or_pool="n2", voting_window_id="W2", timestamp="t2")
    assert store.append_block(b2) is True
    assert store.chain_length() == 2
    assert store.last_block_hash() == b2.block_hash
    chain = store.get_chain()
    assert [b.law_id for b in chain] == ["L1", "L2"]
    assert chain[0].is_hash_valid()
    assert store.get_block(b1.block_hash) == b1


def test_append_block_cas_rechaza_tip_incorrecto(store):
    """Un bloque con previous_hash que no es el tip actual es rechazado (A-04)."""
    b1 = seal_block(previous_hash=GENESIS_PREVIOUS_HASH, law_id="L1",
                    action=ACTION_PROMULGACION, n_zeros_required=1, nonce=5,
                    winning_node_or_pool="n1", voting_window_id="W1", timestamp="t1")
    assert store.append_block(b1) is True

    # Bloque que apunta a genesis (tip incorrecto: el tip real es b1.block_hash)
    b_fork = seal_block(previous_hash=GENESIS_PREVIOUS_HASH, law_id="L2",
                        action=ACTION_PROMULGACION, n_zeros_required=1, nonce=7,
                        winning_node_or_pool="n2", voting_window_id="W2", timestamp="t2")
    assert store.append_block(b_fork) is False
    assert store.chain_length() == 1  # cadena intacta


def test_append_block_genesis_acepta_cadena_vacia(store):
    """El primer bloque se acepta aunque la cadena esté vacía (sin tip)."""
    b1 = seal_block(previous_hash=GENESIS_PREVIOUS_HASH, law_id="L1",
                    action=ACTION_PROMULGACION, n_zeros_required=1, nonce=5,
                    winning_node_or_pool="n1", voting_window_id="W1", timestamp="t1")
    assert store.append_block(b1) is True
    assert store.chain_length() == 1
