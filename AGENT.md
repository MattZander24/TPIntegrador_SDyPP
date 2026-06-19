# AGENT.md — VoxChain: Democracia vía Blockchain

> Documento de contexto para asistentes de IA (Claude, Copilot, ChatGPT/Codex, Cursor, etc.) que colaboren en el desarrollo de este proyecto. Resume el dominio, las reglas de negocio, las decisiones de diseño ya cerradas, y cómo todo eso mapea a la arquitectura técnica exigida por el TP Integrador de Blockchain Distribuida y CUDA (UNLu, Sistemas Distribuidos y Programación Paralela, 2026).
>
> Si estás generando código, documentación o tests para este proyecto, este archivo es la fuente de verdad sobre el dominio. Ante cualquier ambigüedad de implementación, las reglas acá descritas tienen prioridad sobre supuestos genéricos de "cómo funciona normalmente una blockchain".

---

## 1. Resumen del proyecto

**VoxChain** es una blockchain distribuida cuyo propósito no es transferir dinero, sino **gobernar por consenso de esfuerzo computacional**. Cualquier individuo capaz de generar un par de claves pública/privada es un participante con derecho a proponer, votar (promulgar) y derogar leyes. El consenso no se logra por votación nominal (una persona, un voto) sino por **Proof of Work**: la voluntad colectiva se mide en hashes calculados, no en cabezas contadas.

La motivación de diseño es deliberadamente política, no solo técnica: el sistema reproduce, a propósito, la dinámica de concentración de poder de las blockchains reales (pools grandes ganan más seguido), y eso se documenta como una observación de diseño, no como un bug.

### 1.1 Relación con el algoritmo Bully

El proyecto nace de una idea original: mejorar el algoritmo Bully (elección de coordinador por mayor ID) para sistemas muy amplios y con miembros lejanos, reemplazando el criterio arbitrario de ID por una **prueba de esfuerzo real**. Esa idea se aplica en dos lugares del sistema:

- **Gobierno:** ganar el derecho de promulgar/derogar una ley es, en esencia, "ganarle al resto" mediante esfuerzo, igual que el nodo Bully le gana al resto por ID.
- **Sucesión del coordinador (NCT):** si el NCT cae, la elección del sucesor se resuelve con un mini-desafío de PoW entre los nodos candidatos, no por ID. Ver sección 6.

---

## 2. Glosario del dominio

| Término | Significado |
|---|---|
| **Individuo / Nodo** | Cualquier participante identificado por un par de claves pública/privada. |
| **Nodo minero** | Individuo que aporta poder de cómputo directamente. |
| **Nodo pool** | Agregador de mineros. Indistinguible de un participante normal desde afuera. |
| **Nodo pool-de-pools** | Agregador de pools. El diseño es recursivo en teoría; la implementación fija 2 niveles (minero → pool → NCT). |
| **NCT (Nodo Coordinador de Tareas)** | Gestiona exclusivamente las ventanas de votación. No arbitra contenido, no decide si una ley es "buena". |
| **Ley** | Una propuesta de texto, identificada por hash, que puede promulgarse o derogarse. |
| **Ventana de votación** | Período de tiempo durante el cual la red completa apunta su poder de cómputo a resolver el desafío de una única ley. |
| **Desafío de esfuerzo** | Encontrar un nonce tal que el hash resultante tenga **n ceros** iniciales (promulgar) o **n+1 ceros** (derogar). |
| **Cooldown** | Período de ventanas durante el cual un autor no puede proponer una nueva ley, tras proponer una. |
| **Ley pendiente** | Ley cuya ventana cerró sin que nadie encontrara el nonce. Se descarta; se interpreta como pedido tácito de revisión. |

---

## 3. Reglas de gobierno (decisiones cerradas)

Estas reglas son normativas. Cualquier implementación debe respetarlas exactamente; no son sugerencias.

### 3.1 Identidad

