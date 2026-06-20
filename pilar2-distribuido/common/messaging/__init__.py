"""Mensajería de VoxChain sobre RabbitMQ (AGENT.md 5, Pilar 2 / P2).

Tres flujos canónicos hacia/desde el NCT (no agregar un cuarto que lo toque):

1. ``propuestas``       cola   nodo → NCT     (ley nueva)
2. ``desafio_activo``   topic  NCT → red      (desafío de la ventana abierta)
3. ``respuesta_nonce``  cola   red → NCT      (nonce ganador)

Más dos flujos **internos** de distribución de trabajo entre TrP y workers
(documentados en el README de Pilar 2; no tocan al NCT):

4. ``tareas_trp``       cola   TrP → workers  (rango de nonces asignado)
5. ``keepalive_trp``    cola   workers → TrP  (capacidad disponible)

``Messaging`` es la interfaz común; ``InMemoryBus`` la implementa para tests y
``RabbitMQMessaging`` para producción con pika.
"""

from .base import (
    Messaging,
    InMemoryBus,
    QUEUE_PROPUESTAS,
    EXCHANGE_DESAFIO,
    DESAFIO_ROUTING_KEY,
    DESAFIO_BINDING_KEY,
    QUEUE_RESPUESTA_NONCE,
    QUEUE_TAREAS,
    QUEUE_KEEPALIVE,
    EXCHANGE_HEARTBEAT,
    HEARTBEAT_ROUTING_KEY,
    HEARTBEAT_BINDING_KEY,
    QUEUE_ELECTION,
)

__all__ = [
    "Messaging",
    "InMemoryBus",
    "QUEUE_PROPUESTAS",
    "EXCHANGE_DESAFIO",
    "DESAFIO_ROUTING_KEY",
    "DESAFIO_BINDING_KEY",
    "QUEUE_RESPUESTA_NONCE",
    "QUEUE_TAREAS",
    "QUEUE_KEEPALIVE",
    "EXCHANGE_HEARTBEAT",
    "HEARTBEAT_ROUTING_KEY",
    "HEARTBEAT_BINDING_KEY",
    "QUEUE_ELECTION",
]


def build_rabbitmq(url: str):
    """Construye la implementación pika (import diferido para no exigir pika en tests)."""
    from common import config
    from .rabbitmq import RabbitMQMessaging

    return RabbitMQMessaging(url, ssl_ca_path=config.RABBITMQ_TLS_CA_PATH)
