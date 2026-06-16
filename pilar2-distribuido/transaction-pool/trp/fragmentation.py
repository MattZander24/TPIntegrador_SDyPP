"""Fragmentación del espacio de nonces (DOC U7.5: bolsa de tareas / granja).

El TrP subdivide el rango completo de búsqueda del nonce en fragmentos más
pequeños que los workers consumen en competencia/colaboración. El tamaño de
fragmento es configurable (Pilar 3 lo barre de 1% a 50%).
"""

from __future__ import annotations


def fragment_range(start: int, end: int, fragment_size: int) -> list[tuple[int, int]]:
    """Parte ``[start, end)`` en tramos ``[min, max)`` de a lo sumo ``fragment_size``."""
    if fragment_size <= 0:
        raise ValueError("fragment_size debe ser positivo")
    if end <= start:
        return []
    chunks = []
    cur = start
    while cur < end:
        chunks.append((cur, min(cur + fragment_size, end)))
        cur += fragment_size
    return chunks


def fragment_size_from_percent(space: int, percent: float) -> int:
    """Convierte un porcentaje de fragmentación (1–50%) a tamaño en nonces."""
    if not 0 < percent <= 100:
        raise ValueError("percent debe estar en (0, 100]")
    return max(1, int(space * percent / 100))
