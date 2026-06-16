# Pilar 2 — Infraestructura de servicios distribuidos (VoxChain)

VoxChain no es una blockchain de dinero: es **gobierno por consenso de esfuerzo
computacional**. Cualquiera con un par de claves propone, promulga o deroga
**leyes**; el consenso se mide en hashes (Proof of Work), no en votos nominales.
El NCT sólo coordina ventanas de votación, no arbitra contenido.

> La fuente de verdad del dominio es [`AGENT.md`](../AGENT.md) (raíz del repo).
> Las reglas de gobierno de su sección 3 son normativas.

El desafío que se hashea es el **desafío de gobierno serializado**:

```
partial_hash_base = law_id + text_hash + voting_window_id + action
nonce válido ⇔ md5(partial_hash_base + str(nonce)) empieza con n ceros
            (n para promulgación, n+1 para derogación)
```

---

## Arquitectura

```
   nodo/ciudadano                         ┌──────────────────────────────┐
   (author_pubkey)                        │            Redis             │
        │ scripts/propose_law.py          │  law:* window:* block:*      │
        │ (flujo 1: propuestas)           │  chain  active_window        │
        ▼                                 │  cooldown:* window_counter   │
 ┌───────────────┐   propuestas (cola)    └───────────────▲──────────────┘
 │   RabbitMQ    │◄───────────────────────────────┐       │ persiste estado
 │               │                                 │       │ y sella bloques
 │ exchange      │   desafio_activo (topic)        │       │
 │ + colas       │────────────┐         ┌──────────┴───────────────┐
 └───────┬───────┘            │         │           NCT            │
         │                    │         │  - cola round-robin autor│
         │ respuesta_nonce    │         │  - abre/cierra ventana   │
         │ (cola) red→NCT     │         │  - dificultad fija n/n+1 │
         │                    │         │  - verifica nonce, sella │
         │                    │         │  - Bully-por-esfuerzo*   │
         │                    ▼         └──────────────────────────┘
         │          ┌──────────────────┐
         │          │ Transaction Pool │  suscrito a desafio_activo
         │          │  - fragmenta el  │
         │          │    espacio nonce │
         │          └───────┬──────────┘
         │      tareas_trp   │   ▲ keepalive_trp
         │    (cola, interno)│   │ (cola, interno)
         │                   ▼   │
         │            ┌──────────────────┐   invoca minero Pilar 1
         └───────────►│  Worker  x2      │──► GPU 05_brute_force_range
            nonce     │  - mina rango    │    └ fallback CPU brute_force.py
            ganador   └──────────────────┘

   (*) Bully-por-esfuerzo: piezas de PoW implementadas; coordinación
       distribuida pendiente (test xfail). Ver nct-coordinator/nct/bully.py
```

### Flujos de RabbitMQ

**Tres flujos canónicos hacia/desde el NCT** (AGENT.md 5 / P2; no se agrega un
cuarto que toque al NCT):

| # | Nombre            | Tipo            | Dirección   | Contenido |
|---|-------------------|-----------------|-------------|-----------|
| 1 | `propuestas`      | cola            | nodo → NCT  | `law_id, author_pubkey, text_hash, created_at, action` |
| 2 | `desafio_activo`  | exchange *topic*| NCT → red   | `voting_window_id, law_id, n_zeros_required, deadline, partial_hash_base, action` |
| 3 | `respuesta_nonce` | cola            | red → NCT   | `voting_window_id, nonce, winning_node_or_pool, block_hash_candidato` |

**Dos flujos internos de distribución de trabajo TrP↔worker** (permitidos por
AGENT.md 10 como flujo interno; documentados aquí *antes* de codearse, no tocan al
NCT):

| # | Nombre          | Tipo | Dirección       | Contenido |
|---|-----------------|------|-----------------|-----------|
| 4 | `tareas_trp`    | cola | TrP → workers   | desafío + `range_min, range_max` (rango de nonces) |
| 5 | `keepalive_trp` | cola | workers → TrP   | `worker_id, capacity, has_gpu, ts` |

---

## Componentes

