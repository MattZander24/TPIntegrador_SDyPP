"""Tests de los dos bugs del NCT detectados con el stack real.

- BUG 1: la suscripción a las colas de trabajo (``propuestas``,
  ``respuesta_nonce``) está gateada por liderazgo. Un follower no compite por
  ellas, así que el standby no se "traga" propuestas por el reparto round-robin.
- BUG 2: el primer nonce válido recibido cierra la ventana de forma atómica
  (guard en Redis); las soluciones válidas tardías para la misma ventana se
  descartan y no sobrescriben el bloque sellado.
"""

import hashlib

from common.messaging import (
    EXCHANGE_HEARTBEAT,
    QUEUE_ELECTION,
    QUEUE_PROPUESTAS,
    QUEUE_RESPUESTA_NONCE,
)
from nct.coordinator import NCTCoordinator
from nct.monitor import NCTHeartbeatMonitor


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def _nct(bus, store, *, nct_id, is_leader, **kw):
    params = dict(n_zeros=2, window_seconds_promulgacion=60,
                  window_seconds_derogacion=90, cooldown_new=0,
                  cooldown_reproposed=0, nct_id=nct_id, is_leader=is_leader)
    params.update(kw)
    nct = NCTCoordinator(bus, store, **params)
    nct.wire()
    return nct


def _follower_node(bus, store):
    """Un nodo NCT en standby: coordinator (follower) + monitor de heartbeats."""
    nct = _nct(bus, store, nct_id="nct-standby", is_leader=False)
    monitor = NCTHeartbeatMonitor(
        bus, store, candidate_id="nct-standby", election_n_zeros=2,
        heartbeat_timeout=12, on_elected=nct.become_leader)
    monitor.wire()
    return nct, monitor


def _solve_from(base, n_zeros, start=0):
    prefix = "0" * n_zeros
    nonce = start
    while not hashlib.md5(f"{base}{nonce}".encode()).hexdigest().startswith(prefix):
        nonce += 1
    return nonce


# ---- BUG 1: gating de suscripción por liderazgo ---------------------------

def test_follower_no_consume_colas_de_trabajo(bus, store):
    """Un follower escucha heartbeat/elección pero NO las colas de trabajo."""
    nct, _ = _follower_node(bus, store)
    consumidas = bus.consumed_queues()
    assert QUEUE_PROPUESTAS not in consumidas
    assert QUEUE_RESPUESTA_NONCE not in consumidas
    assert EXCHANGE_HEARTBEAT in consumidas
    assert QUEUE_ELECTION in consumidas
    assert nct.consumed_work_queues() == set()


def test_promocion_a_lider_abre_las_colas_de_trabajo(bus, store):
    """Al ganar la elección (become_leader), el follower abre las colas de trabajo."""
    nct, _ = _follower_node(bus, store)
    nct.become_leader()
    consumidas = bus.consumed_queues()
    assert QUEUE_PROPUESTAS in consumidas
    assert QUEUE_RESPUESTA_NONCE in consumidas
    assert nct.consumed_work_queues() == {QUEUE_PROPUESTAS, QUEUE_RESPUESTA_NONCE}


def test_step_down_cierra_las_colas_de_trabajo(bus, store):
    """Un líder que pierde el liderazgo deja de consumir las colas de trabajo."""
    leader = _nct(bus, store, nct_id="nct-leader", is_leader=True)
    assert leader.consumed_work_queues() == {QUEUE_PROPUESTAS, QUEUE_RESPUESTA_NONCE}
    leader.step_down()
    assert leader.consumed_work_queues() == set()


def test_standby_no_roba_propuestas_cero_perdidas(bus, store):
    """Líder + follower suscritos: las N propuestas se persisten (sin pérdidas).

    Sin el gating del BUG 1 el follower también consumiría ``propuestas`` y, por
    el reparto round-robin, se quedaría con ~la mitad de los mensajes (que ackea
    y descarta por no ser líder), perdiéndolos."""
    leader = _nct(bus, store, nct_id="nct-leader", is_leader=True)
    follower = _nct(bus, store, nct_id="nct-standby", is_leader=False)
    assert leader and follower  # ambos cableados sobre el mismo bus

    n = 8
    for i in range(n):
        bus.publish_proposal({"law_id": f"L{i}", "author_pubkey": f"autor-{i}",
                              "text_hash": f"h{i}", "created_at": "t"})

    persistidas = [f"L{i}" for i in range(n) if store.get_law(f"L{i}")]
    assert len(persistidas) == n, f"se perdieron propuestas: sólo {persistidas}"


