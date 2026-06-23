# CONTEXTO DEL PROYECTO - VoxChain

**Este documento es una guía introductoria para entender el proyecto VoxChain desde cero.**

---

## ¿Qué es VoxChain?

VoxChain es una **blockchain distribuida de gobierno por consenso computacional**. A diferencia de blockchains tradicionales como Bitcoin (que gobiernan dinero), VoxChain permite que cualquier persona con un par de claves criptográficas proponga, promulgue o derogue **leyes**. El consenso no se logra por votos nominales, sino por **esfuerzo computacional** (Proof of Work).

### Analogía Simple

Imagina una democracia donde:
- Cualquier ciudadano puede proponer una ley
- Para que una ley se apruebe, los ciudadanos deben resolver un problema matemático complejo
- El primero en resolverlo "sella" la ley en un libro inmutable
- Todos los ciudadanos tienen una copia de este libro
- Nadie puede borrar o modificar leyes ya aprobadas

Eso es VoxChain, pero implementado con tecnología blockchain distribuida.

---

## Arquitectura General del Sistema

VoxChain está organizado en **3 pilares** que representan el progreso del desarrollo:

```
┌─────────────────────────────────────────────────────────────┐
│                    PILAR 1: Minería                         │
│              (CPU y GPU con CUDA)                           │
│  Desarrollar el motor de cómputo para resolver PoW          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│              PILAR 2: Infraestructura Distribuida           │
│         (RabbitMQ, Redis, NCT, Workers, API)                │
│  Conectar componentes en un sistema distribuido escalable   │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│               PILAR 3: Despliegue en la Nube                │
│         (GKE, k3s, Terraform, CI/CD, Monitoreo)             │
│  Desplegar en producción con autoescalado y observabilidad  │
└─────────────────────────────────────────────────────────────┘
```

---

## Estructura de Directorios

### Raíz del Proyecto

```
TPIntegrador_SDyPP/
├── pilar1-minero/           # Motor de minería (CPU + GPU CUDA)
├── pilar2-distribuido/      # Sistema distribuido completo
├── pilar3-despliegue/       # Despliegue en nube y pruebas
├── docs/                    # Documentación adicional
├── .github/                 # Workflows de GitHub Actions
├── AGENT.md                 # Especificación del agente VoxChain
├── DOC.md                   # Documentación académica completa
├── README.md                # Descripción breve del proyecto
└── INSTRUCCIONES.md         # Guía de pruebas
```

---

## PILAR 1: Minería CPU y GPU CUDA

### Propósito
Desarrollar el motor computacional que resuelve el problema de Proof of Work (PoW). Este es el corazón de la blockchain: sin él, no hay consenso.

### Concepto Clave: Proof of Work (PoW)
Para que una ley se apruebe, alguien debe encontrar un número (nonce) tal que:
```
MD5(texto_de_la_ley + nonce) empiece con N ceros
```

Encontrar este nonce requiere probar millones de combinaciones. Es computacionalmente costoso, lo que hace que el consenso sea valioso.

### Estructura del Directorio

```
pilar1-minero/
├── cpu/                     # Implementación en Python (baseline)
│   └── src/
│       └── brute_force.py  # Minería por fuerza bruta en CPU
├── gpu/                     # Implementación en CUDA C/C++ (optimizado)
│   ├── include/             # Kernels reutilizables
│   ├── 01_hello.cu          # Hello World CUDA
│   ├── 02_thrust_vector.cu  # Uso de Thrust (librería NVIDIA)
│   ├── 03_md5_hash.cu       # Cálculo de MD5 en GPU
│   ├── 04_brute_force.cu    # Fuerza bruta para encontrar nonce
│   ├── 05_prefix_bench.cu   # Benchmarks de diferentes prefijos
│   ├── 06_brute_force_range.cu  # Fuerza bruta con límites de rango
│   └── Makefile             # Compilación de programas CUDA
└── benchmarks/              # Comparativas CPU vs GPU
```

### Rol de Cada Componente

| Componente | Rol | Por qué existe |
|------------|-----|----------------|
| `cpu/src/brute_force.py` | Minería en CPU | Baseline para comparar rendimiento |
| `gpu/*.cu` | Minería en GPU | Versión optimizada (100x más rápida) |
| `benchmarks/` | Comparativas | Demostrar ventaja de GPU sobre CPU |

