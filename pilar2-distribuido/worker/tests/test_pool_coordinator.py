"""Tests para Pool Coordinator embebido."""

from __future__ import annotations

import json
import time
from unittest import mock

import pytest
from common.messaging import InMemoryBus, Messaging

from worker_pkg.pool_coordinator.coordinator import PoolCoordinator, fragment_range


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
        self.challenges_registered = []
        self._healthy = True

    def on_challenge(self, handler):
        self.challenges_registered.append(handler)

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
        if handler in self.challenges_registered:
            self.challenges_registered.remove(handler)


class TestFragmentation:
    def test_fragment_range_exacto(self):
        assert fragment_range(0, 100, 25) == [(0, 25), (25, 50), (50, 75), (75, 100)]

    def test_fragment_range_con_resto(self):
        assert fragment_range(0, 10, 3) == [(0, 3), (3, 6), (6, 9), (9, 10)]

    def test_fragment_range_vacio_o_invalido(self):
        assert fragment_range(10, 10, 5) == []
        with pytest.raises(ValueError):
            fragment_range(0, 10, 0)


class TestPoolCoordinator:
    @pytest.fixture
    def coordinator(self):
        m = FakeMessaging()
        r = FakeRedis()
        c = PoolCoordinator(m, pool_id="test-pool", redis=r, mine=lambda *a: (None, None))
        c._running = True
        c.try_acquire_leadership()
        return c

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

    def test_get_next_task_no_fragments(self, coordinator):
        mid = coordinator.register_miner()
        task = coordinator.get_next_task(mid)
        assert task is None

    def test_handle_challenge_fragmenta(self, coordinator):
        mid = coordinator.register_miner(capacity=1)
        coordinator.fragment_size = 25
        coordinator.nonce_space = 100
        coordinator.handle_challenge({
            "voting_window_id": "win-1",
            "law_id": "law-1",
            "action": "promulgacion",
            "partial_hash_base": "abc",
            "n_zeros_required": 4,
        })
        assert len(coordinator._pending_fragments) == 4

    def test_get_next_task_asigna_fragmento(self, coordinator):
        mid1 = coordinator.register_miner(capacity=1)
        coordinator.fragment_size = 25
        coordinator.nonce_space = 100
        coordinator.handle_challenge({
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
        assert "range_min" in t1
        assert "range_max" in t1

    def test_submit_result(self, coordinator):
        mid = coordinator.register_miner()
        result = {"voting_window_id": "win-1", "nonce": 42,
                   "block_hash_candidato": "0xdead"}
        ok = coordinator.submit_result(mid, result)
        assert ok is True
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

    def test_policy_accept(self, coordinator):
        coordinator.set_voting_policy({"decision": "accept"})
        assert coordinator._check_voting_policy({"action": "derogacion"}) is True
        assert coordinator._check_voting_policy({"action": "promulgacion"}) is True

    def test_policy_reject_action(self, coordinator):
        coordinator.set_voting_policy({"decision": "reject", "action": "derogacion"})
        assert coordinator._check_voting_policy({"action": "derogacion"}) is False
        assert coordinator._check_voting_policy({"action": "promulgacion"}) is True

    def test_policy_reject_all(self, coordinator):
        coordinator.set_voting_policy({"decision": "reject"})
        assert coordinator._check_voting_policy({"action": "promulgacion"}) is False
        assert coordinator._check_voting_policy({"action": "derogacion"}) is False

    def test_leader_renewal_failure(self, coordinator):
        coordinator.is_leader = True
        coordinator.redis._data["pool:leader"] = "other-instance"
        ok = coordinator.renew_leadership()
        assert ok is False
        assert coordinator.is_leader is False


class TestPoolWorkerReregistration:
    """Verifica que el pool-worker se re-registra cuando el coordinator lo pierde."""

    def _make_worker(self, post_side_effect):
        from worker_pkg.pool_worker import PoolWorker

        calls = {"register": 0}

        def fake_mine(*a):
            return (None, None)

        worker = PoolWorker(
            "http://coordinator:9001",
            miner_id="",
            mine=fake_mine,
        )

        def fake_register():
            calls["register"] += 1
            worker.miner_id = f"miner-{calls['register']}"
            worker._registered = True
            return True

        worker.register = fake_register
        worker._post = post_side_effect
        worker._get = lambda path: None
        return worker, calls

    def test_reregistra_cuando_heartbeat_dice_desconocido(self):
        """Si el coordinator responde ok:false, el worker se re-registra."""
        responses = iter([
            {"ok": False},   # heartbeat 1 → coordinator no conoce al miner
            {"ok": True},    # heartbeat 2 → ya re-registrado
        ])

        iteration = {"n": 0}

        def fake_post(path, data):
            if "/heartbeat" in path:
                resp = next(responses, {"ok": True})
                iteration["n"] += 1
                if iteration["n"] >= 2:
                    worker._running = False  # detener tras segunda iteración
                return resp
            return None

        worker, calls = self._make_worker(fake_post)
        worker.heartbeat_interval = 0  # forzar heartbeat en cada tick

        worker.run()

        assert calls["register"] == 2  # se registró dos veces

    def test_no_reregistra_cuando_coordinator_esta_caido(self):
        """Si el HTTP falla (resp None), el worker espera sin re-registrarse."""
        tick = {"n": 0}

        def fake_post(path, data):
            if "/heartbeat" in path:
                tick["n"] += 1
                if tick["n"] >= 3:
                    worker._running = False
                return None  # coordinator caído → HTTP falla

        worker, calls = self._make_worker(fake_post)
        worker.heartbeat_interval = 0

        worker.run()

        assert calls["register"] == 1  # solo el registro inicial
