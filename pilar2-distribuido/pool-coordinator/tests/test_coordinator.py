"""Tests para Pool Coordinator."""

from __future__ import annotations

import json
import time
from unittest import mock

import pytest
from common.messaging import Messaging

from pool_coordinator.coordinator import PoolCoordinator


class FakePipeline:
    def __init__(self, redis):
        self._redis = redis
        self._cmds = []

    def get(self, key):
        self._cmds.append(("get", key))
        return self

    def pttl(self, key):
        self._cmds.append(("pttl", key))
        return self

    def execute(self):
        results = []
        for cmd, key in self._cmds:
            if cmd == "get":
                results.append(self._redis._data.get(key))
            elif cmd == "pttl":
                results.append(5000 if key in self._redis._data else -2)
        return results


class FakeRedis:
    def __init__(self):
        self._data = {}

    def set(self, key, value, *, nx=False, ex=None):
        if nx and key in self._data:
            return None
        self._data[key] = value
        self._ttl = ex
        return True

    def get(self, key):
        return self._data.get(key)

    def setex(self, key, ttl, value):
        self._data[key] = value
        return True

    def pttl(self, key):
        return 5000 if key in self._data else -2

    def pipeline(self):
        return FakePipeline(self)


class FakeMessaging(Messaging):
    def __init__(self):
        self.published = []
        self.tasks_registered = []
        self._healthy = True

    def on_task(self, handler):
        self.tasks_registered.append(handler)

    def publish_nonce_response(self, msg):
        self.published.append(("nonce", msg))

    def publish_keepalive(self, msg):
        self.published.append(("keepalive", msg))

    def connect(self):
        pass

    def start_consuming(self, tick=None, tick_interval=1.0):
        pass

    def close(self):
        pass

    def is_healthy(self):
        return self._healthy

    def unsubscribe(self, handler):
        if handler in self.tasks_registered:
            self.tasks_registered.remove(handler)


@pytest.fixture
def coordinator():
    m = FakeMessaging()
    r = FakeRedis()
    c = PoolCoordinator(m, pool_id="test-pool", redis=r)
    c.try_acquire_leadership()
    return c


class TestPoolCoordinator:
    def test_leadership(self, coordinator):
        assert coordinator.is_leader
        pool_is_leader = coordinator.redis.get("pool:leader")
        assert pool_is_leader == "test-pool"

    def test_register_miner(self, coordinator):
        mid = coordinator.register_miner(capacity=2, has_gpu=True)
        assert mid.startswith("test-pool-miner-")
        assert len(coordinator._miners) == 1

    def test_heartbeat(self, coordinator):
        mid = coordinator.register_miner()
        assert coordinator.handle_heartbeat(mid) is True
        assert coordinator.handle_heartbeat("nonexistent") is False

    def test_get_next_task_no_miners(self, coordinator):
        task = coordinator.get_next_task("nonexistent")
        assert task is None

    def test_get_next_task_no_tasks(self, coordinator):
        mid = coordinator.register_miner()
        task = coordinator.get_next_task(mid)
        assert task is None

    def test_get_next_task_assigns_chunk(self, coordinator):
        mid1 = coordinator.register_miner(capacity=1)
        mid2 = coordinator.register_miner(capacity=1)
        coordinator.handle_task({
            "voting_window_id": "win-1",
            "law_id": "law-1",
            "action": "promulgacion",
            "partial_hash_base": "abc",
            "n_zeros_required": 4,
            "range_min": "0",
            "range_max": "1000",
        })
        t1 = coordinator.get_next_task(mid1)
        assert t1 is not None
        assert t1["range_min"] == 0
        assert t1["range_max"] == 500
        t2 = coordinator.get_next_task(mid2)
        assert t2 is not None

    def test_submit_result(self, coordinator):
        mid = coordinator.register_miner()
        result = {"voting_window_id": "win-1", "nonce": 42,
                   "block_hash_candidato": "0xdead"}
        ok = coordinator.submit_result(mid, result)
        assert ok is True
        # Verificar que se publicó el nonce
        nonce_published = any(
            msg_type == "nonce" and msg["nonce"] == 42
            for msg_type, msg in coordinator.m.published
        )
        assert nonce_published

    def test_purge_stale_miners(self, coordinator):
        mid = coordinator.register_miner()
        coordinator._miners[mid]["last_seen"] = 0  # simular miner muerto
        assert len(coordinator._miners) == 1
        coordinator._purge_stale_miners()
        assert len(coordinator._miners) == 0

    def test_keepalive_publishing(self, coordinator):
        coordinator.register_miner(capacity=2, has_gpu=True)
        coordinator.emit_keepalive()
        assert len(coordinator.m.published) > 0
        _, msg = coordinator.m.published[-1]
        assert msg["worker_id"] == "test-pool"
        assert msg["capacity"] >= 2

    def test_leader_renewal_failure(self, coordinator):
        coordinator.is_leader = True
        coordinator.redis._data["pool:leader"] = "other-instance"
        ok = coordinator.renew_leadership()
        assert ok is False
        assert coordinator.is_leader is False