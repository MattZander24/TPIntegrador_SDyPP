"""Identidad opcional del worker/pool para firmar respuestas de nonce (A-01 fase 2).

Si la variable de entorno ``WORKER_PRIVKEY_PEM`` apunta a una clave EC P-256 (PEM),
el worker firma cada nonce que publica y usa su clave pública como
``winning_node_or_pool``; así el NCT puede verificar la firma (y la regla 3.4 de
"el autor no gana su propia ventana" se vuelve exigible). Sin clave configurada,
el comportamiento es el de siempre: ``winning_node_or_pool`` es el id textual y no
se adjunta firma. La clave privada nunca se transmite (AGENT.md 3.1).
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger("voxchain.worker.identity")


class WorkerSigner:
    """Firma respuestas de nonce si hay una clave configurada; si no, no-op."""

    def __init__(self, privkey_pem_path: str = ""):
        self._key = None
        self.pubkey = None
        if privkey_pem_path:
            from common.identity import load_private_key, public_key_b64

            self._key = load_private_key(privkey_pem_path)
            self.pubkey = public_key_b64(self._key)
            log.info("worker firma nonces con identidad %s…", self.pubkey[:16])

    @classmethod
    def from_env(cls) -> "WorkerSigner":
        return cls(os.getenv("WORKER_PRIVKEY_PEM", ""))

    @property
    def enabled(self) -> bool:
        return self._key is not None

    def identity(self, fallback_id: str) -> str:
        """``winning_node_or_pool`` a publicar: la pubkey si firmamos, si no el id."""
        return self.pubkey if self.enabled else fallback_id

    def sign_nonce(self, voting_window_id: str, nonce: int, winner: str):
        """Firma ``voting_window_id|nonce|winner`` o devuelve ``None`` si no hay clave."""
        if not self.enabled:
            return None
        from common.identity import nonce_message, sign

        return sign(self._key, nonce_message(voting_window_id, nonce, winner))
