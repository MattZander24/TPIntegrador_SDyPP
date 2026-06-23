"""Verificación de firmas ECDSA P-256 sobre propuestas y nonces (A-01).

La identidad es un par ECDSA P-256 generado en el cliente (frontend Web Crypto o
``propose_law.py``). El servidor verifica la firma **contra la propia
``author_pubkey`` del mensaje**: esto impide suplantar una identidad existente
(proponer/votar en nombre de otro). No mitiga Sybil —un individuo puede generar
sus propias claves— que es una limitación documentada (AGENT.md 9).

Detalles de interoperabilidad con Web Crypto (``crypto.subtle``):

- **Clave pública:** exportada como ``spki`` DER y codificada en base64. Se carga
  con ``load_der_public_key``.
- **Firma:** Web Crypto produce ECDSA en formato **IEEE P1363** (``r || s`` crudo,
  64 bytes), mientras que ``cryptography`` espera **DER**. Hay que convertir con
  ``encode_dss_signature(r, s)``; omitirlo hace fallar TODA verificación.
- **Mensaje canónico:** una concatenación con delimitador y orden fijo (no JSON),
  para que el string firmado sea byte-idéntico entre TypeScript y Python sin
  depender de la canonicalización JSON.
"""

from __future__ import annotations

import base64

# El import de cryptography es diferido para no romper entornos de test que no
# lo tengan instalado y sólo ejerciten la lógica de dominio pura.

_SIG_RAW_LEN = 64  # P-256: r (32 bytes) || s (32 bytes)


def proposal_message(author_pubkey: str, action: str, text_hash: str,
                     law_id: str, created_at: str) -> bytes:
    """Mensaje canónico de una propuesta (debe coincidir byte a byte con el cliente)."""
    return f"{author_pubkey}|{action}|{text_hash}|{law_id}|{created_at}".encode()


def nonce_message(voting_window_id: str, nonce, winning_node_or_pool: str) -> bytes:
    """Mensaje canónico de una respuesta de nonce (fase 2: firma de pools/nodos)."""
    return f"{voting_window_id}|{nonce}|{winning_node_or_pool}".encode()


def sign(private_key, message: bytes) -> str:
    """Firma ``message`` con una clave privada EC y devuelve la firma cruda (r||s) en base64.

    ``private_key`` es un ``EllipticCurvePrivateKey`` de ``cryptography``. El formato
    de salida (P1363) es el mismo que produce Web Crypto, para que el lado servidor
    use el mismo ``verify`` tanto para firmas del frontend como del CLI/tests.
    """
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, utils

    der = private_key.sign(message, ec.ECDSA(hashes.SHA256()))
    r, s = utils.decode_dss_signature(der)
    raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return base64.b64encode(raw).decode()


def public_key_b64(private_key) -> str:
    """Deriva la ``author_pubkey`` (SPKI DER en base64) de una clave privada EC."""
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    der = private_key.public_key().public_bytes(
        Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    return base64.b64encode(der).decode()


def load_private_key(pem_path: str):
    """Carga una clave privada EC desde un archivo PEM (sin passphrase)."""
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    with open(pem_path, "rb") as fh:
        return load_pem_private_key(fh.read(), password=None)


def verify(pubkey_b64: str, message: bytes, signature_b64: str) -> bool:
    """Verifica una firma ECDSA P-256/SHA-256.

    ``pubkey_b64``: clave pública SPKI DER en base64 (igual que la exporta el
    frontend). ``signature_b64``: firma cruda P1363 (``r||s``) en base64.
    Devuelve ``False`` ante cualquier error (clave/firma malformada, no coincide),
    nunca lanza: el llamador rechaza el mensaje.
    """
    if not pubkey_b64 or not signature_b64:
        return False
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec, utils
        from cryptography.hazmat.primitives.serialization import load_der_public_key

        pub = load_der_public_key(base64.b64decode(pubkey_b64))
        if not isinstance(pub, ec.EllipticCurvePublicKey):
            return False
        raw = base64.b64decode(signature_b64)
        if len(raw) != _SIG_RAW_LEN:
            return False
        r = int.from_bytes(raw[:32], "big")
        s = int.from_bytes(raw[32:], "big")
        der_sig = utils.encode_dss_signature(r, s)
        try:
            pub.verify(der_sig, message, ec.ECDSA(hashes.SHA256()))
            return True
        except InvalidSignature:
            return False
    except Exception:
        return False