- Identidad = par de claves pública/privada, generado localmente por el individuo.
- **No hay verificación de identidad real.** El sistema es pseudo-anónimo y vulnerable a ataques Sybil (un individuo puede generar múltiples identidades) **por diseño conocido y documentado**, no por descuido.
- **Extensión futura fuera de alcance:** anclar la generación de claves a un documento de identidad real (DNI) para mitigar Sybil. No se implementa en este TP porque requeriría una autoridad certificadora externa, lo cual contradice la filosofía descentralizada del sistema. Se menciona en el informe como trabajo futuro, no como feature.
- La clave privada **nunca sale del nodo del individuo** — ni siquiera para almacenamiento. Esto es coherente con la idea de que nadie puede votar en nombre de otro.

### 3.2 Ciclo de vida de una ley

1. Cualquier nodo propone una ley. **Proponer no tiene costo de PoW**, solo de cooldown (ver 3.4).
2. El NCT encola la propuesta.
3. Cuando le toca turno (round-robin entre autores distintos, ver 3.3), el NCT abre una ventana de votación con dificultad **n ceros** (promulgación).
4. Si algún nodo o pool encuentra el nonce válido antes de que cierre la ventana → la ley se promulga y se adhiere a la cadena.
5. Si nadie lo logra antes del cierre → la ley queda **pendiente** y se descarta. No vuelve a la cola automáticamente; alguien debe reproponerla (ver 3.5).

### 3.3 Cola de ventanas

- **Una sola ventana de votación activa en todo momento** (cola secuencial). No hay ventanas paralelas ni fragmentación de cómputo entre leyes distintas.
- El NCT decide qué ley entra a la siguiente ventana mediante **round-robin entre autores distintos** (no FIFO estricto, para evitar que un autor monopolice turnos consecutivos).

### 3.4 Costo de proponer y cooldown

- El autor de una ley pierde el derecho a voto **únicamente en la ventana de su propia ley** (no en ventanas ajenas).
- Tras proponer, el autor entra en cooldown de **n ventanas** antes de poder proponer otra ley.
- Si la ley queda pendiente (sin nonce encontrado), se descarta definitivamente. No hay reapertura automática.

### 3.5 Reproposición

- Se compara por **hash exacto del texto** de la ley. Cualquier cambio, sin importar cuán mínimo, cuenta como contenido distinto.
- **Idéntica** a una descartada anteriormente → cooldown **mayor** al normal (penaliza insistir sin cambios).
- **Distinta** (aunque sea una corrección mínima) → se trata como propuesta nueva, con el cooldown normal de 3.4.
- No hay diferencia de dificultad de promulgación entre una ley nueva y una revisada. Todas usan el mismo **n** base.

### 3.6 Derogación

- Cualquier ley promulgada puede derogarse.
- Dificultad de derogación = **n+1 ceros**, siempre, sin distinción de antigüedad o historial de revisiones de la ley.
- La asimetría es intencional: derogar siempre cuesta más esfuerzo colectivo que promulgar.

### 3.7 Duración de ventana

- Variable según tipo de acción: **promulgar** y **derogar** tienen duraciones de ventana distintas (valores concretos a definir como parámetros de configuración en la implementación, documentados en el README del Pilar correspondiente).

### 3.8 Membresía de red

- Descubrimiento **P2P** entre nodos y pools.
- El NCT **no gestiona membresía**, solo coordina ventanas de votación. Un nodo puede unirse o irse de la red sin que el NCT intervenga en ese proceso.

### 3.9 Pools y jerarquía

- Un nodo pool agrega la capacidad de cómputo de varios mineros y compite con esa capacidad combinada por el nonce de la ventana activa.
- Un pool es **indistinguible** de un participante individual desde la perspectiva del NCT — recibe el desafío igual que cualquier nodo, y responde con un nonce igual que cualquier nodo.
- La jerarquía es recursiva por diseño (pool-de-pools), pero la **implementación fija una profundidad de 2 niveles**: minero → pool → NCT. Se documenta en el informe que la arquitectura permite mayor profundidad, aunque no se prueba.
- Dado que solo hay una ventana activa a la vez (3.3), un pool **no fragmenta su capacidad entre leyes distintas**: toda la red, en todo momento, apunta su poder de cómputo a la ventana en curso.

