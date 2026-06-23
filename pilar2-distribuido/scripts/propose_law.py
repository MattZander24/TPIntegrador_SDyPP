"""Publica una propuesta de ley en la cola `propuestas` (flujo 1: nodo → NCT).

Es el "nodo individual" que propone: calcula el hash del texto, **firma la
propuesta con su clave privada local** y publica. La clave privada nunca se
transmite (AGENT.md 3.1/10): firma localmente y sólo viaja la firma + la
author_pubkey, que se deriva de la propia clave.

Uso (firmado, recomendado):
    python scripts/propose_law.py --text "Texto de la ley" --privkey id_ec.pem
    python scripts/propose_law.py --law-id ley-x --action derogacion --privkey id_ec.pem

Uso legacy (sin firma; sólo si REQUIRE_SIGNATURES está desactivado):
    python scripts/propose_law.py --text "Texto" --author pk-ciudadano-1

Generar una identidad EC P-256:
    openssl ecparam -name prime256v1 -genkey -noout -out id_ec.pem

Requiere RABBITMQ_URL en el entorno (por defecto el del docker-compose).
"""

from __future__ import annotations

import argparse
import hashlib
import uuid
from datetime import datetime, timezone

from common import config
from common.blockchain import ACTION_PROMULGACION, compress_text
from common.identity import proposal_message, public_key_b64, sign
from common.messaging import build_rabbitmq


def _load_private_key(path: str):
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    with open(path, "rb") as fh:
        return load_pem_private_key(fh.read(), password=None)


def main() -> None:
    ap = argparse.ArgumentParser(description="Proponer una ley a VoxChain")
    ap.add_argument("--text", default=None, help="texto de la ley (se hashea y comprime)")
    ap.add_argument("--text-hash", default=None,
                    help="hash del texto ya calculado (alternativa a --text)")
    ap.add_argument("--privkey", default=None,
                    help="ruta a la clave privada EC P-256 (PEM); firma la propuesta")
    ap.add_argument("--author", default=None,
                    help="author_pubkey (si no se usa --privkey; modo legacy sin firma)")
    ap.add_argument("--law-id", default=None,
                    help="id de la ley (obligatorio para derogación)")
    ap.add_argument("--action", default=ACTION_PROMULGACION,
                    choices=["promulgacion", "derogacion"])
    args = ap.parse_args()

    if not args.privkey and not args.author:
        ap.error("hace falta --privkey (firmado) o --author (legacy sin firma)")

    if args.text:
        text_hash = hashlib.sha256(args.text.encode()).hexdigest()
        text_compressed = compress_text(args.text)
        text_original_len = len(args.text)
    elif args.text_hash:
        text_hash = args.text_hash
        text_compressed = ""
        text_original_len = 0
    else:
        ap.error("hace falta --text o --text-hash")

    private_key = _load_private_key(args.privkey) if args.privkey else None
    author = public_key_b64(private_key) if private_key else args.author
    law_id = args.law_id or f"ley-{uuid.uuid4().hex[:8]}"
    created_at = datetime.now(timezone.utc).isoformat()

    law = {
        "law_id": law_id,
        "author_pubkey": author,
        "text_hash": text_hash,
        "text_compressed": text_compressed,
        "text_original_len": text_original_len,
        "created_at": created_at,
        "action": args.action,
    }

    if private_key is not None:
        msg = proposal_message(author, args.action, text_hash, law_id, created_at)
        law["signature"] = sign(private_key, msg)

    messaging = build_rabbitmq(config.RABBITMQ_URL)
    messaging.connect()
    messaging.publish_proposal(law)
    messaging.close()
    print(f"propuesta publicada: {law}")


if __name__ == "__main__":
    main()