### Hits de Desarrollo (Ejercicios Progresivos)

El pilar 1 se desarrolló en 7 "hits" (ejercicios):

1. **Hit #2**: Hello World CUDA - Aprender a programar en GPU
2. **Hit #3**: Thrust Vectors - Usar librerías de alto nivel de NVIDIA
3. **Hit #4**: MD5 Hash - Calcular hash de un string en GPU
4. **Hit #5**: Fuerza Bruta - Encontrar nonce dado un hash y prefijo
5. **Hit #6**: Prefix Bench - Medir rendimiento vs longitud de prefijo
6. **Hit #7**: Rango Limitado - Buscar nonce dentro de un rango específico

### Por qué CUDA?
CUDA es la tecnología de NVIDIA para programar GPUs. Las GPUs son ideales para minería porque:
- Tienen miles de núcleos (vs 8-16 en CPU)
- Están diseñadas para procesamiento paralelo masivo
- Pueden probar millones de hashes por segundo

---

## PILAR 2: Infraestructura Distribuida

### Propósito
Construir el sistema distribuido que coordina múltiples mineros trabajando en paralelo. Aquí es donde la blockchain se vuelve realmente distribuida.

### Concepto Clave: Arquitectura de Servicios

VoxChain no es un monolito: está compuesto por múltiples servicios que se comunican mediante colas de mensajes.

### Estructura del Directorio

```
pilar2-distribuido/
├── common/                  # Código compartido entre servicios
│   ├── blockchain/          # PoW (challenge.py), bloques, cadena, compresión
│   ├── identity/            # Firma Ed25519 (signing.py)
│   ├── messaging/           # Abstracción de RabbitMQ (base.py, rabbitmq.py)
│   ├── storage/             # Abstracción de Redis (redis_store.py → VoxChainStore)
│   ├── config.py            # Configuración centralizada (variables de entorno)
│   ├── health.py            # Servidor HTTP de health check
│   ├── logging_setup.py     # Logs estructurados en JSON
│   └── metrics.py           # Métricas Prometheus (contadores, gauges)
├── nct-coordinator/         # Nodo Coordinador de Tareas (NCT)
│   ├── nct/
│   │   ├── coordinator.py   # Lógica principal: ventanas, nonces, cadena
│   │   ├── monitor.py       # Monitor de heartbeat y failover por lease Redis
│   │   └── queue_logic.py   # Round-robin de autores y cola de leyes
│   ├── main.py              # Punto de entrada
│   ├── Dockerfile           # Imagen Docker
│   └── tests/               # Pruebas unitarias
├── worker/                  # Workers de minería
│   ├── worker_pkg/
│   │   ├── standalone_worker.py  # Worker independiente (mina rango completo)
│   │   ├── miner.py              # Puente al binario Pilar 1 (GPU CUDA / CPU)
│   │   ├── pool_coordinator/     # Pool Coordinator (agrega miners vía HTTP)
│   │   │   ├── coordinator.py    # Lógica: fragmenta, distribuye, auto-mina
│   │   │   └── election.py       # Elección Bully por PoW + Redis NX
│   │   ├── pool_worker.py        # Pool Miner (cliente HTTP del coordinator)
│   │   └── admin_server.py       # HTTP server :9001 del Pool Coordinator
│   ├── main.py              # Punto de entrada
│   ├── Dockerfile           # Imagen Docker
│   └── tests/               # Pruebas unitarias
├── voxchain_api/            # API REST del sistema
│   ├── routers/             # Endpoints: /laws /chain /windows /workers /health
│   ├── services/            # rabbitmq_publisher.py, redis_reader.py
│   ├── models.py            # Modelos Pydantic
│   ├── main.py              # Punto de entrada (FastAPI)
│   └── Dockerfile           # Imagen Docker
├── voxchain-frontend/       # Frontend web (Angular)
│   ├── src/                 # Código fuente Angular
│   └── Dockerfile           # Imagen Docker
├── tests/                   # Pruebas de integración
│   └── test_e2e.py          # Test extremo a extremo
├── docker-compose.yml       # Orquestación local
├── pytest.ini               # Configuración de pytest
└── conftest.py              # Fixtures compartidas de tests
```