---

## 4. Tolerancia a fallos del NCT (Bully mejorado)

- Si el NCT actual cae, se ejecuta una variante del algoritmo Bully: en lugar de elegir sucesor por mayor ID, **los nodos candidatos resuelven un mini-desafío de PoW**, y quien lo resuelve primero asume como nuevo NCT.
- **Candidatos:** cualquier nodo de la red puede postularse (no hay restricción a pools ni a nodos con antigüedad mínima).
- **Estado de la ventana en curso:** se pierde. No se persiste en Redis para este propósito. El nuevo NCT **siempre arranca con una ventana nueva**, incluso si había una en progreso al momento de la caída. Esto es una simplificación deliberada — el costo de cómputo ya invertido por los nodos en la ventana perdida se documenta como una limitación conocida, no se intenta mitigar.

---

## 5. Mapeo a los Pilares del TP

### Pilar 1 — Minero CUDA

Sin cambios respecto al enunciado base del TP: el minero GPU/CPU calcula hashes (MD5 para desarrollo iterativo, con SHA-256 como comparación opcional) buscando un nonce que produzca **n ceros iniciales**. La única particularidad de VoxChain es que el "string base" a hashear no es una transacción monetaria sino el contenido serializado del desafío de gobierno: `law_id + texto_hash + voting_window_id + action`.

### Pilar 2 — Infraestructura distribuida

**P1 (Validación):** el minero CUDA resuelve el desafío de gobierno (promulgar o derogar) en lugar de una transacción genérica. La dificultad (n o n+1) la define el NCT al abrir la ventana, no un ajuste dinámico por carga de red.

**P2 (RabbitMQ):** tres flujos de mensajes:

1. `propuesta → NCT`: cualquier nodo publica una ley nueva a la cola de propuestas.
2. `NCT → red (tópico)`: al abrir una ventana, el NCT publica el desafío activo (`law_id`, `n_zeros`, `deadline`, `partial_hash_base`). Todos los nodos/pools suscritos lo reciben simultáneamente.
3. `red → NCT (cola de respuesta)`: el primer nodo/pool que encuentra el nonce válido publica la solución. El NCT verifica y descarta soluciones tardías para la misma ventana.

Más dos flujos para el Bully distribuido (AGENT.md 4):

6. `NCT activo → backups (tópico, nct.heartbeat)`: heartbeat periódico del NCT primario. Los standbys suscritos detectan su ausencia.
7. `backups → backups (cola, nct_election)`: claims de la elección distribuida. Los candidatos publican su nonce solución y el primero válido en Redis gana.

**P3 (Redis — estado de la cadena):** ver esquema en sección 7.

**P4 (NCT):** responsabilidades acotadas respecto al TP base:
- Gestiona exclusivamente ventanas de votación (abrir, cerrar, verificar).
- Decide el orden de la cola (round-robin por autor).
- Verifica nonces recibidos antes del deadline.
- **No** ajusta dificultad dinámicamente por carga de red (la dificultad es fija: n para promulgar, n+1 para derogar).
- **No** arbitra contenido de las leyes.

**P5 (Pool):** rol redefinido — ya no es solo infraestructura de escalado, es una **facción política**. Subdivide el espacio de nonces de la ventana activa entre los mineros que agrega. Recibe keep-alives para conocer capacidad disponible. Dado que solo hay una ventana activa a la vez, el pool no necesita lógica de distribución entre múltiples desafíos simultáneos — toda su capacidad apunta siempre al desafío vigente.

### Pilar 3 — Despliegue y pruebas

Las métricas de carga del TP (volumen de transacciones, dificultad de prefijo, fragmentación del pool) se reinterpretan así:

