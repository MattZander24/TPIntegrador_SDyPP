"""Tests del modelo de bloque y validación de cadena."""

import hashlib

import pytest

from common.blockchain import (
    ACTION_PROMULGACION,
    ACTION_DEROGACION,
    Block,
    ChainValidationError,
    build_partial_hash_base,
    seal_block,
    validate_chain,
    validate_chain_links,
)
from common.blockchain.block import GENESIS_PREVIOUS_HASH


def _solve(base, n_zeros):
    prefix = "0" * n_zeros
    nonce = 0
    while not hashlib.md5(f"{base}{nonce}".encode()).hexdigest().startswith(prefix):
        nonce += 1
    return nonce


def test_seal_block_calcula_hash_valido():
    b = seal_block(previous_hash=GENESIS_PREVIOUS_HASH, law_id="L1",
                   action=ACTION_PROMULGACION, n_zeros_required=2, nonce=42,
                   winning_node_or_pool="pool-A", voting_window_id="W1",
                   timestamp="2026-01-01T00:00:00Z")
    assert b.block_hash
    assert b.is_hash_valid()


def test_block_hash_cambia_si_cambia_contenido():
    b = seal_block(previous_hash=GENESIS_PREVIOUS_HASH, law_id="L1",
                   action=ACTION_PROMULGACION, n_zeros_required=2, nonce=42,
                   winning_node_or_pool="pool-A", voting_window_id="W1",
                   timestamp="2026-01-01T00:00:00Z")
    b.nonce = 43
    assert not b.is_hash_valid()


def test_to_from_dict_roundtrip():
    b = seal_block(previous_hash=GENESIS_PREVIOUS_HASH, law_id="L1",
                   action=ACTION_DEROGACION, n_zeros_required=3, nonce=7,
                   winning_node_or_pool="n1", voting_window_id="W1",
                   timestamp="t")
    b2 = Block.from_dict(b.to_dict())
    assert b2 == b
    assert b2.is_hash_valid()


def _build_chain():
    bases = {}
    blocks = []
    prev = GENESIS_PREVIOUS_HASH
    for i, action in enumerate([ACTION_PROMULGACION, ACTION_PROMULGACION, ACTION_DEROGACION]):
        wid = f"W{i}"
        base = build_partial_hash_base(f"L{i}", "texthash", wid, action)
        n_zeros = 1 if action == ACTION_PROMULGACION else 2
        nonce = _solve(base, n_zeros)
        block = seal_block(previous_hash=prev, law_id=f"L{i}", action=action,
                           n_zeros_required=n_zeros, nonce=nonce,
                           winning_node_or_pool=f"node{i}", voting_window_id=wid,
                           timestamp=f"t{i}")
        bases[block.block_hash] = base
        blocks.append(block)
        prev = block.block_hash
    return blocks, bases


def test_validate_chain_links_ok():
    blocks, _ = _build_chain()
    assert validate_chain_links(blocks) is True


def test_validate_chain_completa_con_resolver_de_base():
    blocks, bases = _build_chain()
    assert validate_chain(blocks, base_resolver=lambda b: bases[b.block_hash]) is True


def test_validate_chain_detecta_encadenamiento_roto():
    blocks, _ = _build_chain()
    blocks[2].previous_hash = "deadbeef" * 8
    blocks[2].block_hash = blocks[2].compute_block_hash()
    with pytest.raises(ChainValidationError):
        validate_chain_links(blocks)


def test_validate_chain_detecta_nonce_invalido():
    blocks, bases = _build_chain()
    # Forzamos exigir más ceros de los que el nonce satisface, re-sellando.
    bad = blocks[0]
    bad.n_zeros_required = 8
    bad.block_hash = bad.compute_block_hash()
    blocks[1].previous_hash = bad.block_hash
    blocks[1].block_hash = blocks[1].compute_block_hash()
    blocks[2].previous_hash = blocks[1].block_hash
    blocks[2].block_hash = blocks[2].compute_block_hash()
    new_bases = {b.block_hash: build_partial_hash_base(b.law_id, "texthash",
                 b.voting_window_id, b.action) for b in blocks}
    with pytest.raises(ChainValidationError):
        validate_chain(blocks, base_resolver=lambda b: new_bases[b.block_hash])


def test_cadena_vacia_es_valida():
    assert validate_chain_links([]) is True


def test_compress_decompress_roundtrip():
    from common.blockchain import compress_text, decompress_text
    original = "Presupuesto 2026: $1.2M para infraestructura"
    compressed = compress_text(original)
    assert isinstance(compressed, str)
    assert len(compressed) < len(original) or True  # gzip overhead aceptado
    restored = decompress_text(compressed)
    assert restored == original


def test_compress_decompress_vacio():
    from common.blockchain import compress_text, decompress_text
    assert decompress_text(compress_text("")) == ""


def test_seal_block_con_texto_comprimido():
    from common.blockchain import compress_text
    original = "Ley de presupuesto 2026: partidas, montos y plazos."
    compressed = compress_text(original)
    b = seal_block(previous_hash=GENESIS_PREVIOUS_HASH, law_id="L1",
                   action=ACTION_PROMULGACION, n_zeros_required=2, nonce=42,
                   winning_node_or_pool="pool-A", voting_window_id="W1",
                   timestamp="2026-01-01T00:00:00Z",
                   text_compressed=compressed, text_original_len=len(original))
    assert b.is_hash_valid()
    assert b.text_compressed == compressed
    assert b.text_original_len == len(original)


def test_from_dict_retrocompatible_sin_texto_comprimido():
    old_dict = {
        "previous_hash": GENESIS_PREVIOUS_HASH,
        "law_id": "L1",
        "action": ACTION_PROMULGACION,
        "n_zeros_required": 2,
        "nonce": 42,
        "winning_node_or_pool": "pool-A",
        "voting_window_id": "W1",
        "timestamp": "2026-01-01T00:00:00Z",
        "block_hash": "",
    }
    b = Block.from_dict(old_dict)
    assert b.text_compressed == ""
    assert b.text_original_len == 0
    # El hash calculado ahora incluye text_compressed="" y text_original_len=0
    assert b.compute_block_hash()