# ---- BUG 2: cierre atómico al primer nonce válido recibido ----------------

def test_primer_nonce_valido_recibido_gana_no_el_mas_chico(bus, store):
    """Dos nonces válidos para la misma ventana: gana el que llegó PRIMERO.

    Se publica primero el nonce mayor (como en la evidencia: el de worker-2,
    1000169, llegó antes que el de worker-1, 72175). El bloque debe sellarse con
    el primero recibido, no con el más chico, y el tardío se descarta."""
    clock = Clock()
    challenges = []
    bus.on_challenge(challenges.append)
    _nct(bus, store, nct_id="nct-leader", is_leader=True, clock=clock)

    bus.publish_proposal({"law_id": "L1", "author_pubkey": "A",
                          "text_hash": "h1", "created_at": "t0"})
    ch = challenges[0]
    n_menor = _solve_from(ch["partial_hash_base"], ch["n_zeros_required"], 0)
    n_mayor = _solve_from(ch["partial_hash_base"], ch["n_zeros_required"], n_menor + 1)
    assert n_menor != n_mayor

    # Llega PRIMERO el nonce mayor; luego (tardío) el menor.
    bus.publish_nonce_response({"voting_window_id": ch["voting_window_id"],
                                "nonce": n_mayor, "winning_node_or_pool": "worker-2"})
    bus.publish_nonce_response({"voting_window_id": ch["voting_window_id"],
                                "nonce": n_menor, "winning_node_or_pool": "worker-1"})

    assert store.chain_length() == 1
    block = store.get_chain()[0]
    assert block.nonce == n_mayor                       # el primero recibido
    assert block.winning_node_or_pool == "worker-2"
    win = store.get_window(ch["voting_window_id"])
    assert int(win["winning_nonce"]) == n_mayor
    assert win["winning_node_or_pool"] == "worker-2"


def test_cierre_atomico_es_autoritativo_en_redis_ante_failover(bus, store):
    """El guard de cierre vive en Redis, no sólo en el estado en memoria.

    Se simula un solapamiento de failover: dos NCT con la MISMA ventana activa
    en memoria. El primero en reclamar el cierre (SETNX) sella; el segundo, aun
    teniendo su ``_active`` apuntando a la ventana, ve el guard ya puesto y
    descarta su nonce válido sin sellar un segundo bloque."""
    clock = Clock()
    challenges = []
    bus.on_challenge(challenges.append)
    nct_a = _nct(bus, store, nct_id="nct-A", is_leader=True, clock=clock)

    bus.publish_proposal({"law_id": "L1", "author_pubkey": "A",
                          "text_hash": "h1", "created_at": "t0"})
    ch = challenges[0]
    n_a = _solve_from(ch["partial_hash_base"], ch["n_zeros_required"], 0)
    n_b = _solve_from(ch["partial_hash_base"], ch["n_zeros_required"], n_a + 1)

    # Un segundo NCT cree tener la MISMA ventana activa (estado en memoria).
    nct_b = NCTCoordinator(bus, store, n_zeros=2, window_seconds_promulgacion=60,
                           window_seconds_derogacion=90, cooldown_new=0,
                           cooldown_reproposed=0, clock=clock, nct_id="nct-B",
                           is_leader=True)
    nct_b._active = dict(nct_a._active)

    # nct_b sella primero (gana el guard atómico en Redis).
    nct_b.handle_nonce_response({"voting_window_id": ch["voting_window_id"],
                                 "nonce": n_b, "winning_node_or_pool": "pool-B"})
    # nct_a procesa después: su _active sigue en pie pero el guard ya está puesto.
    nct_a.handle_nonce_response({"voting_window_id": ch["voting_window_id"],
                                 "nonce": n_a, "winning_node_or_pool": "pool-A"})

    assert store.chain_length() == 1
    block = store.get_chain()[0]
    assert block.nonce == n_b
    assert block.winning_node_or_pool == "pool-B"