### Rol de Cada Servicio

#### 1. NCT Coordinator (Nodo Coordinador de Tareas)
**Rol:** Es el "cerebro" del sistema. Coordina todo el proceso de aprobación de leyes.

**Responsabilidades:**
- Recibir propuestas de leyes
- Abrir ventanas de votación
- Definir la dificultad del PoW (número de ceros requeridos)
- Verificar que el nonce encontrado es válido
- Sellar el bloque en Redis
- Publicar heartbeats para tolerancia a fallos

**Analogía:** Es como el presidente del parlamento que organiza las votaciones.

#### 2. Worker Standalone
**Rol:** Minero independiente que resuelve el PoW por cuenta propia.

**Responsabilidades:**
- Se suscribe al topic `desafio_activo` (fan-out de RabbitMQ)
- Mina el **rango completo** de nonces [0, NONCE_SPACE) con el motor de Pilar 1
- Si tiene GPU, usa CUDA; si no, hace fallback automático a CPU
- Publica el nonce encontrado a la cola `respuesta_nonce`

**Analogía:** Es un ciudadano que trabaja solo para resolver el problema matemático.

#### 3. Pool Coordinator
**Rol:** Agrega varios mineros bajo un mismo coordinador, como una "facción política".

**Responsabilidades:**
- Se suscribe al topic `desafio_activo` igual que un worker standalone
- **Fragmenta internamente** el espacio de nonces en tramos de `FRAGMENT_SIZE`
- Distribuye fragmentos a sus Pool Miners vía HTTP (puerto :9001)
- También mina un fragmento propio en paralelo (auto-miner)
- Publica el nonce ganador a `respuesta_nonce` en nombre del pool
- Realiza una **elección Bully por PoW** cuando el coordinador líder cae (ver §8.8 de FUNCIONAMIENTO.md)

**Analogía:** Es un partido político con un líder que coordina a sus militantes.

#### 4. Pool Miner
**Rol:** Minero que trabaja dentro de un pool, conectado al Pool Coordinator por HTTP.

**Responsabilidades:**
- Se registra en el Pool Coordinator (`POST /register`)
- Envía heartbeats periódicos para no ser expulsado (`POST /heartbeat`)
- Pide fragmentos de trabajo (`GET /work/next`) y los mina con Pilar 1
- Devuelve el nonce encontrado (`POST /work/result`)

**Analogía:** Es el militante del partido que ejecuta la tarea que le asigna el líder.

#### 5. voxchain-api
**Rol:** Expone una interfaz HTTP para interactuar con el sistema.

**Responsabilidades:**
- Endpoint para proponer leyes
- Endpoint para consultar el estado de la blockchain
- Endpoint para consultar leyes específicas
- Agrega health checks de otros servicios

**Analogía:** Es como el mostrador de atención al público del gobierno.

#### 6. voxchain-frontend
**Rol:** Interfaz gráfica para usuarios finales.

**Responsabilidades:**
- Formulario para proponer leyes
- Visualización de la blockchain
- Dashboard de estado del sistema

**Analogía:** Es como el sitio web del gobierno donde los ciudadanos tramitan cosas.

#### 7. common/
**Rol:** Código compartido para evitar duplicación.

**Contenido:**
- `blockchain/`: PoW (MD5 + prefijo de n ceros), bloques, cadena, compresión de texto
- `storage/`: Abstracción de Redis — `VoxChainStore` (permite usar fakeredis en tests)
- `messaging/`: Abstracción de RabbitMQ — `Messaging` / `InMemoryBus` (para tests)
- `identity/`: Firma y verificación Ed25519 (opcional, configurable)
- `health.py`: Servidor HTTP de health check
- `logging_setup.py`: Logs estructurados JSON compatibles con Prometheus/Grafana
- `metrics.py`: Contadores y gauges exportados como métricas Prometheus
- `config.py`: Lectura centralizada de variables de entorno

### Flujo de Mensajes (RabbitMQ)

El sistema usa RabbitMQ como bus de mensajes. Hay **4 flujos activos**:

