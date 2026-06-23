"""Genera payloads de propuesta válidos para las pruebas de estrés.

Soporta dos modos:
- Sin firma (default): más rápido, válido cuando REQUIRE_SIGNATURES=false.
- Con firma ECDSA P-256: mide el overhead real del camino firmado.

Cada `Identity` tiene su propio `author_pubkey`, por lo que N identidades
distintas evitan que el cooldown de una bloquee a las demás.
"""

from __future__ import annotations

import hashlib
import threading
import uuid
from datetime import datetime, timezone
from typing import Iterator


# ── Identidad sin firma (default para stress) ──────────────────────────────

class UnsignedIdentity:
    """Identidad ligera: solo necesita un pubkey único."""

    def __init__(self, pubkey: str | None = None):
        self.pubkey = pubkey or f"stress-{uuid.uuid4().hex[:12]}"

    def make_proposal(self, text: str, action: str = "promulgacion",
                      law_id: str | None = None) -> dict:
        return {
            "law_id": law_id or f"ley-{uuid.uuid4().hex[:8]}",
            "author_pubkey": self.pubkey,
            "text": text,
            "action": action,
        }


# ── Identidad con firma ECDSA P-256 ────────────────────────────────────────

class SignedIdentity:
    """Par ECDSA P-256 que genera propuestas firmadas (A-01)."""

    def __init__(self):
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        import base64

        self._privkey = ec.generate_private_key(ec.SECP256R1())
        der = self._privkey.public_key().public_bytes(
            Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
        self.pubkey = base64.b64encode(der).decode()

    def make_proposal(self, text: str, action: str = "promulgacion",
                      law_id: str | None = None) -> dict:
        import base64
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

        text_hash = hashlib.sha256(text.encode()).hexdigest()
        law_id = law_id or f"ley-{uuid.uuid4().hex[:8]}"
        created_at = datetime.now(timezone.utc).isoformat()

        msg = f"{self.pubkey}|{action}|{text_hash}|{law_id}|{created_at}".encode()
        der_sig = self._privkey.sign(msg, ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der_sig)
        raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")

        return {
            "law_id": law_id,
            "author_pubkey": self.pubkey,
            "text": text,
            "text_hash": text_hash,
            "action": action,
            "created_at": created_at,
            "signature": base64.b64encode(raw).decode(),
        }


# ── Pool de identidades ────────────────────────────────────────────────────

class IdentityPool:
    """Pool de N identidades con reparto round-robin thread-safe.

    Mantener múltiples identidades evita que el cooldown por autor
    bloquee el flujo de propuestas durante pruebas de alta tasa.
    """

    def __init__(self, n: int, signed: bool = False):
        cls = SignedIdentity if signed else UnsignedIdentity
        self._ids = [cls() for _ in range(n)]
        self._lock = threading.Lock()
        self._idx = 0

    def next(self):
        with self._lock:
            identity = self._ids[self._idx % len(self._ids)]
            self._idx += 1
        return identity

    def __iter__(self) -> Iterator:
        return iter(self._ids)


# ── Generadores de texto ───────────────────────────────────────────────────

def unique_text(prefix: str = "stress", seq: int | None = None) -> str:
    """Texto único que evita colisiones de text_hash entre propuestas."""
    suffix = uuid.uuid4().hex if seq is None else f"{seq:06d}-{uuid.uuid4().hex[:6]}"
    return (
        f"[{prefix}] Artículo de ley de prueba de estrés #{suffix}. "
        "Este texto fue generado automáticamente para verificar el comportamiento "
        "del sistema bajo carga sostenida. No tiene validez legal."
    )


def derogation_text(law_id: str) -> str:
    return f"Derogatoria de {law_id}: se deja sin efecto por decisión del cuerpo legislativo."
