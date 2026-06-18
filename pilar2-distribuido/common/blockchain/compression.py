"""Compresión de textos de leyes para almacenamiento en blockchain.

El ``text_hash`` del desafío PoW se calcula sobre el texto **original** (sin
comprimir). El ``text_compressed`` se almacena en el bloque para preservar el
contenido de la ley dentro de la cadena, sin depender de MinIO.
"""

from __future__ import annotations

import base64
import gzip


def compress_text(text: str) -> str:
    """Comprime texto con gzip y codifica en base64.

    Útil para leyes (lenguaje natural): compresión típica 2x–5x.
    """
    compressed = gzip.compress(text.encode("utf-8"))
    return base64.b64encode(compressed).decode("ascii")


def decompress_text(compressed: str) -> str:
    """Decodifica base64 y descomprime gzip, devuelve el texto original."""
    raw = base64.b64decode(compressed)
    return gzip.decompress(raw).decode("utf-8")
