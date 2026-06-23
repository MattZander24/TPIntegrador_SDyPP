"""Interfaz de mensajería e implementación en memoria (para tests).

La interfaz es agnóstica del transporte: cada servicio recibe un objeto
``Messaging`` y registra callbacks. En producción se inyecta ``RabbitMQMessaging``;
en tests, ``InMemoryBus``, que despacha de forma síncrona y determinística.
"""

from __future__ import annotations

from typing import Callable

# --- Nombres de los flujos (mismos para in-memory y RabbitMQ) ---------------
QUEUE_PROPUESTAS = "propuestas"            # nodo → NCT
EXCHANGE_DESAFIO = "desafio_activo"        # NCT → red (topic)
DESAFIO_ROUTING_KEY = "desafio.activo"
DESAFIO_BINDING_KEY = "desafio.#"
QUEUE_RESPUESTA_NONCE = "respuesta_nonce"  # red → NCT
QUEUE_TAREAS = "tareas_trp"                # TrP → workers (interno)
QUEUE_KEEPALIVE = "keepalive_trp"          # workers → TrP (interno)

# Heartbeat del NCT activo (AGENT.md 4, P2):
# La elección de sucesor se resuelve vía Redis (elect_acquire_leadership),
# no vía mensajería, por lo que no existe cola nct_election.
EXCHANGE_HEARTBEAT = "nct.heartbeat"       # NCT activo → backups (topic)
HEARTBEAT_ROUTING_KEY = "nct.heartbeat.live"
HEARTBEAT_BINDING_KEY = "nct.heartbeat.#"

EXCHANGE_POOL_ELECTION = "pool.election"   # bully líder pool (topic)

# Topics (exchanges) → fan-out: cada consumidor recibe una copia.
# El resto son colas de trabajo → consumidores competidores (round-robin),
# igual que RabbitMQ reparte una cola entre sus consumidores.
BROADCAST_STREAMS = frozenset({EXCHANGE_DESAFIO, EXCHANGE_HEARTBEAT})

Handler = Callable[[dict], None]


class Messaging:
    """Contrato común. Las implementaciones concretas overridean estos métodos."""

    # -- publicación --
    def publish_proposal(self, law: dict) -> None: raise NotImplementedError
    def publish_challenge(self, challenge: dict) -> None: raise NotImplementedError
    def publish_nonce_response(self, solution: dict) -> None: raise NotImplementedError
    def publish_task(self, task: dict) -> None: raise NotImplementedError
    def publish_keepalive(self, keepalive: dict) -> None: raise NotImplementedError
    def publish_heartbeat(self, hb: dict) -> None: raise NotImplementedError
    def publish_pool_election(self, pool_id: str, msg: dict) -> None:
        raise NotImplementedError

    # -- suscripción (registra callback; se ejecutan al consumir) --
    def on_proposal(self, handler: Handler) -> None: raise NotImplementedError
    def on_challenge(self, handler: Handler) -> None: raise NotImplementedError
    def on_nonce_response(self, handler: Handler) -> None: raise NotImplementedError
    def on_task(self, handler: Handler) -> None: raise NotImplementedError
    def on_keepalive(self, handler: Handler) -> None: raise NotImplementedError
    def on_heartbeat(self, handler: Handler) -> None: raise NotImplementedError
    def on_pool_election(self, pool_id: str, handler: Handler) -> None:
        raise NotImplementedError
    def unsubscribe_pool_election(self) -> None:
        raise NotImplementedError

    # -- cancelación de consumo (gating por liderazgo, AGENT.md 4) --
    # Un NCT follower NO debe consumir las colas de trabajo (propuestas,
    # respuesta_nonce); deja de hacerlo cancelando su consumidor sobre ese stream.
    def unsubscribe(self, stream: str) -> None: raise NotImplementedError

    # Conjunto de streams que este nodo consume actualmente.
    def consumed_queues(self) -> set[str]: raise NotImplementedError

    # -- ciclo de vida --
    # tick: callback periódico para trabajo no disparado por mensajes
    # (apertura de ventana, chequeo de deadline, emisión de keep-alives).
    def start_consuming(self, tick: Callable[[], None] | None = None,
                        tick_interval: float = 1.0) -> None:
        raise NotImplementedError

    def close(self) -> None: pass


