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

### 6.2 MinIO — almacenamiento de objetos (opcional, justificar si se incluye)

No es un requisito del TP. Si se incluye, su justificación en VoxChain sería almacenar el **texto completo de las leyes** (el contenido real, no solo su hash). La transacción en la blockchain solo lleva el hash; el texto íntegro vive en MinIO y cualquiera puede verificarlo recalculando el hash. Si el tiempo de desarrollo es limitado, priorizar Vault sobre MinIO — Vault responde a un requisito explícito del TP, MinIO no.

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

## 9. Limitaciones conocidas (documentar explícitamente en el informe)

- **Sybil:** el sistema no verifica identidad real. Un individuo puede generar múltiples claves y proponer/votar como si fuera varios. Mitigación futura (DNI) fuera de alcance.
- **Pérdida de estado en falla del NCT:** la ventana en curso se pierde íntegramente al caer el NCT; el cómputo invertido por la red hasta ese momento no se aprovecha.
- **Concentración de poder:** el diseño favorece estructuralmente a pools grandes sobre mineros individuales, igual que las blockchains reales de PoW. No se mitiga — se documenta como observación de diseño y se discute cualitativamente en el informe, sin pretender un estudio estadístico riguroso de la distribución de poder computacional en la población (fuera de alcance del TP).
- **MinIO (si se implementa):** no hay garantía de que el texto en MinIO no se borre o modifique fuera de la blockchain; solo la verificación de hash por parte de terceros detecta la alteración a posteriori, no la previene.

---

## 10. Convenciones para agentes de IA que trabajen en este repo

- Usar esta terminología exacta en código y commits: `law` (no "proposal" ni "bill" salvo en comentarios aclaratorios), `voting_window`, `n_zeros_required`, `NCT`, `pool`, `cooldown`.
- No introducir ajuste dinámico de dificultad por carga de red — es una decisión de diseño explícita que la dificultad sea fija (n / n+1). Si se sugiere una optimización en esa línea, marcarla como pregunta abierta para el equipo, no implementarla directamente.
- No implementar verificación de identidad real (DNI, OAuth, etc.) sin discusión explícita — está documentado como fuera de alcance.
- Cualquier nuevo tipo de mensaje en RabbitMQ debe respetar los tres flujos descritos en la sección 5 (Pilar 2 / P2). Si se necesita un cuarto flujo, documentarlo acá antes de implementarlo.
- Las claves privadas de los individuos nunca deben persistirse en Redis, Vault, ni en ningún servicio de backend. Si código nuevo intenta hacer esto, es un error de diseño y debe rechazarse.
