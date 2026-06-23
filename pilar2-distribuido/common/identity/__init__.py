"""Identidad criptográfica de VoxChain (AGENT.md 3.1).

La identidad de un individuo es su par de claves pública/privada. La clave
privada **nunca** sale del nodo (AGENT.md 3.1, 10): firma localmente y sólo
viaja la firma + la ``author_pubkey``. Este paquete contiene la verificación de
firmas del lado servidor (NCT/API); la firma del lado cliente la hace el
frontend (Web Crypto) o ``scripts/propose_law.py`` con la privkey local.
"""

from .signing import (
    nonce_message,
    proposal_message,
    public_key_b64,
    sign,
    verify,
)

__all__ = ["proposal_message", "nonce_message", "verify", "sign", "public_key_b64"]
