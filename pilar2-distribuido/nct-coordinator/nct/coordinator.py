"""Núcleo del NCT: cola de leyes, apertura/cierre de ventanas, verificación y sellado.

El NCT gestiona **exclusivamente** ventanas de votación (AGENT.md 3.3, P4): una
sola ventana activa a la vez, orden round-robin por autor, dificultad fija n/n+1,
verificación de nonce contra el desafío y sellado del bloque en Redis. No arbitra
contenido ni ajusta dificultad por carga de red.

Es agnóstico del transporte y del backend: recibe un ``Messaging`` y un
``VoxChainStore``, de modo que el mismo código corre con RabbitMQ+Redis reales o
con el bus en memoria + fakeredis en los tests.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone

from common.blockchain import (
    ACTION_DEROGACION,
    ACTION_PROMULGACION,
    build_partial_hash_base,
    n_zeros_for_action,
    seal_block,
    verify_nonce,
)
from common.blockchain.challenge import VALID_ACTIONS
from common.messaging import QUEUE_PROPUESTAS, QUEUE_RESPUESTA_NONCE
from common.storage import LawStatus, WindowResult
from common.metrics import (
    nct_blocks_sealed_total,
    nct_is_leader,
    nct_proposals_total,
    nct_windows_opened_total,
)
from .queue_logic import classify_proposal, cooldown_until, select_next_law

log = logging.getLogger("voxchain.nct")


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


class NCTCoordinator:
    def __init__(self, messaging, store, *, n_zeros: int,
                 window_seconds_promulgacion: int, window_seconds_derogacion: int,
                 cooldown_new: int, cooldown_reproposed: int, clock=time.time,
                 nct_id: str = "nct", is_leader: bool = True,
                 heartbeat_interval: float = 0.0, on_stepdown=None):
        self.m = messaging
        self.store = store
        self.n_zeros = n_zeros
        self.window_seconds = {
            ACTION_PROMULGACION: window_seconds_promulgacion,
            ACTION_DEROGACION: window_seconds_derogacion,
        }
        self.cooldown_new = cooldown_new
        self.cooldown_reproposed = cooldown_reproposed
        self.now = clock
        self.nct_id = nct_id
        self.is_leader = is_leader
        self.heartbeat_interval = heartbeat_interval
        # Callback invocado al ceder el liderazgo: lo usa el monitor para
        # activarse y empezar a observar heartbeats del nuevo líder.
        self._on_stepdown = on_stepdown

        # Estado en memoria de la ventana activa (no se persiste para recuperación:
        # ante caída del NCT la ventana se pierde, AGENT.md 4).
        self._last_author = store.get_last_author()
        self._active = None  # dict con datos de la ventana en curso, o None
        self._last_heartbeat_pub = 0.0

    # -- registro de handlers ----------------------------------------------
    def wire(self) -> None:
        """Suscribe los handlers según el rol.

        Las colas de trabajo (``propuestas``, ``respuesta_nonce``) se consumen
        **sólo siendo líder** (BUG 1 / AGENT.md 4): un follower que también las
        consumiera competiría con el líder por el reparto round-robin de RabbitMQ
        y se "tragaría" la mitad de los mensajes sin actuar. Mientras es follower
        sólo escucha ``nct.heartbeat`` y ``nct_election`` (vía el monitor)."""
        if self.is_leader:
            self._subscribe_work_queues()

    def _subscribe_work_queues(self) -> None:
        self.m.on_proposal(self.handle_proposal)
        self.m.on_nonce_response(self.handle_nonce_response)

    def _unsubscribe_work_queues(self) -> None:
        self.m.unsubscribe(QUEUE_PROPUESTAS)
        self.m.unsubscribe(QUEUE_RESPUESTA_NONCE)

    def consumed_work_queues(self) -> set[str]:
        """Colas de trabajo que este NCT consume hoy (gateadas por liderazgo)."""
        return self.m.consumed_queues() & {QUEUE_PROPUESTAS, QUEUE_RESPUESTA_NONCE}

    # -- flujo 1: propuestas (nodo → NCT) ----------------------------------
    def handle_proposal(self, law: dict) -> None:
        if not self.is_leader:
            log.debug("propuesta ignorada (no somos el líder)")
            return
        author = law.get("author_pubkey")
        text_hash = law.get("text_hash")
        action = law.get("action", ACTION_PROMULGACION)
        law_id = law.get("law_id") or str(uuid.uuid4())
        created_at = law.get("created_at") or _iso(self.now())

        nct_proposals_total.inc()

        if not author or not text_hash:
            log.warning("propuesta inválida (faltan author/text_hash): %s", law)
            return
        if action not in VALID_ACTIONS:
            log.warning("propuesta con action inválida: %s", action)
            return

        # Cooldown del autor (3.4): no puede proponer mientras esté en cooldown.
        if self.store.is_in_cooldown(author):
            cd = self.store.get_cooldown(author)
            log.info("propuesta rechazada: autor %s en cooldown hasta ventana %s",
                     author[:12], cd["cooldown_until_window"])
            return

        text_compressed = law.get("text_compressed", "")
        text_original_len = int(law.get("text_original_len", 0))

        if action == ACTION_DEROGACION:
            self._enqueue_derogacion(law_id, author, action)
        else:
            self._enqueue_promulgacion(law_id, author, text_hash, created_at,
                                       text_compressed, text_original_len)

        self.maybe_open_window()

    def _enqueue_promulgacion(self, law_id, author, text_hash, created_at,
                              text_compressed="", text_original_len=0) -> None:
        # Reproposición idéntica (3.5): mismo hash de texto que algo descartado.
        reason = classify_proposal(self.store.is_text_hash_discarded(text_hash))
        self.store.save_law(law_id=law_id, author_pubkey=author,
                            text_hash=text_hash, created_at=created_at,
                            status=LawStatus.PENDING_QUEUE,
                            action=ACTION_PROMULGACION,
                            text_compressed=text_compressed,
                            text_original_len=text_original_len)
        self.store.enqueue_law(law_id)
        until = cooldown_until(self.store.current_window_number(), reason,
                               cooldown_new=self.cooldown_new,
                               cooldown_reproposed=self.cooldown_reproposed)
        self.store.set_cooldown(author, until, reason)
        log.info("ley %s encolada (promulgacion, %s, cooldown→ventana %d)",
                 law_id, reason, until)

    def _enqueue_derogacion(self, law_id, author, action) -> None:
        target = self.store.get_law(law_id)
        if not target or target.get("status") != LawStatus.PROMULGATED:
            log.warning("derogacion rechazada: ley %s no existe o no está promulgada",
                        law_id)
            return
        # La derogación reutiliza la ley promulgada cambiando su action; se reencola.
        self.store.set_law_action(law_id, ACTION_DEROGACION)
        self.store.enqueue_law(law_id)
        until = cooldown_until(self.store.current_window_number(),
                               classify_proposal(False),
                               cooldown_new=self.cooldown_new,
                               cooldown_reproposed=self.cooldown_reproposed)
        self.store.set_cooldown(author, until, classify_proposal(False))
        log.info("ley %s encolada para derogacion (cooldown→ventana %d)", law_id, until)

    # -- apertura de ventana (round-robin, dificultad fija) ----------------
    def maybe_open_window(self) -> None:
        if not self.is_leader:
            return  # sólo el líder abre ventanas (el follower no toca la cola)
        if self._active is not None:
            return
        law = select_next_law(self.store.queued_laws(), self._last_author)
        if law is None:
            return
        self.open_window(law)

    def open_window(self, law: dict) -> None:
        action = law.get("action", ACTION_PROMULGACION)
        law_id = law["law_id"]
        window_num = self.store.next_window_number()
        voting_window_id = f"W{window_num}-{law_id}"
        n_zeros_required = n_zeros_for_action(self.n_zeros, action)
        opened = self.now()
        deadline = opened + self.window_seconds[action]
        base = build_partial_hash_base(law_id, law["text_hash"],
                                       voting_window_id, action)

        self.store.save_window(voting_window_id=voting_window_id, law_id=law_id,
                               action=action, n_zeros_required=n_zeros_required,
                               opened_at=_iso(opened), deadline=_iso(deadline),
                               partial_hash_base=base)
        self.store.set_law_status(law_id, LawStatus.IN_WINDOW)
        self.store.remove_from_queue(law_id)
        self.store.set_active_window(voting_window_id)

        self._active = {
            "voting_window_id": voting_window_id, "law_id": law_id,
            "action": action, "n_zeros_required": n_zeros_required,
            "partial_hash_base": base, "deadline_epoch": deadline,
            "author_pubkey": law.get("author_pubkey"),
        }
        self._last_author = law.get("author_pubkey")
        self.store.set_last_author(self._last_author)

        nct_windows_opened_total.inc()

        self.m.publish_challenge({
            "voting_window_id": voting_window_id, "law_id": law_id,
            "n_zeros_required": n_zeros_required, "deadline": _iso(deadline),
            "partial_hash_base": base, "action": action,
        })
        log.info("ventana %s abierta (%s, %d ceros, deadline %s)",
                 voting_window_id, action, n_zeros_required, _iso(deadline))

    # -- flujo 3: respuesta_nonce (red → NCT) ------------------------------
    def handle_nonce_response(self, sol: dict) -> None:
        if not self.is_leader:
            log.debug("nonce ignorado (no somos el líder)")
            return
        if self._active is None:
            log.info("nonce descartado: no hay ventana activa (%s)", sol)
            return
        active = self._active
        wid = sol.get("voting_window_id")
        if wid != active["voting_window_id"]:
            log.info("nonce descartado (tardío/otra ventana): %s ≠ %s",
                     wid, active["voting_window_id"])
            return
        if self.now() > active["deadline_epoch"]:
            log.info("nonce descartado: llegó después del deadline de %s", wid)
            return

        winner = sol.get("winning_node_or_pool", "")
        nonce = sol.get("nonce")
        # Regla 3.4: el autor pierde el voto en la ventana de su propia ley.
        if winner and winner == active["author_pubkey"]:
            log.info("nonce descartado: el autor no puede ganar su propia ventana")
            return

        ok, block_hash_input = verify_nonce(active["partial_hash_base"],
                                            int(nonce), active["n_zeros_required"])
        if not ok:
            log.warning("nonce inválido descartado (no cumple %d ceros): %s",
                        active["n_zeros_required"], nonce)
            return

        # Cierre atómico (BUG 2 / AGENT.md 5): el PRIMER nonce válido recibido
        # cierra la ventana. El guard vive en Redis (SETNX) para ser autoritativo
        # ante failover; toda solución válida posterior para la misma ventana ve
        # la clave ya puesta y se descarta como tardía (no sobrescribe nada).
        wid = active["voting_window_id"]
        if not self.store.try_seal_window(wid, winner or "desconocido"):
            log.info("nonce tardío descartado: ventana %s ya sellada por %s",
                     wid, self.store.get_window_sealer(wid))
            return

        self._seal(active, int(nonce), winner)

    def _seal(self, active: dict, nonce: int, winner: str) -> None:
        action = active["action"]
        law_id = active["law_id"]
        law = self.store.get_law(law_id) or {}
        text_compressed = str(law.get("text_compressed", ""))
        text_original_len = int(law.get("text_original_len", 0))
        block = seal_block(
            previous_hash=self.store.last_block_hash(),
            law_id=law_id, action=action,
            n_zeros_required=active["n_zeros_required"], nonce=nonce,
            winning_node_or_pool=winner or "desconocido",
            voting_window_id=active["voting_window_id"], timestamp=_iso(self.now()),
            text_compressed=text_compressed,
            text_original_len=text_original_len,
        )
        self.store.append_block(block)
        self.store.set_window_result(active["voting_window_id"],
                                     result=WindowResult.SUCCESS, winning_nonce=nonce,
                                     winning_node_or_pool=winner)
        new_status = (LawStatus.REPEALED if action == ACTION_DEROGACION
                      else LawStatus.PROMULGATED)
        self.store.set_law_status(law_id, new_status)
        self.store.clear_active_window()
        self._active = None
        nct_blocks_sealed_total.inc()
        log.info("bloque sellado %s (ley %s → %s, nonce %d, por %s)",
                 block.block_hash[:12], law_id, new_status, nonce, winner)
        self.maybe_open_window()

    # -- cierre por deadline (ley pendiente → discarded) -------------------
    def check_deadline(self) -> None:
        if self._active is None:
            return
        if self.now() <= self._active["deadline_epoch"]:
            return
        active = self._active
        law = self.store.get_law(active["law_id"])
        # Ley pendiente (3.2/3.4): se descarta, NO se reencola automáticamente.
        self.store.set_window_result(active["voting_window_id"],
                                     result=WindowResult.EXPIRED_PENDING)
        self.store.set_law_status(active["law_id"], LawStatus.DISCARDED)
        if law:
            self.store.mark_text_hash_discarded(law.get("text_hash", ""))
        self.store.clear_active_window()
        self._active = None
        log.info("ventana %s vencida sin solución: ley %s descartada",
                 active["voting_window_id"], active["law_id"])
        self.maybe_open_window()

    def become_leader(self) -> None:
        """Transiciona este NCT de follower a líder tras ganar la elección.

        Recién acá abre los consumidores de las colas de trabajo (BUG 1): siendo
        follower no estaba suscrito a ``propuestas`` ni ``respuesta_nonce``."""
        if self.is_leader:
            return
        nct_is_leader.set(1)
        log.info("asumiendo como líder NCT (%s): abriendo colas de trabajo", self.nct_id)
        self.is_leader = True
        self._subscribe_work_queues()
        self._last_author = self.store.get_last_author()
        self.store.clear_active_window()
        self._active = None
        # La ventana en curso al momento de la caída se pierde (AGENT.md 4);
        # si hay leyes pendientes en Redis, abrimos una ventana nueva.
        self.maybe_open_window()

    def step_down(self) -> None:
        """Líder → follower: cierra las colas de trabajo y suelta la ventana.

        Se invoca al detectar pérdida de liderazgo en Redis (split-brain,
        AGENT.md 11.4): no basta con ignorar mensajes en memoria, hay que dejar
        de consumir ``propuestas``/``respuesta_nonce`` para no robarlos del
        reparto round-robin. La ventana en curso se pierde por diseño (AGENT.md 4).
        Tras ceder el liderazgo, notifica al monitor (``_on_stepdown``) para que
        empiece a observar heartbeats del nuevo líder."""
        if not self.is_leader:
            return
        nct_is_leader.set(0)
        log.warning("step_down (%s): liderazgo perdido, cerrando colas de trabajo",
                    self.nct_id)
        self.is_leader = False
        self._unsubscribe_work_queues()
        self._active = None
        if self._on_stepdown is not None:
            self._on_stepdown()

    # -- tick periódico para el loop de consumo ----------------------------
    def tick(self) -> None:
        self.check_deadline()
        self.maybe_open_window()
        self._maybe_publish_heartbeat()

    def _maybe_publish_heartbeat(self) -> None:
        if not self.is_leader or self.heartbeat_interval <= 0:
            return
        now = self.now()
        if now - self._last_heartbeat_pub < self.heartbeat_interval:
            return
        self._last_heartbeat_pub = now
        # Renovar liderazgo en Redis. Si otro NCT ya lo adquirió (split-brain,
        # AGENT.md 11.4), renovar falla y nos retiramos cerrando las colas.
        if not self.store.renew_leadership(self.nct_id):
            self.step_down()
            return
        self.m.publish_heartbeat({
            "nct_id": self.nct_id,
            "ts": now,
            "active_window_id": (self._active["voting_window_id"]
                                 if self._active else None),
            "last_block_hash": self.store.last_block_hash(),
        })
