# VoxChain — Funcionamiento del Sistema (Guía de Defensa)

> Documento de presentación y defensa del TP Integrador de Sistemas Distribuidos
> y Programación Paralela (UNLu, 2026). Explica **cómo funciona todo el sistema**:
> el camino feliz, y exhaustivamente **qué pasa cuando algo falla** (caída del
> NCT, de Redis, de RabbitMQ, de los workers, particiones de red, etc.).
>
> Para el dominio y las reglas de negocio cerradas, ver `AGENT.md`. Para el
> enunciado oficial, ver `DOC.md`. Este documento conecta esas reglas con la
> **implementación real** del repositorio y con el **comportamiento ante fallos**.

---

## Índice

1. [Qué es VoxChain (en una frase)](#1-qué-es-voxchain-en-una-frase)
2. [Componentes del sistema](#2-componentes-del-sistema)
3. [Mensajería: los flujos de RabbitMQ](#3-mensajería-los-flujos-de-rabbitmq)
4. [Estado persistido: el esquema de Redis](#4-estado-persistido-el-esquema-de-redis)
5. [El desafío de Proof of Work](#5-el-desafío-de-proof-of-work)
6. [Flujo feliz: de la propuesta al bloque sellado](#6-flujo-feliz-de-la-propuesta-al-bloque-sellado)
7. [Casos no felices del dominio (reglas de gobierno)](#7-casos-no-felices-del-dominio-reglas-de-gobierno)
8. [Casos no felices de infraestructura (caídas y fallos)](#8-casos-no-felices-de-infraestructura-caídas-y-fallos)
9. [Tolerancia a fallos del NCT: Bully por esfuerzo](#9-tolerancia-a-fallos-del-nct-bully-por-esfuerzo)
10. [Concurrencia y condiciones de carrera](#10-concurrencia-y-condiciones-de-carrera)
11. [Seguridad y ataques](#11-seguridad-y-ataques)
12. [Despliegue, escalado y observabilidad](#12-despliegue-escalado-y-observabilidad)
13. [Tabla resumen de modos de fallo](#13-tabla-resumen-de-modos-de-fallo)
14. [Limitaciones conocidas (declaradas)](#14-limitaciones-conocidas-declaradas)

---

## 1. Qué es VoxChain (en una frase)

**VoxChain es una blockchain distribuida cuyo propósito no es transferir dinero,
sino gobernar por consenso de esfuerzo computacional.** Cualquiera con un par de
claves pública/privada puede **proponer**, **promulgar** (votar a favor) y
**derogar** leyes. El consenso no se logra por "una persona, un voto", sino por
**Proof of Work (PoW)**: la voluntad colectiva se mide en *hashes calculados*, no
en *cabezas contadas*.

La idea original del proyecto es **mejorar el algoritmo Bully**: en lugar de
elegir coordinador por el mayor ID (criterio arbitrario), se elige por **prueba
de esfuerzo real**. Esto se aplica en dos lugares:

- **Gobierno:** ganar el derecho a promulgar/derogar una ley es "ganarle al
  resto" resolviendo el PoW primero.
- **Sucesión del coordinador (NCT):** si el coordinador cae, su sucesor se elige
  con un mini-desafío de PoW entre los candidatos, no por ID.

---

## 2. Componentes del sistema

El sistema está partido en **3 pilares**:

- **Pilar 1 — Minero:** el algoritmo de hashing en **CUDA (GPU)** con fallback a
  **CPU (Python)**. Recibe un string base, un prefijo (`n` ceros) y un rango de
  nonces; devuelve el primer nonce cuyo MD5 empieza con ese prefijo.
- **Pilar 2 — Infraestructura distribuida:** los servicios que orquestan el
  gobierno (lo que se detalla abajo).
- **Pilar 3 — Despliegue:** Kubernetes (GKE) + OpenTofu/Terraform, CI/CD,
  autoescalado (HPA/KEDA), observabilidad (Prometheus/Grafana).

### Servicios del Pilar 2

| Servicio | Rol | Comunicación |
|---|---|---|
| **voxchain-api** (FastAPI) | Gateway HTTP. Recibe propuestas del frontend, las publica a RabbitMQ; lee el estado de Redis para exponer la cadena, leyes y ventanas. Emite eventos en tiempo real por **SSE**. | HTTP ↔ frontend; publica a RabbitMQ; lee Redis |
| **voxchain-frontend** (Angular) | UI web. Genera identidad (par de claves) localmente, propone leyes, muestra la cadena en vivo. | HTTP ↔ API; SSE |
| **NCT (Nodo Coordinador de Tareas)** | El corazón del consenso. Gestiona **exclusivamente** las ventanas de votación: encola leyes, abre/cierra ventanas, verifica nonces y sella bloques. Corre con **réplica primary + standby** y failover por Bully. | Consume RabbitMQ; lee/escribe Redis |
| **Transaction Pool (TrP)** | Recibe el desafío activo y **fragmenta** el espacio de nonces en tramos pequeños que reparte a los workers. Recibe keep-alives para conocer la capacidad disponible. | RabbitMQ |
| **Worker** | Minero "standalone". Consume un fragmento de rango, mina (puente al binario CUDA o CPU del Pilar 1) y publica el nonce si lo encuentra. | RabbitMQ |
| **Pool Coordinator** | Una **facción política**: agrega varios *pool-miners* vía HTTP. Desde afuera es indistinguible de un worker. Subdivide el rango recibido entre sus miners. | RabbitMQ (hacia el NCT/TrP) + HTTP (hacia sus miners) |
| **Pool Miner** | Minero que se conecta a un Pool Coordinator por HTTP (no usa RabbitMQ). Pide sub-rangos, mina y devuelve resultados. | HTTP ↔ Pool Coordinator |
| **RabbitMQ** | Bus de mensajería asíncrona. Colas de trabajo + topics de broadcast. | — |
| **Redis** | Estado persistente: la cadena de bloques, leyes, ventanas, cooldowns y el *lease* de liderazgo del NCT. | — |

> **Decisión de diseño clave:** todo el código de dominio es **agnóstico del
> transporte y del backend**. Recibe una interfaz `Messaging` y un
> `VoxChainStore`. En producción se inyecta `RabbitMQMessaging` + Redis real; en
> los tests, un `InMemoryBus` + `fakeredis`. El mismo código corre idéntico en
> ambos. Esto permite probar toda la lógica distribuida (incluido el failover)
> de forma determinística.

---

## 3. Mensajería: los flujos de RabbitMQ

Hay **dos tipos de canales** en RabbitMQ, y la diferencia es crucial para
entender los fallos:

- **Colas de trabajo** (`propuestas`, `respuesta_nonce`, `tareas_trp`,
  `keepalive_trp`, `nct_election`): RabbitMQ reparte cada mensaje a **un solo
  consumidor** (round-robin entre los consumidores conectados).
- **Topics / exchanges de broadcast** (`desafio_activo`, `nct.heartbeat`):
  **fan-out**, cada suscriptor recibe **una copia** del mensaje.

Los flujos:

| # | Flujo | Tipo | De → A | Contenido |
|---|---|---|---|---|
| 1 | `propuestas` | cola | nodo/API → NCT | Una ley nueva (`law_id`, `author_pubkey`, `text_hash`, `action`, texto comprimido). |
| 2 | `desafio_activo` | **topic** | NCT → toda la red | El desafío de la ventana abierta (`voting_window_id`, `n_zeros_required`, `deadline`, `partial_hash_base`, `action`). |
| 3 | `respuesta_nonce` | cola | red → NCT | El nonce encontrado (`voting_window_id`, `nonce`, `winning_node_or_pool`). |
| 4 | `tareas_trp` | cola | TrP → workers | Un fragmento del espacio de nonces (`range_min`, `range_max`, más los datos del desafío). |
| 5 | `keepalive_trp` | cola | workers → TrP | Keep-alive con capacidad y si tiene GPU. |
| 6 | `nct.heartbeat` | **topic** | NCT líder → followers | Latido periódico del líder (cada `HEARTBEAT_INTERVAL` ≈ 3 s). |
| 7 | `nct_election` | cola | candidato → candidatos | Claim de elección: "yo resolví el mini-PoW, este es mi nonce". |

**Garantías de RabbitMQ usadas:**
- Mensajes **persistentes** (`delivery_mode=2`) y colas **durables** → sobreviven
  a un reinicio del broker.
- `prefetch_count=1` → un consumidor recibe un mensaje por vez (reparto justo).
- **ACK manual** tras procesar (`basic_ack` en `finally`) → si el consumidor
  muere antes del ACK, RabbitMQ **reentrega** el mensaje a otro consumidor.

---

## 4. Estado persistido: el esquema de Redis

Redis es la fuente de verdad del estado. Claves principales:

| Clave | Estructura | Contenido |
|---|---|---|
| `law:<id>` | hash | La ley: autor, `text_hash`, `status`, `action`, texto comprimido. |
| `window:<id>` | hash | La ventana: ley, acción, `n_zeros_required`, `deadline`, resultado, ganador. |
| `block:<hash>` | hash | Un bloque sellado de la cadena. |
| `chain` | lista | Orden de la cadena (lista de `block_hash`). |
| `law_queue` | lista | Leyes en estado `pending_queue` esperando turno. |
| `cooldown:<pubkey>` | hash | Hasta qué ventana el autor no puede volver a proponer. |
| `discarded_text_hashes` | set | Hashes de textos descartados (para detectar reproposición idéntica). |
| `active_window` | string | El `voting_window_id` vigente (solo uno a la vez). |
| `window_sealed:<id>` | string (TTL) | **Guard atómico de cierre**: el primer nonce válido lo escribe (SETNX). |
| `window_counter` | contador | Número monótono de ventanas (base del cooldown). |
| `nct:leader` | string (TTL) | **Lease de liderazgo del NCT** (quién es el coordinador activo). |
| `nct:last_author` | string | Último autor cuya ley entró a ventana (para el round-robin). |

> **Las claves privadas de los individuos NUNCA se persisten.** Solo circula la
> `author_pubkey`. La clave privada vive y firma exclusivamente en el navegador
> del usuario.

---

## 5. El desafío de Proof of Work

El "string base" que se hashea **no es una transacción de dinero**, es el
desafío de gobierno serializado:

```
partial_hash_base = law_id + text_hash + voting_window_id + action
```

**Resolver el desafío** = encontrar un `nonce` tal que:

```
md5(partial_hash_base + str(nonce))   empieza con  n ceros
```

- **Promulgar** una ley exige **n** ceros.
- **Derogar** una ley exige **n+1** ceros (siempre más difícil, por diseño:
  destruir consenso debe costar más esfuerzo que construirlo).

`n` es **fijo y configurable** (`N_ZEROS`, default 4). **No hay ajuste dinámico
de dificultad** — esa fue una decisión deliberada documentada en `AGENT.md §11`:
cualquier regla de ajuste autónomo basada en el comportamiento de los actores es
*gameable* (un atacante con identidades Sybil puede manipular el promedio para
abaratar su propia ley). El ajuste, si hace falta, lo hace un operador externo.

El mismo MD5 y la misma convención de prefijo se usan en tres lugares idénticos:
el minero del Pilar 1, el puente del worker, y la verificación del NCT
(`common/blockchain/challenge.py`). Así la verificación es exacta.

---

## 6. Flujo feliz: de la propuesta al bloque sellado

Este es el camino completo cuando todo funciona:

```
Usuario (frontend)
   │  1. Genera par de claves localmente. Escribe el texto de la ley.
   ▼
voxchain-api (POST /api/laws)
   │  2. Calcula SHA-256 del texto, lo comprime, arma el law_id.
   │  3. Verifica cooldown del autor en Redis (si está en cooldown → HTTP 429).
   │  4. Publica la ley a la cola `propuestas`.
   ▼
NCT (líder)  — handle_proposal()
   │  5. Valida (author + text_hash + action válidos). Re-chequea cooldown.
   │  6. Detecta si es reproposición idéntica (hash en discarded_text_hashes).
   │  7. Guarda la ley en Redis (status=pending_queue), la encola en law_queue.
   │  8. Setea el cooldown del autor.
   │  9. maybe_open_window(): si no hay ventana activa, abre una.
   ▼
NCT  — open_window()
   │ 10. Elige la próxima ley por ROUND-ROBIN entre autores distintos.
   │ 11. Incrementa window_counter, arma voting_window_id = "W<n>-<law_id>".
   │ 12. Calcula n_zeros (n o n+1) y el partial_hash_base.
   │ 13. Persiste la ventana, marca la ley IN_WINDOW, setea active_window.
   │ 14. Publica el desafío al topic `desafio_activo` (lo reciben TODOS).
   ▼
Transaction Pool  — handle_challenge()
   │ 15. Recibe el desafío. Mira qué workers están frescos (keep-alives).
   │ 16. Fragmenta [0, NONCE_SPACE) en tramos de FRAGMENT_SIZE.
   │ 17. Publica cada tramo a la cola `tareas_trp`.
   ▼
Workers / Pools  — handle_task()
   │ 18. Cada worker toma un fragmento (round-robin de RabbitMQ).
   │ 19. Mina ese rango: invoca el binario CUDA (GPU) o el script CPU.
   │ 20. Si encuentra el nonce → publica a `respuesta_nonce`.
   │     (Un Pool subdivide su fragmento entre sus pool-miners por HTTP.)
   ▼
NCT (líder)  — handle_nonce_response()
   │ 21. ¿Es para la ventana activa? ¿Llegó antes del deadline? Si no → descarta.
   │ 22. ¿El que gana NO es el autor de la ley? (el autor no vota su propia ley)
   │ 23. verify_nonce(): recalcula el MD5 y comprueba los n ceros.
   │ 24. CIERRE ATÓMICO: try_seal_window() (SETNX en Redis). El PRIMER nonce
   │     válido gana; los demás ven la clave ya puesta y se descartan.
   │ 25. _seal(): arma el bloque, lo encadena (previous_hash), lo guarda en Redis.
   │ 26. Marca la ley PROMULGATED (o REPEALED si era derogación).
   │ 27. Limpia active_window y abre la siguiente ventana (maybe_open_window()).
   ▼
voxchain-api  — sse_polling_task()
   │ 28. Detecta el bloque nuevo / cambio de ventana / cambio de status en Redis.
   │ 29. Emite eventos SSE (block_added, window_opened, law_updated).
   ▼
Frontend
     30. Actualiza la UI en tiempo real: la ley aparece promulgada en la cadena.
```

**Duración de la ventana:** `WINDOW_SECONDS_PROMULGACION` (60 s) o
`WINDOW_SECONDS_DEROGACION` (90 s). Si nadie encuentra el nonce en ese tiempo, la
ventana **vence** (ver caso no feliz 7.1).

---

## 7. Casos no felices del dominio (reglas de gobierno)

Estos son los casos donde el sistema **rechaza o descarta** algo a propósito,
según las reglas de gobierno. No son errores: son el comportamiento esperado.

### 7.1 La ventana vence sin que nadie encuentre el nonce
- **Qué pasa:** `check_deadline()` detecta que pasó el `deadline`.
- **Acción:** la ventana se marca `expired_pending`, la ley pasa a `discarded`,
  y su `text_hash` se agrega a `discarded_text_hashes`.
- **Importante:** la ley **NO se reencola automáticamente**. Se interpreta como
  un pedido tácito de revisión: alguien debe reproponerla. El esfuerzo de
  cómputo invertido se pierde.
- **Luego:** el NCT abre la siguiente ventana de la cola (si hay leyes).

### 7.2 Llega un nonce, pero la ventana ya cerró (nonce tardío)
- **Causas:** llegó después del `deadline`, o para una ventana que ya se selló.
- **Acción:** `handle_nonce_response()` lo descarta (chequeo de `deadline_epoch`
  y de `voting_window_id`). Si la ventana ya fue sellada por otro, el guard
  `window_sealed:<id>` en Redis devuelve `False` y se descarta como tardío.

### 7.3 Llegan DOS nonces válidos casi simultáneos para la misma ventana
- **Qué pasa:** dos workers/pools resuelven el desafío casi al mismo tiempo.
- **Acción:** el **cierre atómico** (`try_seal_window`, SETNX en Redis) garantiza
  que **solo el primero** sella el bloque. El segundo ve la clave ya puesta y se
  descarta. **No se crean dos bloques, no hay fork.** Esto resuelve el "BUG 2"
  documentado y es autoritativo incluso ante failover (el guard vive en Redis,
  no en memoria del proceso).

### 7.4 El nonce recibido es inválido (no cumple los n ceros)
- **Causa:** un nodo malicioso o con bug envía un nonce que no resuelve el
  desafío.
- **Acción:** `verify_nonce()` recalcula el MD5 y lo rechaza. **El NCT nunca
  confía: siempre re-verifica.** No se sella nada.

### 7.5 El autor intenta ganar la ventana de su propia ley
- **Regla (AGENT.md 3.4):** el autor pierde el derecho a voto **únicamente en la
  ventana de su propia ley**.
- **Acción:** si `winning_node_or_pool == author_pubkey`, el nonce se descarta.

### 7.6 Un autor en cooldown intenta proponer otra ley
- **Regla:** tras proponer, el autor entra en cooldown de `N` ventanas.
- **Doble barrera:** la API rechaza con **HTTP 429** (con mensaje de cuántas
  ventanas faltan); y aunque el mensaje llegara igual a la cola, el NCT
  re-verifica el cooldown en `handle_proposal()` y lo ignora.

### 7.7 Reproposición idéntica de una ley descartada
- **Regla (AGENT.md 3.5):** se compara por **hash exacto del texto**.
  - Texto **idéntico** a uno descartado → cooldown **mayor** (penaliza insistir
    sin cambios): `COOLDOWN_WINDOWS_REPROPOSED` (default `2*n`).
  - Texto **distinto** (aunque cambie una coma) → propuesta nueva, cooldown
    normal `COOLDOWN_WINDOWS_NEW` (default `n`).
- **Acción:** `classify_proposal()` consulta `is_text_hash_discarded()` y aplica
  el cooldown correspondiente.

### 7.8 Se intenta derogar una ley que no está promulgada
- **Acción:** `_enqueue_derogacion()` verifica que la ley exista y su `status`
  sea `promulgated`. Si no, la derogación se rechaza y se loguea.

### 7.9 Propuesta malformada (falta autor o text_hash, action inválida)
- **Acción:** se loguea un warning y se descarta. No tumba al NCT.

### 7.10 No hay leyes en la cola
- **Acción:** `maybe_open_window()` no hace nada (no hay ventana vacía). El NCT
  espera nuevas propuestas. El sistema queda **idle**, no roto.

---

## 8. Casos no felices de infraestructura (caídas y fallos)

Aquí está lo que pide la consigna: **qué pasa si se cae cada cosa.**

### 8.1 Se cae el NCT (el coordinador)
Este es **el caso central** del proyecto. Resumen (detalle en §9):

1. El NCT líder deja de emitir heartbeats (`nct.heartbeat`).
2. Los followers (standby, o cualquier nodo sin lease) detectan el silencio tras
   `HEARTBEAT_TIMEOUT` (12 s).
3. Se dispara la **elección Bully por esfuerzo**: cada candidato resuelve un
   mini-PoW (`ELECTION_N_ZEROS` = 3 ceros) sobre un seed compartido (hash del
   último bloque).
4. El primero que lo resuelve publica su claim a `nct_election` y adquiere el
   **lease** `nct:leader` en Redis (vía Lua/SET con reglas de TTL).
5. Ese candidato se promueve a líder: **abre las colas de trabajo**
   (`propuestas`, `respuesta_nonce`) y empieza a emitir heartbeats.
6. **La ventana en curso se pierde.** El nuevo NCT siempre arranca con una
   ventana nueva (limitación declarada — AGENT.md §4). El cómputo de la ventana
   perdida no se aprovecha.
- **Por qué no se duplican bloques tras el failover:** el guard
  `window_sealed:<id>` y el contador `window_counter` viven en Redis, no en el
  proceso caído.

### 8.2 El NCT primario reinicia (p. ej. Kubernetes lo reprograma)
- Al arrancar en modo `primary`, intenta adquirir el lease con SETNX.
- **Si otro nodo ya es líder** (un standby se promovió mientras reiniciaba), el
  SETNX falla y **arranca como follower**, monitoreando heartbeats. No hay dos
  líderes. El "primario" es solo una etiqueta cosmética; **quien manda es quien
  tiene el lease**, no el nombre del servicio.

### 8.3 Partición de red que aísla al NCT líder (split-brain)
- **Riesgo:** el primario no murió, pero quedó aislado; un standby cree que cayó
  y se promueve. Por un instante podría haber dos líderes.
- **Mitigación:** en cada `tick()`, el líder ejecuta `renew_leadership()` (Lua
  atómico): comprueba que el lease en Redis **sigue siendo suyo**. Si otro NCT lo
  adquirió, el líder original ejecuta `step_down()`:
  - `is_leader = False`
  - **Cancela los consumidores** de `propuestas` y `respuesta_nonce` (no basta
    con ignorar en memoria: RabbitMQ ya le entregó mensajes en round-robin, hay
    que dejar de consumirlos para no "robárselos" al líder real).
  - Suelta la ventana en curso y reactiva su monitor de heartbeats.
- **Ventana de solapamiento:** la detección no es instantánea; dura hasta
  `HEARTBEAT_INTERVAL` (≈3 s). Es una **limitación conocida y aceptada**.

### 8.4 Se cae Redis
Redis es la **fuente de verdad** y un **punto único de fallo** del estado.
- **Salud:** el endpoint `/health` del NCT y de la API reporta `redis: down`.
- **Efectos:**
  - El NCT no puede leer la cola, abrir/cerrar ventanas ni sellar bloques.
  - Falla `renew_leadership` → el líder hace `step_down`; **nadie puede adquirir
    el lease** (Redis está caído) → el sistema **se detiene de forma segura**, no
    corrompe la cadena.
  - La API responde, pero las lecturas de cadena/leyes fallan.
- **Recuperación:** en Kubernetes, Redis es un **StatefulSet con persistencia
  (PVC)**. Al reprogramarse, recupera el volumen y la cadena queda intacta. Al
  volver, el NCT readquiere el lease y continúa.
- **Mitigación de diseño:** el estado crítico está **idempotentemente** modelado
  (SETNX, contadores monótonos), así que un reinicio no produce dobles bloques.

### 8.5 Se cae RabbitMQ
- **Salud:** `/health` reporta `rabbitmq: down`.
- **En la conexión:** `RabbitMQMessaging.connect()` **reintenta** (hasta 30
  intentos, 2 s entre cada uno) antes de rendirse. Los servicios que arrancan con
  RabbitMQ caído esperan a que vuelva.
- **Mensajes en vuelo:** colas durables + mensajes persistentes → **no se pierden
  los mensajes ya encolados** cuando el broker reinicia.
- **Mensajes sin ACK:** si un consumidor muere procesando, RabbitMQ **reentrega**
  el mensaje a otro (el ACK es manual y va en `finally`).
- **Efecto temporal:** mientras RabbitMQ está caído, no fluyen propuestas ni
  desafíos ni respuestas; el sistema queda en pausa, pero **no corrompe estado**.

### 8.6 Se cae el Transaction Pool (TrP)
- **Efecto:** los desafíos publicados por el NCT al topic `desafio_activo` no se
  fragmentan ni se reparten a los workers vía `tareas_trp`. La ventana
  probablemente **vence** (caso 7.1) y la ley queda `discarded`.
- **Recuperación:** el TrP es **stateless** respecto de la cadena (solo mantiene
  en memoria un mapa de keep-alives frescos). Tiene **≥2 réplicas** y autoescala
  por CPU (HPA). Al volver, retoma desde el próximo desafío. No hay estado que
  reconstruir.
- **Nota:** como `desafio_activo` es un **topic**, cada réplica del TrP recibe
  una copia del desafío. Las réplicas fragmentan en paralelo; los workers toman
  los fragmentos por round-robin de la cola `tareas_trp`.

### 8.7 Se cae un Worker (minero standalone)
- **Mientras minaba:** el mensaje de su fragmento ya fue ACKeado al recibirlo
  (procesamiento síncrono); ese fragmento concreto no se reintenta, pero **otros
  fragmentos** del mismo espacio siguen siendo minados por otros workers. Como el
  rango total se fragmenta, perder un worker solo reduce el throughput, **no
  rompe la ventana**: si la solución estaba en otro fragmento, igual se encuentra.
- **Idempotencia:** el worker recuerda las ventanas que ya resolvió (`_solved`),
  así que una reentrega no genera un doble envío.
- **Autoescalado:** los workers GPU corren en un cluster k3s con **KEDA**
  (escala por profundidad de la cola `tareas_trp`) + HPA (máx 10). Si caen, KEDA
  levanta nuevos según la demanda.

### 8.8 No hay workers con GPU disponibles
- **Detección:** el TrP mira los keep-alives frescos (`KEEPALIVE_TTL` = 15 s) y
  ve que ninguno tiene GPU.
- **Acción (decisión de diseño):** el TrP **loguea** la necesidad de escalar
  mineros CPU, **pero NO reduce la dificultad** `n`. La dificultad la fija el NCT
  y el ajuste dinámico está prohibido (sería *gameable*). El enunciado sugería
  "bajar el prefijo sin GPU", pero eso contradiría la dificultad fija del
  consenso, así que se documenta la decisión en lugar de implementarla.
- **Escalado real:** levantar mineros CPU es responsabilidad del **Pilar 3**
  (HPA/KEDA), no de la lógica del TrP. Con solo mineros CPU, las ventanas tardan
  más (o vencen si `n` es alto), lo cual es el comportamiento esperado.

### 8.9 Se cae el Pool Coordinator
- **Liderazgo de pool:** el Pool Coordinator también usa un **lease en Redis**
  (`pool:leader`, TTL 10 s). Solo el líder consume la cola `tareas_trp` y emite
  keep-alives. Si el líder cae, otra réplica adquiere el lease en su próximo
  `tick()` y toma el relevo.
- **Miners conectados:** los pool-miners hacen polling HTTP; si el coordinator no
  responde, reintentan (`request_work` devuelve `None` → esperan y reintentan).
- **Efecto:** la facción "pool" pierde temporalmente su capacidad agregada, pero
  los workers standalone y otros pools siguen compitiendo por la ventana.

### 8.10 Se cae un Pool Miner
- Es un cliente HTTP puro. Si cae, el Pool Coordinator lo detecta porque deja de
  recibir su heartbeat (`KEEPALIVE_TTL` = 15 s) y lo **purga** de la lista de
  miners frescos. El rango que tenía asignado simplemente no se completa, pero
  el coordinator reparte el trabajo entre los miners que quedan vivos.
- Al volver, el pool-miner se **re-registra** (reintenta cada 5 s hasta lograrlo).

### 8.11 Se cae la voxchain-api
- **Efecto:** el frontend no puede proponer leyes ni leer estado; se cortan los
  eventos SSE.
- **Pero:** el núcleo del consenso (NCT + workers + Redis + RabbitMQ) **sigue
  funcionando**. La API es solo un gateway de lectura/escritura, no participa del
  consenso.
- **Recuperación:** ≥2 réplicas detrás de un Service/Ingress + HPA por CPU. Al
  reconectar, el frontend reabre el stream SSE y re-sincroniza desde Redis.

### 8.12 Se cae el frontend
- Es estático (Angular servido por nginx). Sin impacto en el backend. Las
  identidades viven en el navegador del usuario; al recargar, se reconstruye la
  vista desde la API.

### 8.13 Mensaje malformado / excepción procesando
- El wrapper de consumo (`_wrap`) captura **cualquier excepción**, la loguea, y
  **siempre ACKea** en `finally`. Un mensaje venenoso no traba la cola ni tumba
  el servicio; se descarta y se sigue.

### 8.14 El minero GPU falla o no está disponible
- El puente `run_miner()` intenta GPU si el binario existe y es ejecutable. Ante
  **cualquier excepción** (driver ausente, binario corrupto, timeout), hace
  **fallback automático a CPU** (script Python). El sistema sigue minando, más
  lento. Esto cubre el escenario "ingreso/egreso de nodos GPU" del Pilar 3.

---

## 9. Tolerancia a fallos del NCT: Bully por esfuerzo

El mecanismo estrella del proyecto. Componentes:

- **`nct/coordinator.py`** — el coordinador en sí (líder o follower).
- **`nct/monitor.py`** — observa heartbeats y dispara la elección.
- **`nct/bully.py`** — resuelve el mini-PoW y arbitra el ganador.
- **Redis** — `nct:leader` (el lease) es el árbitro final y autoritativo.

### Roles y arranque
- `NCT_MODE=primary`: intenta adquirir el lease al arrancar (SETNX). Si lo
  consigue, es líder inicial; si no, arranca como follower.
- `NCT_MODE=standby`: arranca como follower.
- **El rol real lo decide el lease, no la etiqueta.** Cualquier nodo sin lease
  corre el monitor y puede ganar una elección futura.

### El líder, mientras vive
- Cada `tick()` (1 s): chequea deadline de la ventana, abre ventanas si hace
  falta, y cada `HEARTBEAT_INTERVAL` (3 s) **renueva el lease** y **emite
  heartbeat**.
- Si la renovación del lease falla → `step_down()` (alguien le ganó el lease →
  split-brain, ver 8.3).

### El follower, vigilando
- Se suscribe a `nct.heartbeat` y `nct_election`. **NO** consume las colas de
  trabajo (si lo hiciera, le robaría la mitad de los mensajes al líder por el
  round-robin de RabbitMQ — este es el "BUG 1" que se corrigió con el *gating*
  por liderazgo).
- Si pasan `HEARTBEAT_TIMEOUT` (12 s) sin heartbeat → dispara la elección.

### La elección (`run_distributed_election`)
1. Calcula el seed: `hash_del_último_bloque + "::election-" + timestamp`
   (determinístico y compartido → competencia justa).
2. Resuelve el mini-PoW localmente (`ELECTION_N_ZEROS` = 3 ceros).
3. **Backoff:** si mientras resuelve recibe un claim válido de otro candidato que
   se adelantó, **se retira**.
4. Si resuelve primero: publica su claim a `nct_election` y **adquiere el lease**
   con `elect_acquire_leadership()`:
   - Lease inexistente (expiró) → adquiere.
   - Lease es suyo (restart) → renueva.
   - Lease es de otro con **TTL bajo** (`≤ dead_threshold`, ≈6 s) → el holder
     está muerto → adquiere.
   - Lease es de otro con **TTL alto** → otro candidato ganó la elección
     concurrente → **falla** (evita split-brain).
5. El ganador llama `become_leader()`: abre las colas de trabajo, relee el último
   autor, **descarta cualquier ventana en curso** y abre una nueva si hay leyes.

### Por qué es "Bully mejorado"
El Bully clásico elige por **mayor ID** — arbitrario, y en redes amplias con
nodos lejanos no refleja capacidad real. Aquí el sucesor se gana **resolviendo un
PoW**: quien tiene más poder de cómputo (o más suerte) y está mejor conectado
gana, que es exactamente la filosofía de toda la red VoxChain.

---

## 10. Concurrencia y condiciones de carrera

| Carrera | Cómo se resuelve |
|---|---|
| Dos workers resuelven el mismo desafío | `try_seal_window` (SETNX en Redis): el primero gana, el resto se descartan como tardíos. |
| Dos candidatos ganan la elección casi a la vez | Backoff del PoW (el segundo ve el claim del primero y se retira) + reglas de TTL del lease. |
| Dos NCT como líder (split-brain) | `renew_leadership` (Lua atómico) → el que pierde el lease hace `step_down`. |
| Dos `primary` arrancan juntos | SETNX: solo uno adquiere; el otro arranca follower. |
| Un follower roba mensajes de las colas de trabajo | *Gating* por liderazgo: el follower nunca se suscribe a `propuestas`/`respuesta_nonce`. |
| Reentrega de un mensaje ya procesado | Sets de idempotencia (`_solved` en worker/pool); el NCT re-verifica todo. |
| Dos pool-coordinators activos | Lease `pool:leader` en Redis (TTL 10 s). |

**Nota honesta:** `elect_acquire_leadership` es GET+SET (no atómico). La
atomicidad efectiva la dan el backoff del PoW (en condiciones normales solo un
candidato llega ahí) y el margen temporal corto. Está documentado como tal.

---

## 11. Seguridad y ataques

| Amenaza | Tratamiento |
|---|---|
| **Ataque Sybil** (un individuo, muchas identidades) | **Posible por diseño**, declarado. Mitigarlo requeriría anclar las claves a un DNI real → una autoridad central, que contradice la filosofía descentralizada. Queda como trabajo futuro. |
| **Ataque del 51%** | Inherente a PoW: quien controla la mayoría del cómputo gana las ventanas más seguido. Se documenta como observación de diseño (favorece a pools grandes), no se mitiga. |
| **Nonce falsificado** | El NCT **siempre re-verifica** el MD5; un nonce inválido se descarta. |
| **Votar en nombre de otro** | Imposible: la clave privada nunca sale del nodo del usuario. |
| **Secretos en el repo** | `gitleaks` corre en CI y **rompe el pipeline** si encuentra un secreto. `.gitignore` configurado. |
| **Credenciales estáticas** | **Zero static keys**: Workload Identity Federation (OIDC) para CI/CD; External Secrets Operator sincroniza desde GCP Secret Manager. |
| **Tráfico de workers externos** | RabbitMQ con **TLS (AMQPS, puerto 5671)** y CA autofirmada para los workers GPU del cluster k3s externo. |

---

## 12. Despliegue, escalado y observabilidad

### Topología (Pilar 3)
- **Cluster 1 — GKE (GCP):** namespace `voxchain`. Aloja RabbitMQ, Redis, NCT
  (primary + standby), TrP, API y frontend.
  - Nodepool `infra` **tainted** → aísla Redis/RabbitMQ.
  - Nodepool `apps` con **autoscaling** → NCT, TrP, API, Frontend.
- **Cluster 2 — k3s externo:** workers GPU, conectados a RabbitMQ por el
  LoadBalancer AMQPS. Escalan con **KEDA** (por profundidad de cola) + HPA.

### Infraestructura como código
- **OpenTofu/Terraform** crea VPC, GKE, nodepools, External Secrets, Artifact
  Registry y el stack de monitoreo. Reproducible y declarativo.

### CI/CD (GitHub Actions)
- `ci-checks` → en cada PR: **gitleaks + pytest**.
- `01-infra` → `tofu apply` (manual).
- `02-services` → despliega Redis + RabbitMQ.
- `03-apps` → build + deploy de las apps del Pilar 2.
- `04-gpu-workers` → deploy de workers al k3s.

### Alta disponibilidad
- **≥2 réplicas por servicio** (requisito del enunciado).
- HPA por CPU (API, TrP); KEDA por cola (workers).
- Redis como StatefulSet con PVC; GKE regional (1 nodo/AZ) para HA del plano de
  control.

### Observabilidad (U5.5)
- **kube-prometheus-stack** (Prometheus + Grafana + Alertmanager).
- Cada servicio expone `/metrics` con métricas de aplicación:
  - NCT: propuestas, ventanas abiertas, bloques sellados, `nct_is_leader`.
  - TrP: workers activos, tareas publicadas.
  - Worker/Pool: tareas recibidas, nonces encontrados, `busy`, `has_gpu`.
  - API: requests y latencia por ruta.
- `/health` en cada servicio devuelve JSON con el estado de sus dependencias
  (Redis/RabbitMQ), cumpliendo el requisito de endpoint de estado.
- Logs en memoria y disco (`logging_setup.py`).

---

## 13. Tabla resumen de modos de fallo

| Componente que cae | Impacto inmediato | Recuperación | ¿Corrompe la cadena? |
|---|---|---|---|
| **NCT líder** | Se detiene el avance de ventanas | Elección Bully por PoW; nuevo líder en ~12-15 s | No (guard en Redis) |
| **NCT primario reinicia** | Ninguno si hay standby | Arranca como follower | No |
| **Partición NCT (split-brain)** | Solapamiento ≤3 s | `step_down` por fallo de `renew_leadership` | No |
| **Redis** | Sistema se detiene (seguro) | StatefulSet + PVC; readquiere lease al volver | No (idempotencia) |
| **RabbitMQ** | Mensajería en pausa | Reconexión con reintentos; colas durables | No |
| **Transaction Pool** | Ventana puede vencer | Réplicas + HPA; stateless | No |
| **Worker** | Menos throughput | KEDA/HPA levanta otros; fragmentos redundantes | No |
| **Sin GPU** | Ventanas más lentas | Escalado CPU (Pilar 3); dificultad NO baja | No |
| **Pool Coordinator** | Pool pierde capacidad | Lease `pool:leader`; otra réplica toma | No |
| **Pool Miner** | Menos capacidad del pool | Purga por keep-alive; re-registro | No |
| **voxchain-api** | Frontend sin servicio | Réplicas + HPA; consenso sigue | No |
| **Frontend** | UI caída | Estático, sin impacto backend | No |
| **Minero GPU** | — | Fallback automático a CPU | No |

---

## 14. Limitaciones conocidas (declaradas)

Honestidad de ingeniería: estas limitaciones están **documentadas a propósito**,
no son descuidos.

1. **Pérdida de la ventana en curso al caer el NCT.** El cómputo invertido en la
   ventana activa se descarta; el nuevo líder arranca con una ventana nueva.
   Mitigarlo (persistir y reanudar la ventana) se decidió fuera de alcance.
2. **Ventana de split-brain de hasta `HEARTBEAT_INTERVAL` (≈3 s).** Detectada por
   `renew_leadership`, pero no instantánea.
3. **Sybil sin mitigar.** El sistema es pseudo-anónimo por diseño.
4. **Concentración de poder.** Igual que las blockchains reales de PoW, favorece
   estructuralmente a los pools grandes. Es una observación política
   intencional del proyecto, no un bug.
5. **Redis como punto único de estado.** Mitigado con persistencia y la
   propiedad de que un reinicio no duplica bloques, pero sigue siendo el SPOF del
   estado.
6. **`elect_acquire_leadership` no es estrictamente atómico** (GET+SET); la
   atomicidad real la aporta el backoff del PoW.

---

### Cierre

VoxChain demuestra los conceptos centrales de la materia en un sistema coherente:
**procesamiento paralelo** (CUDA + bolsa de tareas fragmentada), **comunicación
asíncrona** (RabbitMQ con colas y topics), **consenso y tolerancia a fallos**
(Bully por esfuerzo, leases en Redis, cierre atómico), **persistencia
distribuida** (Redis + esquema de cadena), y **despliegue cloud-native**
(Kubernetes, IaC, CI/CD, autoescalado y observabilidad). La elección de "gobierno
por PoW" en vez de "transferencias de dinero" es el giro original que ata todo:
la misma prueba de esfuerzo que protege la cadena es la que elige al coordinador
cuando cae — el Bully mejorado que da origen al proyecto.
