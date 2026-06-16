"""Validación de la cadena de bloques de VoxChain de punta a punta.

Dos niveles de validación:

- ``validate_chain_links``: encadenamiento autocontenido. El primer bloque
  referencia el génesis virtual; cada bloque referencia el ``block_hash`` del
  anterior y su ``block_hash`` recomputa correctamente.
- ``validate_chain``: lo anterior + que el ``nonce`` de cada bloque satisface la
  dificultad declarada. Como el bloque no almacena ``text_hash`` (esquema 7.3),
  reconstruir el ``partial_hash_base`` requiere un ``base_resolver`` que mapee un
  bloque a su base de desafío (el NCT lo resuelve desde la ventana en Redis).
"""

from __future__ import annotations

from typing import Callable, Sequence

from .block import Block, GENESIS_PREVIOUS_HASH
from .challenge import verify_nonce


class ChainValidationError(Exception):
    """La cadena no es válida; el mensaje indica el bloque y el motivo."""


def validate_chain_links(blocks: Sequence[Block]) -> bool:
    """Valida encadenamiento y ``block_hash`` de cada bloque.

    Lanza ``ChainValidationError`` con detalle si algo no cierra; devuelve True
    si la cadena (posiblemente vacía) es consistente.
    """
    expected_previous = GENESIS_PREVIOUS_HASH
    for i, block in enumerate(blocks):
        if not block.is_hash_valid():
            raise ChainValidationError(
                f"bloque {i} ({block.block_hash[:12]}…): block_hash no recomputa"
            )
        if block.previous_hash != expected_previous:
            raise ChainValidationError(
                f"bloque {i}: previous_hash {block.previous_hash[:12]}… "
                f"≠ esperado {expected_previous[:12]}…"
            )
        expected_previous = block.block_hash
    return True


def validate_chain(blocks: Sequence[Block],
                   base_resolver: Callable[[Block], str] | None = None) -> bool:
    """Valida encadenamiento + (si hay ``base_resolver``) el nonce de cada bloque."""
    validate_chain_links(blocks)
    if base_resolver is not None:
        for i, block in enumerate(blocks):
            base = base_resolver(block)
            ok, _ = verify_nonce(base, block.nonce, block.n_zeros_required)
            if not ok:
                raise ChainValidationError(
                    f"bloque {i}: nonce {block.nonce} no satisface "
                    f"{block.n_zeros_required} ceros para la ley {block.law_id}"
                )
    return True
