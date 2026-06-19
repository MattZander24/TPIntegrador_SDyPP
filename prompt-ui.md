## Prompt para agente de IA en IDE

---

```
# VoxChain Frontend — Prompt de implementación para agente de IA

## Contexto del proyecto

VoxChain es una blockchain de gobernanza distribuida (no monetaria). Los
participantes proponen, promulgan y derogan **leyes** mediante Proof of Work.
El backend ya está implementado y corre en Docker Compose.

Lee los siguientes archivos antes de escribir cualquier código:
- `AGENT.md` — fuente de verdad del dominio (reglas de negocio, glosario,
  esquema de datos, flujos)
- `DOC.md` — requisitos del TP
- `pilar2-distribuido/README.md` — arquitectura del backend
- `pilar2-distribuido/docker-compose.yml` — servicios existentes
- `pilar2-distribuido/common/storage/redis_store.py` — esquema exacto de
  claves Redis y estructuras de datos
- `pilar2-distribuido/common/blockchain/challenge.py` — lógica del desafío
- `pilar2-distribuido/scripts/propose_law.py` — referencia de cómo se
  publica una propuesta al sistema

---

## Lo que debes construir

### 1. API Gateway — nuevo servicio `voxchain-api`

Ubicación: `pilar2-distribuido/voxchain-api/`

Tecnología: Python 3.11, FastAPI, pika (RabbitMQ), redis-py, uvicorn.

El servicio lee estado desde Redis y publica acciones a RabbitMQ.
No reimplementa lógica de dominio — solo expone lo que ya existe.

#### Estructura de archivos

```
pilar2-distribuido/voxchain-api/
  main.py
  routers/
    chain.py
    laws.py
    windows.py
    health.py
  services/
    redis_reader.py     # lectura de estado desde Redis
    rabbitmq_publisher.py  # publicación a colas RabbitMQ
  models.py             # Pydantic response models
  config.py             # variables de entorno
  requirements.txt
  Dockerfile
```

#### Endpoints requeridos

**Chain**
- `GET /api/chain` — lista de bloques en orden, con todos sus campos
  (ver esquema 7.3 de AGENT.md y Block en redis_store.py)
- `GET /api/chain/{block_hash}` — bloque individual

**Laws**
- `GET /api/laws` — todas las leyes; soporta query param `?status=`
  (valores: pending_queue, in_window, promulgated, discarded, repealed)
- `GET /api/laws/{law_id}` — ley individual con todos sus campos
- `POST /api/laws` — propone una ley nueva; publica a la cola `propuestas`
  de RabbitMQ. Body:
  ```json
  {
    "law_id": "string (opcional, se genera uuid si no viene)",
    "author_pubkey": "string (requerido)",
    "text": "string (requerido, se hashea con sha256 y se comprime)",
    "action": "promulgacion | derogacion (default: promulgacion)"
  }
  ```
  La API debe replicar exactamente la lógica de
  `pilar2-distribuido/scripts/propose_law.py`: calcular sha256 del texto,
  comprimir con `common.blockchain.compression.compress_text`, generar
  law_id si no viene, y publicar a RabbitMQ.

**Windows**
- `GET /api/windows/active` — ventana activa actual (o 404 si no hay)
- `GET /api/windows/{voting_window_id}` — ventana por id

**Health**
- `GET /api/health` — agrega los health checks de NCT (:8081), TrP (:8082)
  y Redis, retorna JSON unificado

**SSE — Server-Sent Events**
- `GET /api/events` — stream SSE que emite eventos cuando cambia el estado.
  Implementar con polling interno cada 2 segundos sobre Redis. Eventos:
  - `block_added` — cuando `chain_length` aumenta, emite el nuevo bloque
  - `window_opened` — cuando `active_window` cambia a un valor nuevo
  - `window_closed` — cuando `active_window` pasa a null
  - `law_updated` — cuando el status de alguna ley cambia

#### CORS

Habilitar CORS para `http://localhost:4200` (Angular dev server).

#### Variables de entorno

```
REDIS_URL=redis://redis:6379/0
RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/
NCT_HEALTH_URL=http://coordinator:8080/health
TRP_HEALTH_URL=http://transaction-pool:8080/health
PORT=8000
```

#### Dockerfile

Mismo patrón que los otros servicios del repo (ver
`pilar2-distribuido/nct-coordinator/Dockerfile`). Contexto de build = raíz
del repo para poder importar `pilar2-distribuido/common`.

PYTHONPATH debe incluir `/app` y `/app/voxchain-api`.

#### docker-compose.yml

Agregar el servicio `voxchain-api` al archivo existente
`pilar2-distribuido/docker-compose.yml`:

```yaml
voxchain-api:
  build:
    context: ..
    dockerfile: pilar2-distribuido/voxchain-api/Dockerfile
  depends_on:
    rabbitmq:
      condition: service_healthy
    redis:
      condition: service_healthy
  environment:
    <<: *app-env
    NCT_HEALTH_URL: http://coordinator:8080/health
    TRP_HEALTH_URL: http://transaction-pool:8080/health
    PORT: "8000"
  ports:
    - "8000:8000"
```

---

### 2. Frontend — nuevo servicio `voxchain-frontend`

Ubicación: `pilar2-distribuido/voxchain-frontend/`

Tecnología: Angular 19, standalone components, Angular Material 3,
signals para estado reactivo, HttpClient para REST, EventSource para SSE.