| # | Canal | Tipo | De → A | Contenido |
|---|---|---|---|---|
| 1 | `propuestas` | **cola** | API/nodo → NCT | Propuesta de ley (`law_id`, `author_pubkey`, `text_hash`, `action`, texto comprimido) |
| 2 | `desafio_activo` | **topic (fan-out)** | NCT → toda la red | Desafío de la ventana abierta (`voting_window_id`, `n_zeros_required`, `deadline`, `partial_hash_base`) |
| 3 | `respuesta_nonce` | **cola** | Workers/Pools → NCT | Nonce encontrado (`voting_window_id`, `nonce`, `winning_node_or_pool`) |
| 4 | `nct.heartbeat` | **topic (fan-out)** | NCT líder → followers | Latido periódico del líder (`nct_id`, `ts`) |

> **Eliminados:** `tareas_trp`, `keepalive_trp` (del Transaction Pool) y `nct_election`
> (del Bully clásico). La fragmentación la hace el Pool Coordinator internamente vía HTTP.
> El failover del NCT usa Redis directamente, sin mensajes de elección.

### Almacenamiento (Redis)

Redis es la base de datos y árbitro del sistema. Claves principales:

| Clave | Estructura | Contenido |
|---|---|---|
| `law:<id>` | hash | Ley: autor, `text_hash`, `status`, `action`, texto comprimido |
| `window:<id>` | hash | Ventana de votación: ley, acción, `n_zeros`, `deadline`, resultado, ganador |
| `chain` | lista | Bloques en orden (historia de la blockchain) |
| `law_queue` | lista | Leyes `pending_queue` esperando turno |
| `active_window` | string | `voting_window_id` vigente (solo uno a la vez) |
| `window_counter` | contador | Número monótono de ventanas (base del cooldown) |
| `window_sealed:<id>` | string (NX, TTL) | **Guard atómico de cierre**: el primer nonce válido lo escribe con SETNX |
| `cooldown:<pubkey>` | hash | Hasta qué ventana el autor no puede proponer |
| `discarded_text_hashes` | set | Hashes de textos descartados (detecta reproposición idéntica) |
| `nct:leader` | string (TTL) | **Lease de liderazgo del NCT** — árbitro del failover |
| `nct:last_author` | string | Último autor que entró a ventana (para round-robin) |
| `pool:leader` | string (TTL) | **Lease del Pool Coordinator** activo |
| `pool:election:<epoch>` | string (NX, TTL) | **Claim atómico** de la elección del pool (SET NX) |

### Ejecución Local

```bash
cd pilar2-distribuido
docker compose up --build
```

Esto levanta todos los servicios localmente en contenedores Docker.

---

## PILAR 3: Despliegue en la Nube

### Propósito
Llevar el sistema a producción con infraestructura escalable, autoescalado y observabilidad.

### Concepto Clave: Arquitectura Híbrida Multi-Cluster

El sistema se despliega en dos clusters separados:

1. **GKE (Google Kubernetes Engine)**: Servicios principales (NCT primary + standby, API, Frontend, Redis, RabbitMQ)
2. **k3s (Cluster GPU)**: Workers standalone + Pool Coordinator + Pool Miners con GPUs

Esta separación permite escalar workers independientemente del resto del sistema.

### Estructura del Directorio

```
pilar3-despliegue/
├── kubernetes/              # Manifiestos de Kubernetes
│   ├── namespace.yaml       # Namespace voxchain
│   ├── infrastructure/      # Redis, RabbitMQ, Secrets
│   ├── applications/        # NCT, API, Frontend
│   ├── hpa/                 # Horizontal Pod Autoscalers
│   ├── monitoring/          # Prometheus, Grafana, ServiceMonitors
│   ├── gpu-cluster/         # Workers en k3s
│   │   ├── worker-deployment.yaml
│   │   ├── worker-hpa.yaml
│   │   └── worker-scaledobject.yaml
│   └── scripts/
│       └── generate-certs.sh # Generación de certificados TLS
├── terraform/               # Infraestructura como código
│   └── gke/
│       ├── main.tf          # Configuración de GKE
│       ├── variables.tf     # Variables
│       └── terraform.tfvars # Valores específicos
├── load-tests/              # Pruebas de carga
│   └── scenarios/
│       ├── test_bulk.py     # Pruebas de volumen
│       ├── test_difficulty.py  # Pruebas de dificultad
│       ├── test_fragmentation.py  # Pruebas de fragmentación
│       └── run_all.sh       # Ejecutar todos los escenarios
├── certs/                   # Certificados TLS autofirmados
├── .secrets/                # Ejemplos de secrets (SOPS)
└── README.md                # Guía de despliegue
```

