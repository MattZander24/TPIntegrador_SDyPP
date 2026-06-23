"""Tests de verificación de firma de propuestas y nonces en el NCT (A-01)."""

import hashlib

import pytest

from common.identity import nonce_message, proposal_message, public_key_b64, sign
from nct.coordinator import NCTCoordinator

pytest.importorskip("cryptography", reason="requiere cryptography")


def solve(base, n_zeros):
    prefix = "0" * n_zeros
    nonce = 0
    while not hashlib.md5(f"{base}{nonce}".encode()).hexdigest().startswith(prefix):
        nonce += 1
    return nonce


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


def _keypair():
    from cryptography.hazmat.primitives.asymmetric import ec

    priv = ec.generate_private_key(ec.SECP256R1())
    return priv, public_key_b64(priv)


def _signed_proposal(priv, pub, *, action="promulgacion", text_hash="h1",
                     law_id="L1", created_at="t0"):
    msg = proposal_message(pub, action, text_hash, law_id, created_at)
    return {"law_id": law_id, "author_pubkey": pub, "text_hash": text_hash,
            "action": action, "created_at": created_at, "signature": sign(priv, msg)}


def test_require_signatures_rechaza_sin_firma(bus, store):
    challenges = []
    bus.on_challenge(challenges.append)
    make_nct(bus, store, Clock(), require_signatures=True)
    bus.publish_proposal({"law_id": "L1", "author_pubkey": "A",
                          "text_hash": "h1", "created_at": "t0"})
    assert challenges == []
    assert store.get_law("L1") is None


def test_require_signatures_acepta_firma_valida(bus, store):
    challenges = []
    bus.on_challenge(challenges.append)
    make_nct(bus, store, Clock(), require_signatures=True)
    priv, pub = _keypair()
    bus.publish_proposal(_signed_proposal(priv, pub))
    assert len(challenges) == 1
    assert store.get_law("L1") is not None


def test_firma_invalida_siempre_rechazada(bus, store):
    """Aun con require_signatures=False, una firma presente pero inválida se rechaza."""
    challenges = []
    bus.on_challenge(challenges.append)
    make_nct(bus, store, Clock(), require_signatures=False)
    priv, pub = _keypair()
    prop = _signed_proposal(priv, pub)
    prop["signature"] = prop["signature"][:-4] + "AAAA"  # firma corrupta
    bus.publish_proposal(prop)
    assert challenges == []


def test_suplantacion_de_autor_rechazada(bus, store):
    """Firmar con una clave y declarar otra author_pubkey → rechazado."""
    challenges = []
    bus.on_challenge(challenges.append)
    make_nct(bus, store, Clock(), require_signatures=True)
    priv, _ = _keypair()
    _, victim_pub = _keypair()
    prop = _signed_proposal(priv, victim_pub)  # firma de priv, autor = víctima
    bus.publish_proposal(prop)
    assert challenges == []


def test_created_at_obsoleto_rechazado_anti_replay(bus, store):
    challenges = []
    bus.on_challenge(challenges.append)
    make_nct(bus, store, Clock(t=10_000.0),
             require_signatures=True, proposal_max_age=300)
    priv, pub = _keypair()
    # created_at muy viejo respecto del reloj del NCT (10000s) → replay rechazado.
    prop = _signed_proposal(priv, pub,
                            created_at="1970-01-01T00:00:00+00:00")
    bus.publish_proposal(prop)
    assert challenges == []


def _open_window(bus, store):
    """Abre una ventana con una propuesta firmada y devuelve el challenge."""
    challenges = []
    bus.on_challenge(challenges.append)
    apriv, apub = _keypair()
    bus.publish_proposal(_signed_proposal(apriv, apub))
    return challenges[0], apub


def test_nonce_firmado_valido_sella_bloque(bus, store):
    make_nct(bus, store, Clock(), require_signatures=True)
    ch, _author = _open_window(bus, store)
    nonce = solve(ch["partial_hash_base"], ch["n_zeros_required"])
    wpriv, wpub = _keypair()
    sig = sign(wpriv, nonce_message(ch["voting_window_id"], nonce, wpub))
    bus.publish_nonce_response({
        "voting_window_id": ch["voting_window_id"], "nonce": nonce,
        "winning_node_or_pool": wpub, "signature": sig,
        "block_hash_candidato": "x",
    })
    assert store.chain_length() == 1


def test_nonce_sin_firma_rechazado_si_require(bus, store):
    make_nct(bus, store, Clock(), require_signatures=True)
    ch, _author = _open_window(bus, store)
    nonce = solve(ch["partial_hash_base"], ch["n_zeros_required"])
    bus.publish_nonce_response({
        "voting_window_id": ch["voting_window_id"], "nonce": nonce,
        "winning_node_or_pool": "pool-sin-firma", "block_hash_candidato": "x",
    })
    assert store.chain_length() == 0


def test_nonce_firma_invalida_rechazado(bus, store):
    make_nct(bus, store, Clock(), require_signatures=False)
    ch, _author = _open_window(bus, store)
    nonce = solve(ch["partial_hash_base"], ch["n_zeros_required"])
    wpriv, wpub = _keypair()
    sig = sign(wpriv, nonce_message(ch["voting_window_id"], nonce, wpub))
    bus.publish_nonce_response({
        "voting_window_id": ch["voting_window_id"], "nonce": nonce,
        "winning_node_or_pool": wpub, "signature": sig[:-4] + "AAAA",
        "block_hash_candidato": "x",
    })
    assert store.chain_length() == 0
