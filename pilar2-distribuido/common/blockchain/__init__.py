"""Modelo de dominio de la blockchain de gobierno VoxChain.

- ``challenge``: serialización del desafío de gobierno y verificación de nonce.
- ``block``: modelo de bloque y cálculo de su hash.
- ``chain``: validación de la cadena de punta a punta.
"""

from .challenge import (
    ACTION_PROMULGACION,
    ACTION_DEROGACION,
    build_partial_hash_base,
    n_zeros_for_action,
    prefix_for_zeros,
    compute_hash,
    verify_nonce,
)
from .block import Block, seal_block
from .chain import validate_chain, validate_chain_links, ChainValidationError
from .compression import compress_text, decompress_text

__all__ = [
    "ACTION_PROMULGACION",
    "ACTION_DEROGACION",
    "build_partial_hash_base",
    "n_zeros_for_action",
    "prefix_for_zeros",
    "compute_hash",
    "verify_nonce",
    "Block",
    "seal_block",
    "validate_chain",
    "validate_chain_links",
    "ChainValidationError",
    "compress_text",
    "decompress_text",
]
