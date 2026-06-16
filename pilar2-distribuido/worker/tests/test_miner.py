"""Tests del puente al minero y de la lógica del worker."""

import hashlib
import os
import sys

from common.messaging import InMemoryBus
from worker_pkg.miner import parse_miner_output, run_miner
from worker_pkg.worker import Worker

CPU_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "..", "..",
                          "pilar1-minero", "cpu", "src", "brute_force.py")


def test_parse_salida_cpu():
    out = 'Nonce = 12345\nMD5("base12345") = 0000abcdef0000abcdef0000abcdef00'
    nonce, h = parse_miner_output(out)
    assert nonce == 12345
    assert h == "0000abcdef0000abcdef0000abcdef00"


def test_parse_salida_gpu():
    out = "Nonce = 777\nMD5 = 000ffacebabe0000facebabe00001234"
    nonce, h = parse_miner_output(out)
    assert nonce == 777
    assert h == "000ffacebabe0000facebabe00001234"


def test_parse_sin_solucion():
    assert parse_miner_output("No encontrado") == (None, None)
    assert parse_miner_output("No se encontró nonce en el rango especificado") == (None, None)


def test_run_miner_cpu_real_encuentra_nonce():
    """Integra de verdad con el minero CPU de Pilar 1 (sin GPU)."""
    base = "L1hW1promulgacion"
    nonce, h = run_miner(base, "00", 0, 1_000_000, prefer_gpu=False,
                         cpu_script=os.path.abspath(CPU_SCRIPT))
    assert nonce is not None
    assert hashlib.md5(f"{base}{nonce}".encode()).hexdigest().startswith("00")
    assert h.startswith("00")


def test_worker_publica_nonce_cuando_encuentra():
    bus = InMemoryBus()
    publicados = []
    bus.on_nonce_response(publicados.append)

    def fake_mine(base, prefix, rmin, rmax):
        return 42, "0000deadbeef0000deadbeef00001234"

    w = Worker(bus, worker_id="w1", mine=fake_mine)
    w.wire()
    bus.publish_task({"voting_window_id": "W1", "partial_hash_base": "base",
                      "n_zeros_required": 4, "range_min": 0, "range_max": 100})
    assert len(publicados) == 1
    assert publicados[0]["nonce"] == 42
    assert publicados[0]["winning_node_or_pool"] == "w1"


def test_worker_es_idempotente_por_ventana():
    bus = InMemoryBus()
    publicados = []
    bus.on_nonce_response(publicados.append)
    calls = []

    def fake_mine(base, prefix, rmin, rmax):
        calls.append((rmin, rmax))
        return 1, "h"

    w = Worker(bus, worker_id="w1", mine=fake_mine)
    w.wire()
    task = {"voting_window_id": "W1", "partial_hash_base": "base",
            "n_zeros_required": 1, "range_min": 0, "range_max": 100}
    bus.publish_task(task)
    bus.publish_task({**task, "range_min": 100, "range_max": 200})  # reasignación
    assert len(publicados) == 1  # no re-publica para la misma ventana
    assert len(calls) == 1


def test_worker_no_publica_si_no_hay_solucion():
    bus = InMemoryBus()
    publicados = []
    bus.on_nonce_response(publicados.append)
    w = Worker(bus, worker_id="w1", mine=lambda *a: (None, None))
    w.wire()
    bus.publish_task({"voting_window_id": "W1", "partial_hash_base": "base",
                      "n_zeros_required": 4, "range_min": 0, "range_max": 100})
    assert publicados == []


def test_worker_keepalive():
    bus = InMemoryBus()
    kas = []
    bus.on_keepalive(kas.append)
    w = Worker(bus, worker_id="w1", mine=lambda *a: (None, None), capacity=3,
               has_gpu=True)
    w.emit_keepalive()
    assert kas[0]["worker_id"] == "w1"
    assert kas[0]["capacity"] == 3
    assert kas[0]["has_gpu"] is True