- **Volumen de "transacciones"** → volumen de leyes propuestas en la cola y frecuencia de turnos.
- **Dificultad de prefijo (1 a 8 caracteres)** → mapea directo a los valores de n y n+1 del desafío de gobierno.
- **Fragmentación del pool** → cantidad de mineros agregados por pool y cómo se subdivide el rango de nonces entre ellos.
- **Ingreso/egreso de nodos GPU** → simula nodos uniéndose o abandonando la red P2P en medio de una ventana activa.

Preguntas de investigación para el informe (cualitativas, no requieren estudio estadístico exhaustivo de distribución de poder computacional — eso queda fuera de alcance):

- Tiempo de promulgación con distinta cantidad de nodos participantes.
- Diferencia de tiempo entre promulgar (n) y derogar (n+1) para la misma población de nodos.
- Comportamiento del sistema cuando un pool grande compite contra muchos mineros individuales pequeños (observación cualitativa sobre concentración de poder, no medición estadística rigurosa).
- Tiempo de recuperación tras una caída del NCT (Bully mejorado) y costo de la ventana perdida.

---

## 6. Infraestructura de soporte (fuera de los Pilares, pero justificada)

### 6.1 Vault — gestión de secretos

Responde directamente al requisito de seguridad del TP ("Zero static keys", credenciales por ambiente). En VoxChain, Vault custodia:

- Credenciales de conexión a Redis y RabbitMQ por ambiente.
- **No** custodia las claves privadas de los individuos — esas nunca salen del nodo del individuo (ver 3.1). Vault es para secretos de infraestructura, no para identidad de los participantes.

---

## 7. Esquema de datos

### 7.1 Ley (propuesta)

| Campo | Tipo | Descripción |
|---|---|---|
| `law_id` | string | Identificador único. |
| `author_pubkey` | string | Clave pública del autor. |
| `text_hash` | string | Hash SHA-256 del texto de la ley. |
| `text_ref` | string (opcional) | Referencia a MinIO si se almacena el texto completo. |
| `status` | enum | `pending_queue`, `in_window`, `promulgated`, `discarded`, `repealed`. |
| `created_at` | timestamp | Momento de la propuesta. |

### 7.2 Ventana de votación

| Campo | Tipo | Descripción |
|---|---|---|
| `voting_window_id` | string | Identificador único de la ventana. |
| `law_id` | string | Ley en disputa. |
| `action` | enum | `promulgacion` \| `derogacion`. |
| `n_zeros_required` | int | n (promulgar) o n+1 (derogar). |
| `opened_at` | timestamp | Apertura. |
| `deadline` | timestamp | Cierre. |
| `partial_hash_base` | string | Dato base que los mineros deben usar para construir el hash. |
| `result` | enum | `success` \| `expired_pending`. |
| `winning_nonce` | int (nullable) | Nonce ganador, si hubo éxito. |
| `winning_node_or_pool` | string (nullable) | Identidad de quien resolvió. |

### 7.3 Bloque (cadena en Redis)

| Campo | Descripción |
|---|---|
| `previous_hash` | Hash del bloque anterior. |
| `law_id` | Ley afectada. |
| `action` | `promulgacion` o `derogacion`. |
| `n_zeros_required` | Dificultad exigida en esa acción. |
| `nonce` | Solución encontrada. |
| `winning_node_or_pool` | Quién resolvió primero. |
| `voting_window_id` | Ventana de origen. |
| `block_hash` | Hash del bloque completo. |
| `timestamp` | Momento del sellado. |

### 7.4 Cooldown de autor

| Campo | Descripción |
|---|---|
| `author_pubkey` | Clave pública del autor. |
| `cooldown_until_window` | Número de ventana a partir de la cual puede volver a proponer. |
| `cooldown_reason` | `proposed_new` \| `reproposed_identical` (cooldown mayor). |

---

## 8. Diagrama de arquitectura