### Rol de Cada Componente

#### 1. Terraform (Infraestructura como Código)
**Rol:** Crear y gestionar la infraestructura de GCP de manera reproducible.

**Crea:**
- VPC (red virtual)
- Cluster GKE regional
- Nodepools (infra y apps)
- Artifact Registry (para imágenes Docker)
- Service Accounts y Workload Identity
- kube-prometheus-stack

**Por qué Terraform?**
- Reproducibilidad: Mismo comando = misma infraestructura
- Versionado: La infraestructura está en Git
- Seguridad: Sin clicks en consola, todo es código

#### 2. Kubernetes Manifests
**Rol:** Definir cómo se despliegan los servicios en GKE.

**Componentes:**
- Deployments: Cómo se ejecutan los pods
- Services: Cómo se exponen los servicios
- ConfigMaps: Configuración sin secrets
- Secrets: Credenciales y certificados
- Ingress: Balanceador de carga externo
- HPA: Autoescalado por CPU
- ServiceMonitors: Configuración de Prometheus

#### 3. GPU Cluster (k3s)
**Rol:** Cluster ligero para workers con GPUs.

**Por qué separado?**
- Los workers necesitan GPUs (caras)
- Se pueden escalar independientemente
- Se pueden apagar cuando no hay carga

**Componentes:**
- KEDA: Event-driven autoscaling (por profundidad de cola)
- HPA: Autoscaling por CPU
- Certificados TLS: Para conectar a RabbitMQ en GKE

#### 4. Load Tests
**Rol:** Probar el sistema bajo diferentes condiciones de carga.

**Escenarios:**
- **Bulk**: 1 a 100,000 transacciones
- **Dificultad**: Prefijos de 1 a 8 ceros
- **Fragmentación**: Tamaños de 1% a 50%

**Por qué?**
- Medir escalabilidad
- Encontrar cuellos de botella
- Generar gráficos para el informe

#### 5. CI/CD (GitHub Actions)
**Rol:** Automatizar build, test y deploy.

**Workflows:**
- `ci-checks`: Gitleaks + pytest en cada PR
- `01-infra`: Terraform apply (manual)
- `02-services`: Deploy de Redis/RabbitMQ
- `03-apps`: Build y deploy de aplicaciones
- `04-gpu-workers`: Deploy de workers en k3s

**Por qué?**
- Sin errores humanos
- Despliegues consistentes
- Rollback automático

#### 6. Monitoreo (Prometheus + Grafana)
**Rol:** Observabilidad del sistema en producción.

**Métricas:**
- Propuestas por segundo
- Bloques sellados por minuto
- Latencia de minería
- Número de workers activos
- Profundidad de colas RabbitMQ
- Latencia de Redis

**Dashboards:**
- VoxChain Overview
- RabbitMQ Metrics
- Redis Metrics
- Worker Performance

---

## Conceptos Técnicos Importantes

### 1. Blockchain
Una base de datos distribuida donde cada bloque contiene:
- Datos (transacciones/leyes)
- Hash del bloque anterior (encadenamiento)
- Nonce (prueba de trabajo)
- Timestamp

**Propiedad clave:** Inmutabilidad. Si cambias un bloque, rompes el encadenamiento.

### 2. Proof of Work (PoW)
Mecanismo de consenso que requiere esfuerzo computacional.

**En VoxChain:**
```
MD5(texto_ley + nonce) debe empezar con N ceros
```

**Por qué?**
- Dificulta ataques Sybil (crear identidades falsas)
- Hace que el consenso sea costoso (y por lo tanto valioso)
- Permite medir "esfuerzo" en lugar de "votos"

### 3. RabbitMQ
Sistema de colas de mensajes (message broker).

**Por qué?**
- Desacopla servicios
- Permite procesamiento asíncrono
- Escala horizontalmente
- Tolerancia a fallos

