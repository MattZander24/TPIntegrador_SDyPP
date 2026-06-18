"""Implementación de ``Messaging`` sobre RabbitMQ con pika (BlockingConnection).

Un único hilo por servicio: se consume con ``process_data_events`` y se publica
sobre el mismo canal, intercalando trabajo periódico vía el callback ``tick``.
La topología (colas + exchange topic) se declara de forma idempotente al conectar.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Callable

import pika

from .base import (
    Messaging,
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

log = logging.getLogger("voxchain.messaging")


class RabbitMQMessaging(Messaging):
    def __init__(self, url: str, connect_retries: int = 30,
                 retry_delay: float = 2.0):
        self.url = url
        self.connect_retries = connect_retries
        self.retry_delay = retry_delay
        self._conn = None
        self._ch = None
        self._handlers: dict[str, Callable[[dict], None]] = {}

    # -- conexión / topología ----------------------------------------------
    def connect(self) -> None:
        params = pika.URLParameters(self.url)
        last_err = None
        for attempt in range(1, self.connect_retries + 1):
            try:
                self._conn = pika.BlockingConnection(params)
                self._ch = self._conn.channel()
                self._declare_topology()
                log.info("conectado a RabbitMQ (%s)", self.url)
                return
            except pika.exceptions.AMQPConnectionError as exc:  # pragma: no cover
                last_err = exc
                log.warning("RabbitMQ no disponible (intento %d/%d), reintento en %.0fs",
                            attempt, self.connect_retries, self.retry_delay)
                time.sleep(self.retry_delay)
        raise RuntimeError(f"no se pudo conectar a RabbitMQ: {last_err}")

    def _declare_topology(self) -> None:
        ch = self._ch
        ch.queue_declare(queue=QUEUE_PROPUESTAS, durable=True)
        ch.queue_declare(queue=QUEUE_RESPUESTA_NONCE, durable=True)
        ch.queue_declare(queue=QUEUE_TAREAS, durable=True)
        ch.queue_declare(queue=QUEUE_KEEPALIVE, durable=True)
        ch.queue_declare(queue=QUEUE_ELECTION, durable=True)
        ch.exchange_declare(exchange=EXCHANGE_DESAFIO, exchange_type="topic",
                            durable=True)
        ch.exchange_declare(exchange=EXCHANGE_HEARTBEAT, exchange_type="topic",
                            durable=True)
        ch.basic_qos(prefetch_count=1)

    def is_healthy(self) -> bool:
        return bool(self._conn and self._conn.is_open)

    # -- publicación --------------------------------------------------------
    def _publish(self, exchange: str, routing_key: str, payload: dict) -> None:
        if self._ch is None:
            self.connect()
        self._ch.basic_publish(
            exchange=exchange,
            routing_key=routing_key,
            body=json.dumps(payload).encode(),
            properties=pika.BasicProperties(delivery_mode=2),  # persistente
        )

    def publish_proposal(self, law): self._publish("", QUEUE_PROPUESTAS, law)
    def publish_challenge(self, challenge):
        self._publish(EXCHANGE_DESAFIO, DESAFIO_ROUTING_KEY, challenge)
    def publish_nonce_response(self, solution):
        self._publish("", QUEUE_RESPUESTA_NONCE, solution)
    def publish_task(self, task): self._publish("", QUEUE_TAREAS, task)
    def publish_keepalive(self, keepalive): self._publish("", QUEUE_KEEPALIVE, keepalive)
    def publish_heartbeat(self, hb):
        self._publish(EXCHANGE_HEARTBEAT, HEARTBEAT_ROUTING_KEY, hb)
    def publish_election_claim(self, claim):
        self._publish("", QUEUE_ELECTION, claim)

    # -- suscripción --------------------------------------------------------
    def on_proposal(self, handler): self._handlers[QUEUE_PROPUESTAS] = handler
    def on_nonce_response(self, handler): self._handlers[QUEUE_RESPUESTA_NONCE] = handler
    def on_task(self, handler): self._handlers[QUEUE_TAREAS] = handler
    def on_keepalive(self, handler): self._handlers[QUEUE_KEEPALIVE] = handler
    def on_challenge(self, handler): self._handlers[EXCHANGE_DESAFIO] = handler
    def on_heartbeat(self, handler): self._handlers[EXCHANGE_HEARTBEAT] = handler
    def on_election_claim(self, handler): self._handlers[QUEUE_ELECTION] = handler

    def _bind_consumers(self) -> None:
        for stream, handler in self._handlers.items():
            if stream in (EXCHANGE_DESAFIO, EXCHANGE_HEARTBEAT):
                result = self._ch.queue_declare(queue="", exclusive=True)
                qname = result.method.queue
                binding_key = (DESAFIO_BINDING_KEY if stream == EXCHANGE_DESAFIO
                               else HEARTBEAT_BINDING_KEY)
                self._ch.queue_bind(exchange=stream, queue=qname,
                                    routing_key=binding_key)
            else:
                qname = stream
            self._ch.basic_consume(queue=qname,
                                   on_message_callback=self._wrap(handler))

    def _wrap(self, handler: Callable[[dict], None]):
        def _cb(ch, method, properties, body):
            try:
                payload = json.loads(body.decode())
                handler(payload)
            except Exception:  # noqa: BLE001
                log.exception("error procesando mensaje en %s", method.routing_key)
            finally:
                ch.basic_ack(delivery_tag=method.delivery_tag)
        return _cb

    # -- ciclo de vida ------------------------------------------------------
    def start_consuming(self, tick=None, tick_interval: float = 1.0) -> None:
        if self._ch is None:
            self.connect()
        self._bind_consumers()
        log.info("consumiendo (%s)", ", ".join(self._handlers) or "sin handlers")
        while True:
            self._conn.process_data_events(time_limit=tick_interval)
            if tick is not None:
                tick()

    def close(self) -> None:
        try:
            if self._conn and self._conn.is_open:
                self._conn.close()
        except Exception:  # pragma: no cover
            pass
