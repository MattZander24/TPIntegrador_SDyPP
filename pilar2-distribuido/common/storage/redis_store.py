"""Cliente de estado de VoxChain sobre Redis (AGENT.md 7).

Esquema de claves (namespaced):

- ``law:<id>``            hash con la ley (7.1)
- ``window:<id>``         hash con la ventana de votación (7.2)
- ``block:<hash>``        hash con el bloque (7.3)
- ``cooldown:<pubkey>``   hash con el cooldown del autor (7.4)
- ``chain``               lista ordenada de ``block_hash`` (la cadena)
- ``active_window``       clave única con el ``voting_window_id`` vigente
- ``window_sealed:<id>``  guard atómico de cierre (primer nonce válido gana, BUG 2)
- ``window_counter``      contador monótono de ventanas abiertas (base del cooldown)
- ``law_queue``           lista de ``law_id`` en estado ``pending_queue``
- ``discarded_text_hashes`` set de ``text_hash`` descartados (detección de reproposición)

Se asume un cliente Redis con ``decode_responses=True`` (valores como ``str``).
Las claves privadas de los individuos **nunca** se persisten (AGENT.md 10):
sólo circula ``author_pubkey``.
"""

from __future__ import annotations

import json
from typing import Optional

from common.blockchain.block import Block, GENESIS_PREVIOUS_HASH


class LawStatus:
    PENDING_QUEUE = "pending_queue"
    IN_WINDOW = "in_window"
    PROMULGATED = "promulgated"
    DISCARDED = "discarded"
    REPEALED = "repealed"


class WindowResult:
    SUCCESS = "success"
    EXPIRED_PENDING = "expired_pending"


class CooldownReason:
    PROPOSED_NEW = "proposed_new"
    REPROPOSED_IDENTICAL = "reproposed_identical"


def connect_redis(url: str, **kwargs):
    """Crea un cliente redis-py a partir de una URL (``redis://host:port/db``)."""
    import redis  # import diferido: el paquete common no debe exigir redis en tests puros

    return redis.Redis.from_url(url, decode_responses=True, **kwargs)


def _clean(mapping: dict) -> dict:
    """Redis no admite valores None en un hash; se omiten esos campos."""
    return {k: v for k, v in mapping.items() if v is not None}