**Patrón usado:** Publish/Subscribe con exchanges topic.

### 4. Redis
Base de datos en memoria con persistencia.

**Por qué?**
- Ultra rápido (microsegundos)
- Soporta estructuras de datos complejas
- Persistencia a disco (AOF)
- Pub/Sub nativo

### 5. Kubernetes
Orquestador de contenedores.

**Por qué?**
- Autoescalado
- Self-healing (reinicia pods caídos)
- Rolling updates (actualizaciones sin downtime)
- Abstracción de infraestructura

### 6. Docker
Contenedorización de aplicaciones.

**Por qué?**
- "Build once, run anywhere"
- Aislamiento de dependencias
- Reproducibilidad
- Eficiencia vs VMs

### 7. CUDA
Plataforma de computación paralela en GPU de NVIDIA.

**Por qué?**
- Miles de núcleos vs decenas en CPU
- Ideal para tareas paralelas (hashing)
- 100x más rápido que CPU para PoW

### 8. Terraform
Infraestructura como código (IaC).

**Por qué?**
- Reproducibilidad
- Versionado
- Seguridad (sin clicks en consola)
- Previsibilidad

### 9. KEDA
Kubernetes Event-driven Autoscaling.

**Por qué?**
- Escala por eventos (profundidad de cola)
- Más eficiente que HPA por CPU
- Ideal para workers de colas

### 10. Workload Identity
Autenticación sin claves estáticas.

**Por qué?**
- Seguridad (no hay keys que robar)
- Rotación automática
- Zero-trust

---

## Flujo Completo de una Ley

### Paso 1: Propuesta
```
Ciudadano → voxchain-api → RabbitMQ (cola propuestas) → NCT
```

### Paso 2: Apertura de Ventana
```
NCT valida propuesta → Abre ventana de votación → Publica desafío en RabbitMQ (topic desafio_activo)
```

### Paso 3: Minería distribuida
```
Worker standalone: consume desafio_activo [AMQPS/TLS] → mina rango completo [0, NONCE_SPACE) → publica respuesta_nonce

Pool Coordinator: consume desafio_activo [AMQPS/TLS]
  → fragmenta internamente en tramos de FRAGMENT_SIZE
  → distribuye a Pool Miners vía HTTP (:9001)
  → auto-mina un fragmento en paralelo
  → el primero en encontrar el nonce lo publica en respuesta_nonce
```

### Paso 4: Verificación y Sellado
```
NCT recibe nonce → Verifica que es válido → Sella bloque en Redis → Cierra ventana
```

### Paso 5: Encadenamiento
```
Bloque nuevo referencia hash del bloque anterior → Cadena se valida de punta a punta
```

---

## Decisiones de Diseño Importantes

### 1. Bolsa de Tareas vs Asignación Directa
**Decisión:** Usar bolsa de tareas (todos los fragmentos en una cola, workers compiten por consumir).

**Por qué:**
- Capacidad emerge naturalmente
- Más workers = más throughput
- Keep-alives para observabilidad, no para asignación

### 2. Dificultad Fija
**Decisión:** No ajustar dificultad dinámicamente por carga.

**Por qué:**
- AGENT.md lo prohíbe
- Rompería el consenso
- Si no hay GPU, se escala CPU (Pilar 3)

### 3. Una Sola Ventana Activa
**Decisión:** El NCT no abre una nueva ventana hasta cerrar la anterior.

**Por qué:**
- Simplifica el estado
- Evita condiciones de carrera
- Más fácil de validar

### 4. Cierre Atómico
**Decisión:** El primer nonce válido cierra la ventana mediante un guard atómico en Redis.

**Por qué:**
- Evita sobrescritura
- Tolerancia a fallos (guard en Redis, no en memoria)
- Desempate por orden de llegada

### 5. Texto Comprimido Inline
**Decisión:** El texto de la ley viaja comprimido en el mensaje, no en MinIO.

**Por qué:**
- Evita dependencia de MinIO en camino crítico
- `text_hash` sigue siendo identidad canónica
- MinIO queda opción para textos grandes

### 6. Round-Robin por Autor
**Decisión:** Un autor no encadena turnos consecutivos si hay leyes de otros.