```
                            ┌──────────────────────┐
                            │     Individuos       │
                            │ (clave pública/priv.)│
                            └──────────┬───────────┘
                                       │ propone ley / vota
                                       ▼
                     ┌──────────────────────────────┐
                     │   Descubrimiento P2P         │
                     │ (nodos y pools se descubre   │
                     │  entre sí; NO vía el NCT)    │
                     └──────────────┬───────────────┘
                                    │
              ┌─────────────────────┼───────────────────────┐
              ▼                     ▼                       ▼
      ┌───────────────┐     ┌─────────────────┐     ┌────────────────┐
      │  Nodo minero  │     │   Nodo pool     │     │ Nodo pool-of-  │
      │ (CUDA/CPU)    │◄────┤ (agrega mineros)│◄────┤ pools (nivel 2)│
      └───────┬───────┘     └───────┬─────────┘     └───────┬────────┘
              │                     │                       │
              └──────────────┬──────┴───────────────────────┘
                             │ keep-alive / nonce encontrado
                             ▼
                  ┌──────────────────────────┐
                  │      RabbitMQ            │
                  │  - cola: propuestas      │
                  │  - tópico: desafío activo│
                  │  - cola: respuesta nonce │
                  └───────────┬──────────────┘
                              │
                              ▼
                  ┌──────────────────────────┐
                  │   NCT (Coordinador)      │
                  │  - cola de leyes         │
                  │    (round-robin autor)   │
                  │  - abre/cierra ventana   │
                  │  - verifica nonce        │
                  │  - Bully-por-esfuerzo si │
                  │    el NCT activo cae     │
                  └───────────┬──────────────┘
                              │ bloque verificado
                              ▼
                  ┌────────────────────────────┐
                  │        Redis               │
                  │  - cadena de bloques       │
                  │  - cooldowns por autor     │
                  │  - estado de ventana activa│
                  └───────────┬────────────────┘
                              │
                  ┌───────────┴─────────────┐
                  ▼                         ▼
          ┌─────────────────┐       ┌────────────────┐
          │     Vault       │       │  MinIO (opc.)  │
          │ (secrets infra: │       │ (texto completo│
          │  Redis/RabbitMQ │       │  de las leyes) │
          │  credentials)   │       │                │
          └─────────────────┘       └────────────────┘

  Plataforma: Kubernetes (GKE) vía OpenTofu — mínimo 2 réplicas
  por servicio. Nodegroup dedicado a infraestructura (Redis,
  RabbitMQ) + nodegroup compartido para apps + VMs externas para
  cómputo intensivo (mineros CPU escalados dinámicamente, HPA).
```

---

## 9. Limitaciones conocidas

- **Sybil:** el sistema no verifica identidad real. Un individuo puede generar múltiples claves y proponer/votar como si fuera varios. Mitigación futura (DNI) fuera de alcance.
- **Pérdida de estado en falla del NCT:** la ventana en curso se pierde íntegramente al caer el NCT; el cómputo invertido por la red hasta ese momento no se aprovecha.
- **Split-brain del NCT:** si una partición de red separa al NCT primario de los standbys sin que el primario falle realmente, ambos pueden operar como líderes simultáneamente. El primario verifica en cada tick que su liderazgo en Redis sigue vigente (`renew_leadership`), y si descubre que otro NCT adquirió el liderazgo, ejecuta `step_down()`. Esta detección no es instantánea; hay una ventana de solapamiento.
- **Concentración de poder:** el diseño favorece estructuralmente a pools grandes sobre mineros individuales, igual que las blockchains reales de PoW. No se mitiga — se documenta como observación de diseño y se discute cualitativamente en el informe, sin pretender un estudio estadístico riguroso de la distribución de poder computacional en la población (fuera de alcance del TP).

---

## 10. Convenciones para agentes de IA que trabajen en este repo

- Usar esta terminología exacta en código y commits: `law` (no "proposal" ni "bill" salvo en comentarios aclaratorios), `voting_window`, `n_zeros_required`, `NCT`, `pool`, `cooldown`.
- La dificultad es fija: `n` para promulgar, `n+1` para derogar. Está demostrado (ver sección 11) que cualquier intento de ajuste dinámico autónomo es gameable o requiere una complejidad excesiva. El ajuste se realiza externamente (operador humano o Pilar 3) con conocimiento de la población de mineros.
- No implementar verificación de identidad real (DNI, OAuth, etc.) sin discusión explícita — está documentado como fuera de alcance.
- Cualquier nuevo tipo de mensaje en RabbitMQ debe respetar los flujos descritos en la sección 5 (Pilar 2 / P2). Si se necesita un nuevo flujo, documentarlo acá antes de implementarlo.
- Las claves privadas de los individuos nunca deben persistirse en Redis, Vault, ni en ningún servicio de backend. Si código nuevo intenta hacer esto, es un error de diseño y debe rechazarse.

