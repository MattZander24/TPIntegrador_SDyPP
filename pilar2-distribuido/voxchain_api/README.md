# VoxChain API

API Gateway para VoxChain, implementada con FastAPI. Expone endpoints REST para consultar la blockchain, leyes, ventanas de votación y proponer nuevas leyes. Incluye Server-Sent Events (SSE) para actualizaciones en tiempo real y métricas Prometheus.

## Responsabilidades

- Expone endpoints REST para consultar cadena, leyes, ventanas y health del sistema.
- Permite proponer nuevas leyes vía POST a `/api/laws` (publica a cola `propuestas`).
- Lee estado de Redis (cadena, leyes, ventanas) sin escribir directamente.
- Publica propuestas de leyes a RabbitMQ para consumo del NCT.
- Implementa SSE (`/api/events`) para broadcasting de cambios en tiempo real (bloques, ventanas, leyes).
- Expone métricas Prometheus en `/metrics` para monitoreo.
- Health check agregado que verifica NCT, Redis y estado interno.

## Estructura

| Archivo                | Contenido |
|------------------------|-----------|
| `main.py` | Aplicación FastAPI, configuración CORS, middleware de métricas, tarea de fondo SSE. |
| `config.py` | Configuración desde variables de entorno (Redis, RabbitMQ, URLs de health, puerto). |
| `models.py` | Modelos Pydantic para requests/responses (Law, Window, Block, HealthResponse, etc.). |
| `routers/chain.py` | Endpoints para consultar la blockchain (`GET /api/chain`, `GET /api/chain/:index`). |
| `routers/laws.py` | Endpoints para leyes (`GET /api/laws`, `POST /api/laws`, `GET /api/laws/:id`). |
| `routers/windows.py` | Endpoints para ventanas de votación (`GET /api/windows`, `GET /api/windows/active`). |
| `routers/health.py` | Health check agregado (`GET /api/health`). |
| `services/redis_reader.py` | Cliente de lectura de Redis (cadena, leyes, ventanas). |
| `services/rabbitmq_publisher.py` | Publicador de RabbitMQ para propuestas de leyes. |

## Ejecución

```bash
# Vía docker-compose (recomendado), desde pilar2-distribuido/
docker compose up --build voxchain-api

# Directo (requiere Redis y RabbitMQ accesibles)
REDIS_URL=redis://localhost:6379/0 RABBITMQ_URL=amqp://guest:guest@localhost:5672/ \
NCT_HEALTH_URL=http://localhost:8080/health \
PORT=8000 python -m voxchain_api.main
```

Root: `GET /` → `{"service":"voxchain-api","version":"1.0.0","status":"running"}`.
Health: `GET /api/health` → `{"api":"ok","nct":"ok","redis":"ok"}`.
Metrics: `GET /metrics` → Métricas Prometheus (Prometheus text format).

## API REST

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/chain` | GET | Obtiene toda la blockchain |
| `/api/chain/{index}` | GET | Obtiene un bloque por índice |
| `/api/laws` | GET | Obtiene todas las leyes |
| `/api/laws/{law_id}` | GET | Obtiene una ley por ID |
| `/api/laws` | POST | Propone una nueva ley (publica a RabbitMQ) |
| `/api/windows` | GET | Obtiene todas las ventanas de votación |
| `/api/windows/active` | GET | Obtiene la ventana activa actual |
| `/api/health` | GET | Health check agregado del sistema |
| `/api/events` | GET | SSE stream para eventos en tiempo real |

## Eventos SSE

El endpoint `/api/events` emite eventos en tiempo real cuando ocurren cambios en el sistema:

| Evento | Data | Descripción |
|--------|------|-------------|
| `block_added` | `{"block": {...}}` | Nuevo bloque añadido a la cadena |
| `window_opened` | `{"window": {...}}` | Nueva ventana de votación abierta |
| `window_closed` | `{}` | Ventana de votación cerrada |
| `law_updated` | `{"law_id": "...", "status": "..."}` | Estado de ley actualizado |

## Configuración (variables de entorno)

| Variable | Default | Descripción |
|----------|---------|-------------|
| `REDIS_URL` | `redis://redis:6379/0` | URL de conexión a Redis |
| `RABBITMQ_URL` | `amqp://guest:guest@rabbitmq:5672/` | URL de conexión a RabbitMQ |
| `NCT_HEALTH_URL` | `http://coordinator:8080/health` | URL de health del NCT |
| `TRP_HEALTH_URL` | (eliminado) | El TrP fue eliminado; la fragmentación la hace cada Pool Coordinator internamente |
| `PORT` | `8000` | Puerto del servidor HTTP |

## Decisiones de diseño

- **Solo lectura de Redis**: la API no escribe estado; lee de Redis y publica propuestas a RabbitMQ. El NCT es la única fuente de verdad para escrituras.
- **SSE polling**: implementación simple con polling cada 2 segundos a Redis. En producción podría reemplazarse por Redis Pub/Sub o notificaciones del NCT.
- **CORS configurado para localhost**: permite desarrollo local con frontend en puerto 4200. En producción debe ajustarse.
- **Métricas Prometheus**: middleware automático que captura duración y conteo de requests por ruta y método.
- **Modelos Pydantic**: validación automática de requests/responses y documentación OpenAPI generada automáticamente (`/docs`).
- **Lifespan manager**: maneja conexión a Redis y tarea de fondo SSE en startup/shutdown.
