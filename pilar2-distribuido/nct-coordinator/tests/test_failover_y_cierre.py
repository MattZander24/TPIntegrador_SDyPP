"""Tests de los bugs del NCT detectados con el stack real.

- BUG 1: la suscripción a las colas de trabajo (``propuestas``,
  ``respuesta_nonce``) está gateada por liderazgo. Un follower no compite por
  ellas, así que el standby no se "traga" propuestas por el reparto round-robin.
- BUG 2: el primer nonce válido recibido cierra la ventana de forma atómica
  (guard en Redis); las soluciones válidas tardías para la misma ventana se
  descartan y no sobrescriben el bloque sellado.
- BUG 3 (failover asimétrico): el monitor de heartbeats vivía solo en el rol
  standby, no en el primario. Si el standby era líder y moría, el primario no
  detectaba la caída y el clúster quedaba acéfalo. Ahora todo follower monitorea,
  sin importar si su etiqueta es "primary" o "standby".
"""

import hashlib
import time

import pytest

from common.messaging import (
    EXCHANGE_HEARTBEAT,
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


def _follower_node(bus, store, nct_id="nct-standby"):
    """Un nodo NCT en estado follower: coordinator + monitor de heartbeats."""
    nct = _nct(bus, store, nct_id=nct_id, is_leader=False)
    monitor = NCTHeartbeatMonitor(
        bus, store, candidate_id=nct_id,
        heartbeat_timeout=12, on_elected=nct.become_leader)
    monitor.wire()
    return nct, monitor


def _full_node(bus, store, *, nct_id, is_leader, clock=None):
    """Un nodo NCT completo: coordinator + monitor, cableados entre sí."""
    kw = {"clock": clock} if clock else {}
    nct = _nct(bus, store, nct_id=nct_id, is_leader=is_leader, **kw)
    monitor = NCTHeartbeatMonitor(
        bus, store, candidate_id=nct_id,
        heartbeat_timeout=12, on_elected=nct.become_leader,
        initial_is_leader=is_leader,
        **({"clock": clock} if clock else {}),
    )
    monitor.wire()
    nct._on_stepdown = monitor.notify_stepdown
    return nct, monitor


def _solve_from(base, n_zeros, start=0):
    prefix = "0" * n_zeros
    nonce = start
    while not hashlib.md5(f"{base}{nonce}".encode()).hexdigest().startswith(prefix):
        nonce += 1
    return nonce


# ---- BUG 1: gating de suscripción por liderazgo ---------------------------

def test_follower_no_consume_colas_de_trabajo(bus, store):
    """Un follower escucha heartbeat pero NO las colas de trabajo."""
    nct, _ = _follower_node(bus, store)
    consumidas = bus.consumed_queues()
    assert QUEUE_PROPUESTAS not in consumidas
    assert QUEUE_RESPUESTA_NONCE not in consumidas
    assert EXCHANGE_HEARTBEAT in consumidas
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


# ---- BUG 3: failover asimétrico (monitor solo en standby) -----------------

@pytest.mark.parametrize("follower_id,leader_id", [
    ("nct-standby-1", "nct-primary"),   # dirección A: standby es follower (ya funcionaba)
    ("nct-primary", "nct-standby-1"),   # dirección B: primario es follower (el bug)
])
def test_todo_follower_monitorea_independientemente_del_id(bus, store,
                                                            follower_id, leader_id):
    """Cualquier NCT en estado follower consume nct.heartbeat y nct_election.

    El conjunto de colas del follower es idéntico independientemente de si su
    id es 'nct-primary' o 'nct-standby-1': la identidad es cosmética."""
    # Follower cableado con monitor (como hace main.py con el fix)
    nct, monitor = _full_node(bus, store, nct_id=follower_id, is_leader=False)

    consumed = bus.consumed_queues()
    assert EXCHANGE_HEARTBEAT in consumed,  f"{follower_id}: debe consumir nct.heartbeat"
    assert QUEUE_PROPUESTAS not in consumed
    assert QUEUE_RESPUESTA_NONCE not in consumed
    assert nct.consumed_work_queues() == set()


@pytest.mark.parametrize("first_leader,survivor", [
    ("nct-primary",   "nct-standby-1"),  # dirección A: primary muere
    ("nct-standby-1", "nct-primary"),    # dirección B: standby muere (el bug)
])
def test_failover_bidireccional_matando_al_poseedor_del_lease(
        bus, store, first_leader, survivor):
    """Matar al nodo que tiene el lease, sea cual sea su identidad, deja un líder vivo.

    Parametrizado para cubrir ambas direcciones. La dirección B (standby era
    líder y muere) es la que destapó el bug: sin monitor en el primario, el
    clúster quedaba acéfalo.

    El TTL inicial del lease (5 s) simula el estado real al momento de la
    elección: con LEADER_LEASE_TTL=15 s y HEARTBEAT_TIMEOUT=12 s, el líder
    muerto renueva por última vez 0-3 s antes de morir, dejando 12-15 s de TTL.
    El follower detecta la caída a los 12 s; el TTL restante ≈ 3 s < dead_threshold.
    Usamos 5 s aquí para que en el bus síncrono (el test corre en microsegundos)
    el TTL restante siga siendo < dead_threshold (6 s) y el ganador pueda adquirir.
    """
    clock = Clock()
    TIMEOUT = 12.0
    # TTL inicial que simula el estado al momento de la elección: restante ≈ 3-5 s
    # (LEADER_LEASE_TTL - HEARTBEAT_TIMEOUT con algo de margen).
    INITIAL_TTL = 5
    DEAD_THRESHOLD = 6  # 2 × HEARTBEAT_INTERVAL, mismo default del monitor

    # Dar el lease al primer líder con el TTL realista (resto que quedaría al
    # momento en que el follower detecta la caída).
    store.try_acquire_leadership(first_leader, ttl=INITIAL_TTL)

    # Crear ambos nodos: líder con initial_is_leader=True, follower con False.
    nct_leader, mon_leader = _full_node(bus, store, nct_id=first_leader,
                                        is_leader=True, clock=clock)
    nct_follower, mon_follower = _full_node(bus, store, nct_id=survivor,
                                            is_leader=False, clock=clock)
    # El dead_threshold del follower debe ser mayor que el INITIAL_TTL restante.
    mon_follower.dead_threshold = DEAD_THRESHOLD

    # El líder publica un heartbeat (el follower registra la hora).
    bus.publish_heartbeat({"nct_id": first_leader, "ts": clock.t,
                           "active_window_id": None, "last_block_hash": ""})
    assert mon_follower._last_heartbeat == clock.t

    # Simular caída del líder: avanzar el reloj más allá del timeout sin nuevos HB.
    clock.t += TIMEOUT + 3  # 15 s: supera el heartbeat_timeout de 12 s

    # tick del follower: detecta timeout, corre elección, promueve.
    mon_leader.tick()    # no hace nada (_is_leader=True en su monitor)
    mon_follower.tick()  # detecta caída, gana elección, llama become_leader

    # El sobreviviente debe haber tomado el lease y abierto las colas de trabajo.
    assert store.get_leader() == survivor, (
        f"El lease debe apuntar a {survivor}, no a {store.get_leader()!r}")
    assert nct_follower.is_leader is True
    assert nct_follower.consumed_work_queues() == {QUEUE_PROPUESTAS, QUEUE_RESPUESTA_NONCE}


def test_lease_ttl_expira_sin_renovacion(store):
    """Si el líder deja de renovar, el lease expira y un follower puede adquirirlo.

    El TTL del lease es coherente con el timeout de heartbeat: expirar si no se
    renueva es el mecanismo de seguridad de respaldo cuando no hay monitor activo.
    """
    TTL = 1  # segundo: valor pequeño para no ralentizar la suite
    store.try_acquire_leadership("nct-muerto", ttl=TTL)
    assert store.get_leader() == "nct-muerto"

    # La clave debe tener TTL set (no -1 = sin expiración).
    remaining = store.r.ttl("nct:leader")
    assert remaining > 0, "el lease debe tener TTL configurado"

    # Un segundo follower NO puede adquirir mientras el lease esté vivo.
    assert store.try_acquire_leadership("nct-follower", ttl=5) is False

    # Esperar expiración y verificar que el lease queda libre.
    time.sleep(TTL + 0.3)
    assert store.get_leader() is None, "el lease debe haber expirado"

    # Ahora el follower puede adquirir (clave expirada).
    assert store.try_acquire_leadership("nct-follower", ttl=5) is True
    assert store.get_leader() == "nct-follower"


def test_primary_step_down_activa_su_monitor(bus, store):
    """Cuando el primario pierde el liderazgo, su monitor se activa (notify_stepdown).

    Tras step_down, el primario debe consumir nct.heartbeat y nct_election
    igual que cualquier follower: sus monitores se deben haber activado.
    """
    clock = Clock()
    nct_primary, mon_primary = _full_node(bus, store, nct_id="nct-primary",
                                          is_leader=True, clock=clock)

    # Al arrancar como líder, el monitor está en modo quiescente (_is_leader=True).
    assert mon_primary._is_leader is True

    # El primario cede el liderazgo (p. ej., otro nodo tomó el lease).
    nct_primary.step_down()

    # Ahora el monitor debe estar activo: _is_leader resetado a False.
    assert mon_primary._is_leader is False
    assert nct_primary.is_leader is False

    # El monitor estaba cableado desde el inicio; wire() registró nct.heartbeat.
    consumed = bus.consumed_queues()
    assert EXCHANGE_HEARTBEAT in consumed