**Por qué:**
- Evita concentración de poder
- Más democrático
- Especificado en AGENT.md

### 7. Núcleo Agnóstico del Transporte
**Decisión:** Servicios reciben abstracciones (Messaging, Storage), no RabbitMQ/Redis directamente.

**Por qué:**
- Mismo código en producción y tests
- Tests usan bus en memoria + fakeredis
- Mejor testabilidad

---

## Vulnerabilidades por Diseño (No Bugs)

El proyecto documenta vulnerabilidades que son **por diseño**, no errores:

### 1. Ataque del 51%
Si alguien controla más del 51% del poder de minado, puede reescribir la historia.

**Por qué no se soluciona:**
- Es una limitación conocida de PoW
- Requiere inversión masiva
- Afecta a todas las blockchains PoW

### 2. Ataque Sybil
Alguien puede crear miles de identidades falsas.

**Por qué no se soluciona:**
- PoW lo hace costoso
- Requiere poder computacional por identidad
- Es un trade-off aceptable

### 3. Concentración en Pools
Si un pool tiene mucho poder, puede influir en el consenso.

**Por qué no se soluciona:**
- Es un problema socioeconómico, no técnico
- Requiere incentivos diferentes
- Documentado en AGENT.md

---

## Tecnologías Utilizadas

| Categoría | Tecnología | Propósito |
|-----------|-----------|-----------|
| **Lenguajes** | Python | Servicios (NCT, Workers, Pool Coordinator, Pool Miner, API) |
| | CUDA C/C++ | Minería GPU |
| | JavaScript/TypeScript | Frontend |
| **Message Broker** | RabbitMQ | Comunicación asíncrona |
| **Base de Datos** | Redis | Almacenamiento de estado |
| **Contenedores** | Docker | Empaquetado de aplicaciones |
| **Orquestación** | Kubernetes | Gestión de contenedores |
| **IaC** | OpenTofu (Terraform) | Infraestructura como código |
| **Cloud** | Google Cloud Platform | Proveedor de nube |
| **CI/CD** | GitHub Actions | Automatización de pipelines |
| **Monitoreo** | Prometheus | Recolección de métricas |
| | Grafana | Visualización de métricas |
| **Autoscaling** | HPA | Escalado por CPU |
| | KEDA | Escalado por eventos |
| **Seguridad** | Workload Identity | Autenticación sin keys |
| | TLS | Comunicación segura |
| **Testing** | pytest | Pruebas unitarias/integración |
| | fakeredis | Mock de Redis para tests |

---

## Métricas de Éxito del Proyecto

### Funcionales
- ✅ Minería GPU funciona (100x más rápido que CPU)
- ✅ Sistema distribuido coordina múltiples workers
- ✅ Blockchain mantiene integridad y encadenamiento
- ✅ Despliegue en nube funciona y escala
- ✅ CI/CD automatiza build y deploy

### No Funcionales
- ✅ Tolerancia a fallos (NCT standby, elección de líder)
- ✅ Autoescalado (HPA + KEDA)
- ✅ Observabilidad (Prometheus + Grafana)
- ✅ Seguridad (TLS, Workload Identity, Gitleaks)
- ✅ Reproducibilidad (Terraform, Docker)

### Académicos
- ✅ Aplica U4.3-U4.5 (Contenedores, Cloud)
- ✅ Aplica U5.1-U5.6 (DevOps, CI/CD, Observabilidad, IaC)
- ✅ Aplica U6.1-U6.5 (Computación paralela, GPU)
- ✅ Aplica U7.5-U7.7 (Esquemas paralelos, CUDA)

---

## Cómo Explicar el Proyecto en una Presentación

### Estructura Sugerida

1. **Introducción (5 min)**
   - ¿Qué es VoxChain?
   - Analogía con democracia tradicional
   - Por qué blockchain para gobierno

2. **Arquitectura General (10 min)**
   - Diagrama de los 3 pilares
   - Explicación de cada pilar
   - Cómo se conectan

3. **Pilar 1: Minería (10 min)**
   - Concepto de Proof of Work
   - CPU vs GPU (demo con benchmarks)
   - Hits de desarrollo

