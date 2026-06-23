"""Tests para Pool Coordinator embebido."""

from __future__ import annotations

import json
import threading
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
        self._list_data: dict = {}

    def set(self, key, value, *, nx=False, ex=None):
        if nx and key in self._data:
            return None
        self._data[key] = value
        return True

    def get(self, key):
        return self._data.get(key)

    def setex(self, key, ttl, value):
        self._data[key] = value
        return True

    def pttl(self, key):
        return 5000 if key in self._data else -2

    def lindex(self, key, index):
        lst = self._list_data.get(key, [])
        if not lst:
            return None
        try:
            return lst[index]
        except IndexError:
            return None

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


class TestPoolElection:
    """Tests para la elección Bully-by-effort del Pool Coordinator."""

    def _make_coordinator(self, pool_id="pool-A", election_n_zeros=1):
        m = FakeMessaging()
        r = FakeRedis()
        c = PoolCoordinator(
            m, pool_id=pool_id, redis=r,
            mine=lambda *a: (None, None),
            election_n_zeros=election_n_zeros,
        )
        c._running = True
        return c, r

    def test_run_pool_election_gana_cuando_no_hay_lider(self):
        from worker_pkg.pool_coordinator.election import run_pool_election

        r = FakeRedis()
        won = run_pool_election(r, "pool-A", n_zeros=1, lease_ttl=10)
        assert won is True
        assert r.get("pool:leader") == "pool-A"

    def test_run_pool_election_pierde_si_election_key_ya_existe(self):
        from worker_pkg.pool_coordinator.election import run_pool_election, ELECTION_EPOCH_SECONDS
        import time as _time

        r = FakeRedis()
        epoch = int(_time.time() / ELECTION_EPOCH_SECONDS)
        r._data[f"pool:election:{epoch}"] = "pool-B"  # otro ya ganó

        won = run_pool_election(r, "pool-A", n_zeros=1, lease_ttl=10)
        assert won is False
        assert r.get("pool:leader") is None

    def test_run_pool_election_pierde_claim_atomico(self):
        """Simula dos candidatos: pool-A llega primero al SET NX (claim)."""
        from worker_pkg.pool_coordinator.election import run_pool_election, ELECTION_EPOCH_SECONDS
        import time as _time

        epoch = int(_time.time() / ELECTION_EPOCH_SECONDS)

        calls = {"n": 0}
        original_set = FakeRedis.set

        r = FakeRedis()

        def rigged_set(self_r, key, value, *, nx=False, ex=None):
            # El primer SET NX sobre la election_key lo gana pool-B (inyectado antes)
            if nx and f"pool:election:{epoch}" in key:
                if calls["n"] == 0:
                    calls["n"] += 1
                    self_r._data[key] = "pool-B"  # pool-B ya lo puso
                    return None  # pool-A pierde
            return original_set(self_r, key, value, nx=nx, ex=ex)

        r.set = lambda *a, **kw: rigged_set(r, *a, **kw)

        won = run_pool_election(r, "pool-A", n_zeros=1, lease_ttl=10)
        assert won is False

    def test_tick_inicia_eleccion_cuando_no_hay_lider(self):
        """tick() dispara _maybe_start_election si no es líder y no hay lease."""
        c, r = self._make_coordinator(election_n_zeros=1)
        assert not c.is_leader

        c._last_lease_renew = 0  # forzar que tick() entre al bloque de lease
        c.tick()

        # Debe haberse iniciado un thread de elección
        assert c._election_thread is not None or c._election_in_progress or c.is_leader

    def test_tick_recoge_resultado_ganador(self):
        """tick() detecta que el thread terminó y actualiza is_leader."""
        c, r = self._make_coordinator(election_n_zeros=1)

        # Simular thread completado con éxito
        c._election_result = True
        c._election_in_progress = False
        dummy_thread = threading.Thread(target=lambda: None)
        dummy_thread.start()
        dummy_thread.join()  # asegurar que is_alive() == False
        c._election_thread = dummy_thread

        c.tick()
        assert c.is_leader is True

    def test_tick_no_inicia_segunda_eleccion_mientras_hay_una_en_curso(self):
        """_maybe_start_election no lanza otro thread si ya hay uno corriendo."""
        c, r = self._make_coordinator(election_n_zeros=1)
        c._election_in_progress = True

        c._last_lease_renew = 0
        c.tick()

        # No debe haber creado un nuevo thread (el existente sigue)
        assert c._election_thread is None

    def test_tick_no_inicia_eleccion_si_otro_es_lider(self):
        """Si ya hay un lider distinto en Redis, no se inicia elección."""
        c, r = self._make_coordinator(election_n_zeros=1)
        r._data["pool:leader"] = "pool-B"

        c._last_lease_renew = 0
        c.tick()

        assert c._election_thread is None
        assert not c._election_in_progress

    def test_eleccion_end_to_end_con_thread_real(self):
        """El thread de elección se ejecuta y el coordinador asume liderazgo."""
        c, r = self._make_coordinator(election_n_zeros=1)

        c._last_lease_renew = 0
        c.tick()  # dispara el thread

        # Esperar a que el thread termine (n_zeros=1 es trivialmente rápido)
        if c._election_thread:
            c._election_thread.join(timeout=5)

        c.tick()  # recoger resultado
        assert c.is_leader is True
        assert r.get("pool:leader") == "pool-A"
