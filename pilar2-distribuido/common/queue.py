"""Lógica de cola de ventanas compartida entre NCT y API Gateway.

- ``select_next_law``: round-robin entre autores distintos (AGENT.md 3.3).
"""

from __future__ import annotations

from typing import Optional


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
