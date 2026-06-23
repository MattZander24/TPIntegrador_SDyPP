"""Tests de verificación de firmas ECDSA P-256 (A-01)."""

import pytest

from common.identity import (
    proposal_message,
    public_key_b64,
    sign,
    verify,
)

ec = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ec",
                         reason="requiere cryptography")


def _keypair():
    from cryptography.hazmat.primitives.asymmetric import ec as _ec

    priv = _ec.generate_private_key(_ec.SECP256R1())
    return priv, public_key_b64(priv)


def test_firma_valida_round_trip():
    priv, pub = _keypair()
    msg = proposal_message(pub, "promulgacion", "h1", "L1", "2026-01-01T00:00:00+00:00")
    sig = sign(priv, msg)
    assert verify(pub, msg, sig) is True


def test_mensaje_alterado_falla():
    priv, pub = _keypair()
    msg = proposal_message(pub, "promulgacion", "h1", "L1", "t0")
    sig = sign(priv, msg)
    tampered = proposal_message(pub, "derogacion", "h1", "L1", "t0")
    assert verify(pub, tampered, sig) is False


def test_otra_pubkey_falla():
    priv, _ = _keypair()
    _, other_pub = _keypair()
    msg = proposal_message(other_pub, "promulgacion", "h1", "L1", "t0")
    sig = sign(priv, msg)
    # Firmado por priv pero verificado contra otra identidad → rechazado.
    assert verify(other_pub, msg, sig) is False


@pytest.mark.parametrize("pub,sig", [
    ("", "AAAA"),
    ("notb64!!", "AAAA"),
    ("AAAA", ""),
    ("AAAA", "QQ=="),  # firma de largo inválido (no 64 bytes)
])
def test_entradas_invalidas_no_lanzan(pub, sig):
    assert verify(pub, b"msg", sig) is False