4. **Pilar 2: Infraestructura Distribuida (15 min)**
   - Arquitectura de microservicios
   - Rol de cada servicio (NCT, Workers standalone, Pool Coordinator)
   - Flujo de mensajes (RabbitMQ)
   - Demo local con docker compose

5. **Pilar 3: Despliegue en Nube (10 min)**
   - Arquitectura híbrida (GKE + k3s)
   - Terraform y Kubernetes
   - CI/CD con GitHub Actions
   - Monitoreo con Prometheus/Grafana

6. **Resultados y Conclusiones (5 min)**
   - Métricas de rendimiento
   - Gráficos de pruebas de carga
   - Lecciones aprendidas

### Tips para la Presentación

- **Usa analogías:** Comparar con gobierno tradicional ayuda a entender
- **Muestra código:** Un ejemplo de CUDA o de un servicio Python
- **Demo en vivo:** Si es posible, mostrar docker compose corriendo
- **Diagramas:** La arquitectura es compleja, visualízala
- **Enfócate en el "por qué":** No solo qué tecnología, sino por qué se eligió
- **Sé honesto sobre limitaciones:** Documenta vulnerabilidades por diseño

---

## Preguntas Frecuentes

### ¿Por qué MD5 y no SHA-256?
MD5 es más rápido para pruebas educativas. SHA-256 se usa en blockchains reales por seguridad, pero es más lento. El proyecto menciona esto como ejercicio opcional.

### ¿Por qué RabbitMQ y no Kafka?
RabbitMQ es más simple para el patrón request/response usado. Kafka sería overkill para este caso de uso.

### ¿Por qué Redis y no PostgreSQL?
Redis es más rápido para el patrón de acceso del proyecto (clave-valor simple). PostgreSQL sería necesario para consultas complejas.

### ¿Por qué dos clusters (GKE + k3s)?
Para escalar workers independientemente. Las GPUs son caras, y no siempre se necesitan. k3s es más ligero que GKE.

### ¿Por qué OpenTofu y no Terraform?
OpenTofu es el fork open-source de Terraform después de cambios de licencia. Es funcionalmente idéntico pero más libre.

### ¿Qué pasa si el NCT falla?
Hay un NCT standby que monitorea el topic `nct.heartbeat`. Si el líder deja de emitir heartbeats por más de `HEARTBEAT_TIMEOUT` (≈12 s), el monitor del standby intenta adquirir el **lease Redis** `nct:leader` directamente (`elect_acquire_leadership`). Si el TTL del lease es ≤ `dead_threshold` (6 s), el standby lo adquiere y se promueve a líder. No hay elección por mensajes ni algoritmo Bully: el árbitro es Redis, no una ronda de mensajes.

### ¿Cómo se previene que alguien proponga la misma ley dos veces?
Por `text_hash`. Si el hash ya existe, se aplica un cooldown mayor. Es una forma de detectar reproposición.

### ¿Por qué el texto va comprimido en el mensaje?
Para evitar depender de MinIO en el camino crítico. MinIO queda como opción para textos muy grandes.

---

## Referencias para Profundizar

- **AGENT.md**: Especificación completa del agente VoxChain (normativo)
- **DOC.md**: Documentación académica con referencias bibliográficas
- **INSTRUCCIONES.md**: Guía de pruebas paso a paso
- **README de cada pilar**: Documentación específica de cada componente
- **Código fuente**: La mejor documentación es el código mismo

---

## Resumen Ejecutivo

VoxChain es un sistema de blockchain distribuida para gobierno por consenso computacional. Está organizado en 3 pilares:

1. **Pilar 1**: Motor de minería CPU/GPU CUDA para resolver Proof of Work
2. **Pilar 2**: Infraestructura distribuida con RabbitMQ, Redis, NCT (primary + standby), Workers standalone, Pool Coordinator + Pool Miners, API y Frontend
3. **Pilar 3**: Despliegue en nube con GKE + k3s, OpenTofu/Terraform, CI/CD y monitoreo

El sistema permite que cualquier persona proponga leyes, y el consenso se logra mediante esfuerzo computacional (PoW) en lugar de votos nominales. Es una aplicación práctica de conceptos de sistemas distribuidos, computación paralela, DevOps y cloud computing.
