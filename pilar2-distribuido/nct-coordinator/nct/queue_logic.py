"""Lógica pura de la cola de ventanas del NCT (AGENT.md 3.3–3.5).

Aislada de Redis y RabbitMQ para poder testearla de forma unitaria:

- ``select_next_law``: round-robin entre autores distintos (no FIFO estricto).
- ``cooldown_until``: cálculo del cooldown según la razón (nuevo vs reproposición).
- ``classify_proposal``: distingue propuesta nueva de reproposición idéntica por
  hash exacto del texto.
"""

from __future__ import annotations

from typing import Optional

from common.storage import CooldownReason


def select_next_law(pending_laws: list[dict], last_author: Optional[str]) -> Optional[dict]:
    """Elige la próxima ley para abrir ventana, en round-robin por autor.

    ``pending_laws`` viene ordenada de más antigua a más nueva. Se elige la ley
    más antigua cuyo autor sea distinto del último que tuvo ventana, para que un
    autor no monopolice turnos consecutivos. Si todas las pendientes son del
    mismo autor que el último (o no hay alternativa), se elige la más antigua.
    """
    if not pending_laws:
        return None
    if last_author is not None:
        for law in pending_laws:
            if law.get("author_pubkey") != last_author:
                return law
    return pending_laws[0]


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