class InMemoryBus(Messaging):
    """Bus en proceso: ``publish_*`` despacha sincrónicamente a los handlers.

    Modela la topología de RabbitMQ para que el dominio corra idéntico en tests:

    - **Topics** (``desafio_activo``, ``nct.heartbeat``): fan-out, cada
      suscriptor recibe una copia.
    - **Colas de trabajo** (``propuestas``, ``respuesta_nonce``, ``tareas_trp``,
      ``keepalive_trp``): consumidores competidores; cada
      mensaje va a **un solo** consumidor en round-robin, igual que RabbitMQ
      reparte una cola. Por eso dos NCT suscritos a ``propuestas`` se reparten
      los mensajes (clave para el test del BUG 1: el follower no debe suscribirse).

    La semántica de "el primero gana" del NCT no se modela acá (eso lo decide el
    propio NCT con el cierre atómico en Redis); el bus sólo entrega los mensajes.
    """

    def __init__(self):
        self._handlers: dict[str, list[Handler]] = {}
        self._rr: dict[str, int] = {}  # cursor round-robin por cola de trabajo

    def _register(self, stream: str, handler: Handler) -> None:
        self._handlers.setdefault(stream, []).append(handler)

    def _dispatch(self, stream: str, payload: dict) -> None:
        handlers = self._handlers.get(stream)
        if not handlers:
            return
        if stream in BROADCAST_STREAMS:
            for handler in list(handlers):
                handler(payload)
            return
        # Cola de trabajo: round-robin entre consumidores competidores.
        idx = self._rr.get(stream, 0) % len(handlers)
        self._rr[stream] = idx + 1
        handlers[idx](payload)

    def unsubscribe(self, stream: str) -> None:
        self._handlers.pop(stream, None)
        self._rr.pop(stream, None)

    def consumed_queues(self) -> set[str]:
        return {s for s, hs in self._handlers.items() if hs}

    # publicación
    def publish_proposal(self, law): self._dispatch(QUEUE_PROPUESTAS, law)
    def publish_challenge(self, challenge): self._dispatch(EXCHANGE_DESAFIO, challenge)
    def publish_nonce_response(self, solution): self._dispatch(QUEUE_RESPUESTA_NONCE, solution)
    def publish_task(self, task): self._dispatch(QUEUE_TAREAS, task)
    def publish_keepalive(self, keepalive): self._dispatch(QUEUE_KEEPALIVE, keepalive)
    def publish_heartbeat(self, hb): self._dispatch(EXCHANGE_HEARTBEAT, hb)
    def publish_pool_election(self, pool_id, msg):
        self._dispatch(EXCHANGE_POOL_ELECTION, msg)

    # suscripción
    def on_proposal(self, handler): self._register(QUEUE_PROPUESTAS, handler)
    def on_challenge(self, handler): self._register(EXCHANGE_DESAFIO, handler)
    def on_nonce_response(self, handler): self._register(QUEUE_RESPUESTA_NONCE, handler)
    def on_task(self, handler): self._register(QUEUE_TAREAS, handler)
    def on_keepalive(self, handler): self._register(QUEUE_KEEPALIVE, handler)
    def on_heartbeat(self, handler): self._register(EXCHANGE_HEARTBEAT, handler)
    def on_pool_election(self, pool_id, handler):
        self._register(EXCHANGE_POOL_ELECTION, handler)
    def unsubscribe_pool_election(self):
        self.unsubscribe(EXCHANGE_POOL_ELECTION)

    def start_consuming(self, tick=None, tick_interval: float = 1.0) -> None:
        # En el bus en memoria el consumo es inmediato en publish; no hay loop.
        pass
