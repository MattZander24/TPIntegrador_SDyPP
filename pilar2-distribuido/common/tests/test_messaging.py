"""Tests del bus en memoria (la implementación RabbitMQ se cubre en e2e con broker)."""

from common.messaging import InMemoryBus


def test_inmemory_dispatch_a_un_handler():
    bus = InMemoryBus()
    recibidos = []
    bus.on_proposal(recibidos.append)
    bus.publish_proposal({"law_id": "L1"})
    assert recibidos == [{"law_id": "L1"}]


def test_inmemory_dispatch_a_multiples_suscriptores_del_topic():
    bus = InMemoryBus()
    a, b = [], []
    bus.on_challenge(a.append)
    bus.on_challenge(b.append)
    bus.publish_challenge({"voting_window_id": "W1"})
    assert a == b == [{"voting_window_id": "W1"}]


def test_flujos_independientes_no_se_cruzan():
    bus = InMemoryBus()
    props, nonces = [], []
    bus.on_proposal(props.append)
    bus.on_nonce_response(nonces.append)
    bus.publish_nonce_response({"nonce": 5})
    assert props == []
    assert nonces == [{"nonce": 5}]


def test_internos_tareas_y_keepalive():
    bus = InMemoryBus()
    tareas, kas = [], []
    bus.on_task(tareas.append)
    bus.on_keepalive(kas.append)
    bus.publish_task({"range_min": 0, "range_max": 100})
    bus.publish_keepalive({"worker_id": "w1", "capacity": 1})
    assert tareas == [{"range_min": 0, "range_max": 100}]
    assert kas == [{"worker_id": "w1", "capacity": 1}]
