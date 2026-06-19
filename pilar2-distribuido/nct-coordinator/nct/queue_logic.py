"""Lógica pura de la cola de ventanas del NCT (AGENT.md 3.3–3.5).

Aislada de Redis y RabbitMQ para poder testearla de forma unitaria:

- ``select_next_law`` (reesportada desde ``common.queue``): round-robin entre
  autores distintos (no FIFO estricto).
- ``cooldown_until``: cálculo del cooldown según la razón (nuevo vs reproposición).
- ``classify_proposal``: distingue propuesta nueva de reproposición idéntica por
  hash exacto del texto.
"""

from __future__ import annotations

from common.queue import select_next_law  # noqa: F401  reexportada
from common.storage import CooldownReason


def classify_proposal(text_hash_was_discarded: bool) -> str:
    """Razón de cooldown: reproposición idéntica (3.5) vs propuesta nueva (3.4)."""
    return (CooldownReason.REPROPOSED_IDENTICAL if text_hash_was_discarded
            else CooldownReason.PROPOSED_NEW)


def cooldown_until(current_window: int, reason: str, *,
                   cooldown_new: int, cooldown_reproposed: int) -> int:
    """Ventana a partir de la cual el autor puede volver a proponer.

    La reproposición idéntica penaliza con un cooldown estrictamente mayor.
    """
    delta = (cooldown_reproposed if reason == CooldownReason.REPROPOSED_IDENTICAL
             else cooldown_new)
    return current_window + delta
