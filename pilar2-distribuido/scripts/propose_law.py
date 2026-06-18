"""Publica una propuesta de ley en la cola `propuestas` (flujo 1: nodo → NCT).

Es el "nodo individual" que propone: genera el hash del texto y publica. La clave
privada NO interviene ni se transmite (AGENT.md 10): sólo viaja la author_pubkey.

Uso:
    python scripts/propose_law.py --text "Texto de la ley" --author pk-ciudadano-1
    python scripts/propose_law.py --law-id ley-x --action derogacion --author pk2

Requiere RABBITMQ_URL en el entorno (por defecto el del docker-compose).
"""

from __future__ import annotations

import argparse
import hashlib
import uuid
from datetime import datetime, timezone

from common import config
from common.blockchain import ACTION_PROMULGACION, compress_text
from common.messaging import build_rabbitmq


def main() -> None:
    ap = argparse.ArgumentParser(description="Proponer una ley a VoxChain")
    ap.add_argument("--text", default=None, help="texto de la ley (se hashea y comprime)")
    ap.add_argument("--text-hash", default=None,
                    help="hash del texto ya calculado (alternativa a --text)")
    ap.add_argument("--author", required=True, help="author_pubkey del proponente")
    ap.add_argument("--law-id", default=None,
                    help="id de la ley (obligatorio para derogación)")
    ap.add_argument("--action", default=ACTION_PROMULGACION,
                    choices=["promulgacion", "derogacion"])
    args = ap.parse_args()

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

    law = {
        "law_id": args.law_id or f"ley-{uuid.uuid4().hex[:8]}",
        "author_pubkey": args.author,
        "text_hash": text_hash,
        "text_compressed": text_compressed,
        "text_original_len": text_original_len,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "action": args.action,
    }

    messaging = build_rabbitmq(config.RABBITMQ_URL)
    messaging.connect()
    messaging.publish_proposal(law)
    messaging.close()
    print(f"propuesta publicada: {law}")


if __name__ == "__main__":
    main()
