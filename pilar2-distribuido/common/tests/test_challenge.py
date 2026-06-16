"""Tests de la serialización del desafío y verificación de nonce."""

import hashlib

import pytest

from common.blockchain import challenge as ch


def test_build_partial_hash_base_orden_fijo():
    base = ch.build_partial_hash_base("L1", "abc", "W1", ch.ACTION_PROMULGACION)
    assert base == "L1abcW1promulgacion"


def test_build_partial_hash_base_rechaza_action_invalida():
    with pytest.raises(ValueError):
        ch.build_partial_hash_base("L1", "abc", "W1", "voto")


def test_n_zeros_promulgacion_es_n_y_derogacion_es_n_mas_uno():
    assert ch.n_zeros_for_action(4, ch.ACTION_PROMULGACION) == 4
    assert ch.n_zeros_for_action(4, ch.ACTION_DEROGACION) == 5


def test_prefix_for_zeros():
    assert ch.prefix_for_zeros(4) == "0000"
    assert ch.prefix_for_zeros(0) == ""


def test_compute_hash_coincide_con_md5_directo():
    base = "L1abcW1promulgacion"
    assert ch.compute_hash(base, 123) == hashlib.md5(f"{base}123".encode()).hexdigest()


def _find_nonce(base, n_zeros):
    """Busca por fuerza bruta un nonce válido (igual que el minero CPU)."""
    prefix = "0" * n_zeros
    nonce = 0
    while True:
        if hashlib.md5(f"{base}{nonce}".encode()).hexdigest().startswith(prefix):
            return nonce
        nonce += 1


def test_verify_nonce_valido_para_promulgacion():
    base = ch.build_partial_hash_base("L1", "h", "W1", ch.ACTION_PROMULGACION)
    nonce = _find_nonce(base, 3)
    ok, hash_hex = ch.verify_nonce(base, nonce, 3)
    assert ok
    assert hash_hex.startswith("000")


def test_verify_nonce_distingue_n_de_n_mas_uno():
    """Un nonce válido para n=3 no necesariamente lo es para n=4 (derogación)."""
    base = ch.build_partial_hash_base("L1", "h", "W1", ch.ACTION_DEROGACION)
    nonce3 = _find_nonce(base, 3)
    ok4, h = ch.verify_nonce(base, nonce3, 4)
    # El cuarto dígito casi nunca es 0; comprobamos coherencia con el hash real.
    assert ok4 == h.startswith("0000")


def test_verify_nonce_invalido():
    base = ch.build_partial_hash_base("L1", "h", "W1", ch.ACTION_PROMULGACION)
    # nonce arbitrario que casi seguro no cumple 5 ceros
    ok, _ = ch.verify_nonce(base, 1, 5)
    assert ok is False