| Servicio                                   | Rol |
|--------------------------------------------|-----|
| [`nct-coordinator/`](nct-coordinator/)     | NCT: cola round-robin, cooldown, apertura/cierre de ventana, verificación de nonce y sellado del bloque |
| [`transaction-pool/`](transaction-pool/)   | TrP: fragmenta el espacio de nonces (bolsa de tareas), trackea capacidad por keep-alives |
| [`worker/`](worker/)                        | Worker: mina el rango asignado invocando el minero de Pilar 1 (GPU/CPU) y publica el nonce |
| `common/`                                   | Paquete compartido: `blockchain`, `storage` (Redis), `messaging` (RabbitMQ), health, logging, config |

---

## Ejecución local

```bash
cd pilar2-distribuido
docker compose up --build          # RabbitMQ + Redis + NCT + TrP + 2 workers

# en otra terminal: proponer una ley (flujo 1)
docker compose run --rm coordinator \
  python /app/pilar2-distribuido/scripts/propose_law.py \
  --text "Presupuesto participativo 2026" --author pk-ciudadano-1
```

El sistema, sin más intervención, abre la ventana, el TrP fragmenta, los workers
resuelven el PoW y el NCT sella el bloque en Redis con encadenamiento válido.

### Health endpoints (JSON, sin GUI)

- NCT: <http://localhost:8081/health> → `{"nct":"ok","redis":"ok","rabbitmq":"ok"}`
- TrP: <http://localhost:8082/health>
- Worker: puerto `8080` en la red interna (2 réplicas, sin puerto de host).
- RabbitMQ management: <http://localhost:15672> (guest/guest, sólo dev local).

### Tests

```bash
cd pilar2-distribuido
python -m venv .venv && . .venv/bin/activate
pip install pytest fakeredis redis pika
pytest                 # unit + integración e2e (fake bus + fakeredis + minero CPU real)
pytest -m integration  # sólo el flujo extremo a extremo
```

---

## Decisiones de diseño

- **Núcleo agnóstico del transporte.** NCT, TrP y Worker reciben un `Messaging` y
  un `VoxChainStore`. En producción se inyecta RabbitMQ + Redis; en tests, un bus
  en memoria + `fakeredis`. El mismo código de dominio corre en ambos.
- **Una sola ventana activa** (AGENT.md 3.3): estado único `active_window` en
  Redis; el NCT no abre una nueva hasta cerrar la anterior.
- **Orden round-robin por autor**, no FIFO (3.3): un autor no encadena turnos
  consecutivos si hay leyes de otros.
- **Dificultad fija n / n+1** (3.6, 10): `n` es configuración; **prohibido** el
  ajuste dinámico por carga de red. Si no hay workers GPU, el TrP **loguea** la
  necesidad de escalar CPU pero **no** reduce el prefijo (se documenta como
  pregunta abierta porque P5 lo sugería; reducirlo rompería el consenso).
- **Ley pendiente → `discarded`** (3.2): si la ventana vence sin nonce, la ley se
  descarta y **no** se reencola; su `text_hash` queda marcado para detectar
  reproposición.
- **Reproposición por hash exacto del texto** (3.5): idéntica a una descartada →
  cooldown mayor (`reproposed_identical`); distinta → propuesta nueva. Misma `n`.
- **Sellado y encadenamiento**: `block_hash = sha256(contenido)`, cada bloque
  referencia el `block_hash` anterior; la cadena se valida de punta a punta
  (links + que el nonce satisface la dificultad declarada).
- **El minero no se reimplementa** (Pilar 1): el worker lo invoca como subproceso
  y cae a CPU si no hay GPU. El "puente" es: `n` ceros ⇒ prefijo de `n` caracteres
  `'0'`.
- **Seguridad** (DOC.md): cero secretos en el repo; URLs y credenciales por
  variables de entorno; las **claves privadas nunca** se persisten ni viajan por
  RabbitMQ (sólo `author_pubkey`).
- **Tolerancia a fallos del NCT** (4): Bully-por-esfuerzo. Piezas de PoW listas;
  coordinación distribuida pendiente (test `xfail`). La ventana en curso se pierde
  por diseño.

## Limitaciones conocidas

- La elección distribuida del NCT está stubbeada (ver `nct/bully.py`).
- Sybil y concentración de poder en pools son vulnerabilidades **por diseño**
  documentado (AGENT.md 9), no bugs.
