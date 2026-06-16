"""Tests de fragmentación y del Transaction Pool."""

import pytest

from common.messaging import InMemoryBus
from trp.fragmentation import fragment_range, fragment_size_from_percent
from trp.pool import TransactionPool


def test_fragment_range_exacto():
    assert fragment_range(0, 100, 25) == [(0, 25), (25, 50), (50, 75), (75, 100)]


def test_fragment_range_con_resto():
    assert fragment_range(0, 10, 3) == [(0, 3), (3, 6), (6, 9), (9, 10)]


def test_fragment_range_vacio_o_invalido():
    assert fragment_range(10, 10, 5) == []
    with pytest.raises(ValueError):
        fragment_range(0, 10, 0)


def test_fragment_size_from_percent():
    assert fragment_size_from_percent(1000, 10) == 100
    assert fragment_size_from_percent(1000, 50) == 500
    with pytest.raises(ValueError):
        fragment_size_from_percent(1000, 0)


class Clock:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t


def _challenge():
    return {"voting_window_id": "W1", "law_id": "L1", "action": "promulgacion",
            "partial_hash_base": "base", "n_zeros_required": 2}


def test_pool_fragmenta_y_publica_tareas():
    bus = InMemoryBus()
    tareas = []
    bus.on_task(tareas.append)
    trp = TransactionPool(bus, nonce_space=100, fragment_size=25)
    trp.wire()
    bus.publish_challenge(_challenge())
    assert len(tareas) == 4
    assert tareas[0]["range_min"] == 0 and tareas[0]["range_max"] == 25
    assert tareas[-1]["range_max"] == 100
    assert all(t["voting_window_id"] == "W1" for t in tareas)
    assert all(t["n_zeros_required"] == 2 for t in tareas)


def test_pool_trackea_capacidad_por_keepalive():
    clock = Clock()
    bus = InMemoryBus()
    trp = TransactionPool(bus, nonce_space=100, fragment_size=50, clock=clock)
    trp.wire()
    bus.publish_keepalive({"worker_id": "w1", "capacity": 2, "has_gpu": True})
    assert trp._has_gpu_capacity() is True
    assert len(trp._fresh_workers()) == 1


def test_pool_keepalive_expira():
    clock = Clock()
    bus = InMemoryBus()
    trp = TransactionPool(bus, nonce_space=100, fragment_size=50, clock=clock)
    trp.wire()
    bus.publish_keepalive({"worker_id": "w1", "capacity": 1, "has_gpu": True})
    clock.t += 100  # supera el TTL
    assert trp._fresh_workers() == []
    assert trp._has_gpu_capacity() is False


def test_pool_loguea_sin_gpu_pero_no_cambia_dificultad(caplog):
    import logging
    bus = InMemoryBus()
    tareas = []
    bus.on_task(tareas.append)
    trp = TransactionPool(bus, nonce_space=50, fragment_size=50)
    trp.wire()
    with caplog.at_level(logging.WARNING, logger="voxchain.trp"):
        bus.publish_challenge(_challenge())
    assert any("escalar mineros CPU" in r.message for r in caplog.records)
    # La dificultad publicada sigue siendo la del NCT (n_zeros=2), sin reducir.
    assert tareas[0]["n_zeros_required"] == 2