class VoxChainStore:
    """Fachada de persistencia. Recibe un cliente Redis (real o fakeredis)."""

    def __init__(self, client):
        self.r = client

    # ---- conexión / salud -------------------------------------------------
    def ping(self) -> bool:
        try:
            return bool(self.r.ping())
        except Exception:
            return False

    # ---- leyes (7.1) ------------------------------------------------------
    def save_law(self, *, law_id: str, author_pubkey: str, text_hash: str,
                 created_at: str, status: str = LawStatus.PENDING_QUEUE,
                 action: str = "promulgacion",
                 text_ref: Optional[str] = None,
                 text_compressed: Optional[str] = None,
                 text_original_len: int = 0) -> None:
        # `action` es la acción que la próxima ventana de esta ley ejecutará.
        # Una derogación reutiliza la ley promulgada existente cambiando su action.
        self.r.hset(f"law:{law_id}", mapping=_clean({
            "law_id": law_id,
            "author_pubkey": author_pubkey,
            "text_hash": text_hash,
            "text_ref": text_ref,
            "text_compressed": text_compressed,
            "text_original_len": str(text_original_len) if text_original_len else None,
            "status": status,
            "action": action,
            "created_at": created_at,
        }))

    def get_law(self, law_id: str) -> Optional[dict]:
        data = self.r.hgetall(f"law:{law_id}")
        return data or None

    def set_law_status(self, law_id: str, status: str) -> None:
        self.r.hset(f"law:{law_id}", "status", status)

    def set_law_action(self, law_id: str, action: str) -> None:
        self.r.hset(f"law:{law_id}", "action", action)

    # ---- cola de leyes (round-robin lo decide el NCT) ---------------------
    def enqueue_law(self, law_id: str) -> None:
        self.r.rpush("law_queue", law_id)

    def remove_from_queue(self, law_id: str) -> None:
        self.r.lrem("law_queue", 0, law_id)

    def queued_law_ids(self) -> list[str]:
        return self.r.lrange("law_queue", 0, -1)

    def queued_laws(self) -> list[dict]:
        return [law for lid in self.queued_law_ids() if (law := self.get_law(lid))]

    # ---- detección de reproposición (3.5) ---------------------------------
    def mark_text_hash_discarded(self, text_hash: str) -> None:
        self.r.sadd("discarded_text_hashes", text_hash)

    def is_text_hash_discarded(self, text_hash: str) -> bool:
        return bool(self.r.sismember("discarded_text_hashes", text_hash))

    # ---- contador de ventanas (base del cooldown) -------------------------
    def current_window_number(self) -> int:
        val = self.r.get("window_counter")
        return int(val) if val is not None else 0

    def next_window_number(self) -> int:
        """Incrementa y devuelve el número de la ventana que se está abriendo."""
        return int(self.r.incr("window_counter"))

    # ---- ventanas (7.2) ---------------------------------------------------
    def save_window(self, *, voting_window_id: str, law_id: str, action: str,
                    n_zeros_required: int, opened_at: str, deadline: str,
                    partial_hash_base: str, result: Optional[str] = None,
                    winning_nonce: Optional[int] = None,
                    winning_node_or_pool: Optional[str] = None) -> None:
        self.r.hset(f"window:{voting_window_id}", mapping=_clean({
            "voting_window_id": voting_window_id,
            "law_id": law_id,
            "action": action,
            "n_zeros_required": n_zeros_required,
            "opened_at": opened_at,
            "deadline": deadline,
            "partial_hash_base": partial_hash_base,
            "result": result,
            "winning_nonce": winning_nonce,
            "winning_node_or_pool": winning_node_or_pool,
        }))

    def get_window(self, voting_window_id: str) -> Optional[dict]:
        data = self.r.hgetall(f"window:{voting_window_id}")
        return data or None

    def set_window_result(self, voting_window_id: str, *, result: str,
                          winning_nonce: Optional[int] = None,
                          winning_node_or_pool: Optional[str] = None) -> None:
        self.r.hset(f"window:{voting_window_id}", mapping=_clean({
            "result": result,
            "winning_nonce": winning_nonce,
            "winning_node_or_pool": winning_node_or_pool,
        }))

    # ---- cierre atómico de ventana (BUG 2 / AGENT.md 5 / P2) --------------
    def try_seal_window(self, voting_window_id: str, winning_node_or_pool: str,
                        *, ttl: int = 3600) -> bool:
        """Reclama el cierre de una ventana de forma atómica (SETNX).

        El **primer** nonce válido recibido para ``voting_window_id`` gana el
        cierre; las soluciones tardías ven la clave ``window_sealed:<id>`` ya
        puesta y obtienen ``False`` (se descartan, AGENT.md 5). El guard vive en
        Redis para ser autoritativo ante un failover (un NCT distinto retomando),
        no sólo en el estado en memoria del proceso. La clave expira tras ``ttl``
        para no acumular entradas indefinidamente.
        """
        acquired = self.r.set(f"window_sealed:{voting_window_id}",
                              winning_node_or_pool, nx=True, ex=ttl)
        return bool(acquired)

    def get_window_sealer(self, voting_window_id: str) -> Optional[str]:
        return self.r.get(f"window_sealed:{voting_window_id}")

    # ---- ventana activa (estado único) ------------------------------------
    def set_active_window(self, voting_window_id: str) -> None:
        self.r.set("active_window", voting_window_id)

    def get_active_window(self) -> Optional[str]:
        return self.r.get("active_window")

    def clear_active_window(self) -> None:
        self.r.delete("active_window")

    # ---- cooldowns (7.4) --------------------------------------------------
    def set_cooldown(self, author_pubkey: str, cooldown_until_window: int,
                     reason: str) -> None:
        self.r.hset(f"cooldown:{author_pubkey}", mapping={
            "author_pubkey": author_pubkey,
            "cooldown_until_window": cooldown_until_window,
            "cooldown_reason": reason,
        })

    def get_cooldown(self, author_pubkey: str) -> Optional[dict]:
        data = self.r.hgetall(f"cooldown:{author_pubkey}")
        return data or None

    def is_in_cooldown(self, author_pubkey: str) -> bool:
        """True si el autor todavía no alcanzó su ``cooldown_until_window``."""
        cd = self.get_cooldown(author_pubkey)
        if not cd:
            return False
        return self.current_window_number() < int(cd["cooldown_until_window"])

    # ---- bloques y cadena (7.3) -------------------------------------------
    def append_block(self, block: Block) -> None:
        self.r.hset(f"block:{block.block_hash}", mapping={
            k: ("" if v is None else v) for k, v in block.to_dict().items()
        })
        self.r.rpush("chain", block.block_hash)

    def get_block(self, block_hash: str) -> Optional[Block]:
        data = self.r.hgetall(f"block:{block_hash}")
        return Block.from_dict(data) if data else None

    def chain_hashes(self) -> list[str]:
        return self.r.lrange("chain", 0, -1)

    def get_chain(self) -> list[Block]:
        return [b for h in self.chain_hashes() if (b := self.get_block(h))]

    def last_block_hash(self) -> str:
        hashes = self.chain_hashes()
        return hashes[-1] if hashes else GENESIS_PREVIOUS_HASH

    def chain_length(self) -> int:
        return self.r.llen("chain")

    # ---- liderazgo del NCT (Bully distribuido, AGENT.md 4) ----------------
    #
    # Dos modos de adquisición del lease:
    #
    # 1. try_acquire_leadership (NX): para el arranque inicial. Solo adquiere si
    #    la clave no existe, evitando que dos nodos que arrancan a la vez compitan.
    #
    # 2. elect_acquire_leadership (SET sin NX): para el ganador de la elección PoW.
    #    El líder anterior está muerto; su clave puede seguir viva dentro del TTL.
    #    El PoW ya arbitró al ganador, así que sobreescribimos sin NX.
    #    La atomicidad entre candidatos múltiples la garantiza el backoff del PoW
    #    (el segundo candidato ve el claim del primero en nct_election y se retira
    #    antes de llegar acá).
    #
    # TTL coherente con el timeout de heartbeat: el leader renueva cada
    # heartbeat_interval (≈3 s); el TTL debe ser mayor que el intervalo pero
    # aproximado al timeout de detección (≈12 s) para que el lease expire si el
    # líder deja de renovar, sin interferir con la adquisición via PoW.
    # Valor por defecto: 20 s (≈ 1.6× el timeout de 12 s, >> el intervalo de 3 s).

    def try_acquire_leadership(self, candidate_id: str, ttl: int = 20) -> bool:
        """Intenta adquirir el liderazgo del NCT vía SETNX (arranque inicial).

        Devuelve True si este candidato ganó la adquisición. El lock expira
        después de ``ttl`` segundos; el líder debe renovarlo con heartbeats.
        """
        acquired = self.r.set("nct:leader", candidate_id, nx=True, ex=ttl)
        return bool(acquired)

    def elect_acquire_leadership(self, candidate_id: str, ttl: int = 20,
                                 dead_threshold: int = 6) -> bool:
        """Adquiere el lease tras ganar la elección PoW.

        Aplica tres reglas en orden:
        1. Clave inexistente (lease expiró naturalmente) → adquirir.
        2. Clave == nosotros → renovar TTL (restart tras crash).
        3. Clave == otro candidato:
           - TTL ≤ dead_threshold → el holder está muerto (dejó de renovar) → adquirir.
           - TTL > dead_threshold → otro candidato ganó la elección concurrente → fallar.

        El ``dead_threshold`` debe ser > (LEADER_LEASE_TTL - HEARTBEAT_TIMEOUT) para
        cubrir el TTL restante del líder caído cuando la elección dispara, y <<
        LEADER_LEASE_TTL para no confundirlo con un ganador concurrente recién
        adquirido. Valor seguro: 2 × HEARTBEAT_INTERVAL ≈ 6 s.

        Nota: la implementación es GET + SET, no atómica. La atomicidad real la
        proveen el backoff del PoW (solo un candidato llega acá en condiciones
        normales) y el corto margen temporal entre ambas operaciones.
        """
        current = self.r.get("nct:leader")
        if current is None:
            self.r.set("nct:leader", candidate_id, ex=ttl)
            return True
        if current == candidate_id:
            self.r.expire("nct:leader", ttl)
            return True
        remaining = self.r.ttl("nct:leader")
        if remaining >= 0 and remaining <= dead_threshold:
            self.r.set("nct:leader", candidate_id, ex=ttl)
            return True
        return False

    def renew_leadership(self, candidate_id: str, ttl: int = 20) -> bool:
        """Renueva el liderazgo: sólo el líder actual puede extender su TTL."""
        # Usamos una transacción Lua para verificar que seguimos siendo el líder.
        lua = """
        local current = redis.call("GET", "nct:leader")
        if current == ARGV[1] then
            redis.call("EXPIRE", "nct:leader", ARGV[2])
            return 1
        end
        return 0
        """
        ok = self.r.eval(lua, 0, candidate_id, ttl)
        return bool(ok)

    def get_leader(self) -> str | None:
        return self.r.get("nct:leader")

    def clear_leadership(self) -> None:
        self.r.delete("nct:leader")