---

## 11. Análisis de diseño: dificultad fija vs. dinámica

### 11.1 El trilema del ajuste de dificultad

Todo sistema PoW enfrenta tres propiedades deseables y mutuamente excluyentes:

| Propiedad | Significado |
|---|---|
| **Simple** | Pocas reglas, comportamiento predecible, fácil de razonar |
| **Autónomo** | Se ajusta sin intervención externa ante cambios en la red |
| **No gameable** | Ningún actor puede manipular la dificultad en su beneficio |

Se pueden elegir **dos**:

| Opción | Simple | Autónomo | No gameable |
|---|---|---|---|
| **Fijo + operador externo** (VoxChain) | ✅ | ❌ | ✅ |
| **Autónomo + simple** (basado en comportamiento) | ✅ | ✅ | ❌ |
| **Autónomo + no gameable** (basado en tiempo real contra reloj de pared) | ❌ | ✅ | ✅ |

### 11.2 Por qué se descartó el ajuste autónomo + simple

Se consideró un mecanismo donde el NCT ajustara `n` basándose en el tiempo de resolución de ventanas exitosas (promedio móvil contra un target). El diseño propuesto era:

- Solo las ventanas con nonce encontrado alimentan el promedio.
- Si el promedio es < 50% del target y `n < MAX` → `n += 1`
- Si el promedio es > 200% del target y `n > MIN` → `n -= 1`
- Las expiraciones no cuentan (una ley que no genera consenso no debería abaratar la dificultad).

Sin embargo, se identificó que incluso esta regla es gameable:

1. Un actor con múltiples identidades Sybil propone leyes impopulares (texto basura).
2. Otros actores (coordinados) se niegan a minarlas.
3. Si se incluye una válvula de escape que reduzca `n` ante N expiraciones consecutivas, el atacante puede hacer expirar ventanas hasta bajar la dificultad.
4. Una vez baja `n`, promulga su ley real con menos esfuerzo del que debería costar.

Se exploró una válvula de escape para bootstrap y contracción de red (N expiraciones consecutivas → bajar `n`), pero se concluyó que cualquier regla basada en el comportamiento de los actores es potencialmente explotable por coordinación externa.

### 11.3 Decisión final

**Dificultad fija configurable externamente.** El valor de `n` se define al desplegar el sistema (variable de entorno `N_ZEROS`) en función del conocimiento que el operador tiene de la población de mineros. Si la población cambia significativamente, el operador (o un pipeline de Pilar 3) actualiza el valor. El algoritmo de consenso no negocia su dificultad.

Esto es consistente con la filosofía del sistema: VoxChain no pretende ser justo ni auto-regulado. Es una herramienta de gobierno donde las reglas son explícitas y no cambian solas.

### 11.4 Split-brain del NCT

El Bully distribuido (sección 4) mitiga la caída del NCT pero introduce un riesgo de split-brain si el primario no cae realmente sino que sufre una partición de red.

**Mecanismo de detección:** en cada `tick()`, el NCT primario verifica que su liderazgo en Redis sigue vigente mediante `renew_leadership()`. Si la operación falla (porque otro NCT adquirió el lock), ejecuta `step_down()`:

- `is_leader = False`
- Limpia `_active` (la ventana en curso se pierde — AGENT.md 4)
- Deja de publicar heartbeats

No hay detección de doble liderazgo más allá de Redis; la ventana de solapamiento es de hasta `HEARTBEAT_INTERVAL` segundos, aceptada como limitación conocida.
