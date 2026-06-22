"""Integración extremo a extremo de Pilar 2 (sin broker: bus en memoria + fakeredis).

Cablea NCT + StandaloneWorker y el minero CPU de Pilar 1, y verifica el flujo
completo del criterio de aceptación:

    proponer ley → NCT abre ventana → worker resuelve el PoW →
    NCT sella el bloque → bloque en Redis con encadenamiento válido.

El bus en memoria despacha de forma síncrona, así que publicar la propuesta
dispara toda la cadena dentro de la misma llamada.
"""

import hashlib
import os

import pytest

from common.blockchain import validate_chain
from common.storage import LawStatus, WindowResult
from nct.coordinator import NCTCoordinator
from worker_pkg.miner import run_miner
from worker_pkg.standalone_worker import StandaloneWorker

CPU_SCRIPT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "pilar1-minero", "cpu", "src",
    "brute_force.py"))


def cpu_mine(base, prefix, rmin, rmax):
    return run_miner(base, prefix, rmin, rmax, prefer_gpu=False,
                     cpu_script=CPU_SCRIPT)


@pytest.fixture
def system(bus, store):
    """NCT + StandaloneWorker cableados sobre el mismo bus/almacén."""
    nct = NCTCoordinator(bus, store, n_zeros=2, window_seconds_promulgacion=300,
                         window_seconds_derogacion=300, cooldown_new=1,
                         cooldown_reproposed=2)
    nct.wire()
    worker = StandaloneWorker(bus, worker_id="worker-1", mine=cpu_mine, clock=lambda: 0)
    worker._rejected_actions = set()
    worker.wire()
    return nct, worker


@pytest.mark.integration
def test_e2e_promulgacion_sella_bloque_con_cadena_valida(system, store):
    bus_proposal = {"law_id": "ley-presupuesto", "author_pubkey": "ciudadano-A",
                    "text_hash": "sha256-del-texto", "created_at": "2026-06-16T00:00:00Z"}
    # publish_proposal dispara: ventana → minado → sellado
    system[0].m.publish_proposal(bus_proposal)

    assert store.chain_length() == 1
    law = store.get_law("ley-presupuesto")
    assert law["status"] == LawStatus.PROMULGATED

    block = store.get_chain()[0]
    assert block.law_id == "ley-presupuesto"
    assert block.action == "promulgacion"
    assert block.n_zeros_required == 2
    assert block.winning_node_or_pool == "worker-1"
    assert block.is_hash_valid()

    # El nonce sellado realmente satisface el desafío
    window = store.get_window(block.voting_window_id)
    h = hashlib.md5(f"{window['partial_hash_base']}{block.nonce}".encode()).hexdigest()
    assert h.startswith("00")

    # Cadena válida de punta a punta (encadenamiento + nonce)
    resolver = lambda b: store.get_window(b.voting_window_id)["partial_hash_base"]
    assert validate_chain(store.get_chain(), base_resolver=resolver) is True
    assert store.get_active_window() is None


@pytest.mark.integration
def test_e2e_dos_leyes_de_autores_distintos_encadenan(system, store):
    nct = system[0]
    nct.m.publish_proposal({"law_id": "L-A", "author_pubkey": "A",
                            "text_hash": "ha", "created_at": "t"})
    nct.m.publish_proposal({"law_id": "L-B", "author_pubkey": "B",
                            "text_hash": "hb", "created_at": "t"})
    assert store.chain_length() == 2
    chain = store.get_chain()
    # encadenamiento: el segundo apunta al hash del primero
    assert chain[1].previous_hash == chain[0].block_hash
    resolver = lambda b: store.get_window(b.voting_window_id)["partial_hash_base"]
    assert validate_chain(chain, base_resolver=resolver) is True


@pytest.mark.integration
def test_e2e_ventana_vencida_descarta_sin_sellar(bus, store):
    """Sin worker que resuelva, el deadline deja la ley discarded (no bloque)."""
    import time as _t
    clock = lambda: _t.time()
    nct = NCTCoordinator(bus, store, n_zeros=8, window_seconds_promulgacion=-1,
                         window_seconds_derogacion=-1, cooldown_new=1,
                         cooldown_reproposed=2)
    nct.wire()
    # n=8 ⇒ no se resuelve; deadline negativo ⇒ ya vencida al primer tick
    nct.m.publish_proposal({"law_id": "L-lenta", "author_pubkey": "A",
                            "text_hash": "h", "created_at": "t"})
    nct.check_deadline()
    assert store.chain_length() == 0
    assert store.get_law("L-lenta")["status"] == LawStatus.DISCARDED
    win_id = f"W1-L-lenta"
    assert store.get_window(win_id)["result"] == WindowResult.EXPIRED_PENDING