No usar NgRx ni librerías de estado externas. Usar signals nativos de
Angular 19 (`signal`, `computed`, `effect`).

#### Estructura de módulos/componentes

```
voxchain-frontend/src/app/
  core/
    services/
      api.service.ts          # HttpClient wrapper para todos los endpoints
      events.service.ts       # SSE client con reconexión automática
    models/
      block.model.ts
      law.model.ts
      window.model.ts
  features/
    dashboard/
      dashboard.component.ts  # vista principal: métricas rápidas + actividad
    chain/
      chain.component.ts      # lista de bloques con paginación
      block-detail.component.ts
    laws/
      laws.component.ts       # lista filtrable por status
      law-detail.component.ts
      propose-law.component.ts  # formulario de propuesta
    health/
      health.component.ts     # estado de todos los servicios
  shared/
    components/
      status-badge/           # badge de color por status de ley/ventana
      hash-display/           # trunca hashes con tooltip del completo
      active-window-banner/   # banner fijo si hay ventana activa
    pipes/
      truncate-hash.pipe.ts
```

#### Vistas requeridas

**Dashboard** (`/`)
- Métricas: total de bloques en la cadena, leyes promulgadas, leyes
  pendientes, ventana activa (si existe)
- Feed de actividad reciente: últimos 5 bloques sellados
- Banner de ventana activa con countdown al deadline si hay una abierta
- Actualización en tiempo real vía SSE

**Cadena** (`/chain`)
- Lista paginada de bloques (más reciente primero)
- Por bloque mostrar: law_id, action, nonce, winning_node_or_pool,
  timestamp, primeros 12 chars del block_hash
- Click → detalle completo del bloque y su ventana asociada

**Leyes** (`/laws`)
- Tabs o filtro por status (todos / pending_queue / in_window /
  promulgated / discarded / repealed)
- Por ley mostrar: law_id, author_pubkey (truncado), status badge, action
- Click → detalle con historial de ventanas asociadas

**Proponer ley** (`/laws/propose`)
- Formulario con campos: Texto de la ley (textarea), Author pubkey
  (input), Acción (select: promulgación / derogación), Law ID (opcional)
- Mostrar el SHA-256 del texto en tiempo real a medida que el usuario
  escribe (computado en el browser con SubtleCrypto API)
- Al enviar: POST a `/api/laws`, mostrar respuesta y navegar a detalle

**Health** (`/health`)
- Cards por servicio (NCT, TrP, Redis, API) con indicador verde/rojo
- Polling cada 10 segundos

#### Comportamiento SSE

En `EventsService`:
- Conectar a `GET /api/events` con `EventSource`
- Ante `block_added`: actualizar signal de cadena sin recargar todo
- Ante `window_opened` / `window_closed`: actualizar banner de ventana activa
- Reconectar automáticamente ante desconexión (backoff exponencial,
  máximo 30 segundos)
- Exponer signals: `latestBlock`, `activeWindow`, `connectionStatus`

#### Estilos y UX

- Angular Material 3 con tema oscuro (apropiado para contexto blockchain)
- Colores de status de leyes:
  - pending_queue → amber
  - in_window → blue (pulsante si es la ventana activa actual)
  - promulgated → green
  - discarded → red
  - repealed → purple
- Hashes siempre en fuente monoespaciada, truncados a 12 chars con
  tooltip del hash completo y botón de copiar
- Responsive: funcional en viewport de 1280px mínimo

#### docker-compose.yml

Agregar el servicio `voxchain-frontend`:

```yaml
voxchain-frontend:
  build:
    context: pilar2-distribuido/voxchain-frontend
    dockerfile: Dockerfile
  ports:
    - "4200:80"
  depends_on:
    - voxchain-api
```

Dockerfile: build Angular con `ng build --configuration production`,
servir con nginx:alpine. Configurar nginx para proxy `/api/*` a
`http://voxchain-api:8000` y `try_files` para SPA routing.

---

## Restricciones y convenciones

- Usar la terminología exacta del dominio en todo el código: `law`,
  `voting_window`, `n_zeros_required`, `NCT`, `pool`, `cooldown`,
  `partial_hash_base`. No usar "transaction", "vote", "block reward" ni
  terminología de blockchain monetaria.
- La API no implementa lógica de dominio. Si necesita calcular algo
  (hash, compresión), usar las funciones ya existentes en
  `pilar2-distribuido/common/blockchain/`.
- No persistir claves privadas en ningún lado. El campo `author_pubkey`
  es solo un string identificador; la UI no genera ni valida pares de
  claves criptográficas.
- El frontend no se comunica directamente con Redis ni RabbitMQ.
- Todos los secretos/URLs por variables de entorno.
- No agregar dependencias a los servicios existentes (nct-coordinator,
  transaction-pool, worker). Solo agregar archivos nuevos y modificar
  `docker-compose.yml`.

## Orden de implementación sugerido al agente

1. `voxchain-api`: modelos Pydantic, `redis_reader.py`, endpoints GET,
   endpoint POST /api/laws, SSE endpoint, Dockerfile, agregar a compose
2. Verificar que `docker compose up` levanta la API y los endpoints
   responden con datos reales de Redis
3. `voxchain-frontend`: scaffold Angular 19, modelos, ApiService,
   EventsService, componentes en orden: Dashboard → Laws → Chain →
   ProposeForm → Health, Dockerfile, agregar a compose
4. Verificar flujo completo: proponer ley desde UI → ver ventana activa
   → ver bloque sellado en cadena
```