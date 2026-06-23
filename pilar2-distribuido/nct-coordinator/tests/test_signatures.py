"""Tests de verificación de firma de propuestas en el NCT (A-01 / AGENT.md 3.1)."""

import pytest

from common.identity import proposal_message, public_key_b64, sign
from nct.coordinator import NCTCoordinator

pytest.importorskip("cryptography", reason="requiere cryptography")


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
