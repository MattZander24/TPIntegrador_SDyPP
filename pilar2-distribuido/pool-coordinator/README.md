# Pool Coordinator

El Pool Coordinator agrega mineros voluntarios y distribuye el trabajo de minería recibido del Transaction Pool (TrP). Desde la perspectiva del NCT/TrP, el pool se comporta como un worker individual, pero internamente fragmenta el rango de nonces entre sus miners registrados vía HTTP.

## Responsabilidades

- Consume tareas de `tareas_trp` (flujo 4) del TrP y las fragmenta entre miners registrados.
- Mantiene registro de miners vía HTTP con capacidad, GPU y keepalive.
- Implementa elección de liderazgo mediante lease en Redis para alta disponibilidad.
- Publica keepalives al TrP con capacidad agregada del pool.
- Recibe resultados de miners y publica nonce ganador a `respuesta_nonce` (flujo 3).
- Solo el líder del pool se suscribe a colas de trabajo; los followers esperan elección.

## Estructura

| Archivo                | Contenido |
|------------------------|-----------|
| `pool_coordinator/coordinator.py` | Núcleo: registro de miners, distribución de trabajo, elección de liderazgo, keepalives. |
| `pool_coordinator/server.py` | Servidor HTTP para registro de miners (`/register`), heartbeat (`/heartbeat`), obtención de trabajo (`/work/next/:miner_id`) y envío de resultados (`/work/result`). |
| `pool_coordinator/main.py` | Punto de entrada: cablea RabbitMQ, Redis, HTTP server y health endpoint. |

## Ejecución

```bash
# Vía docker-compose (recomendado), desde pilar2-distribuido/
docker compose up --build pool-coordinator

# Directo (requiere RabbitMQ y Redis accesibles)
RABBITMQ_URL=amqp://guest:guest@localhost:5672/ REDIS_URL=redis://localhost:6379/0 \
PYTHONPATH=..:. POOL_ID=pool-1 POOL_CAPACITY=10 python -m pool_coordinator.main
```

Health: `GET :8080/health` → `{"pool":"ok","rabbitmq":"ok","redis":"ok"}`.
Pool HTTP server: `GET :9001/health` → `{"pool":"ok","rabbitmq":"ok","miners":N}`.

## API HTTP para Miners

| Endpoint | Método | Payload | Respuesta |
|----------|--------|---------|-----------|
| `/register` | POST | `{"capacity": int, "has_gpu": bool}` | `{"miner_id": str}` |
| `/heartbeat` | POST | `{"miner_id": str}` | `{"ok": bool}` |
| `/work/next/:miner_id` | GET | - | Task JSON o `204 No Content` |
| `/work/result` | POST | `{"miner_id": str, "result": {...}}` | `{"ok": bool}` |
| `/health` | GET | - | `{"pool":"ok","rabbitmq":"ok","miners":N}` |

## Configuración (variables de entorno)

| Variable | Default | Descripción |
|----------|---------|-------------|
| `POOL_ID` | `pool-default` | Identificador único del pool en el sistema |
| `POOL_CAPACITY` | `1` | Capacidad base del pool (sin miners) |
| `LEADER_LEASE_TTL` | `10` | TTL en segundos del lease de liderazgo en Redis |
| `POOL_HTTP_PORT` | `9001` | Puerto del servidor HTTP para miners |
| `HEALTH_PORT` | `8080` | Puerto del health endpoint |
| `RABBITMQ_URL`, `REDIS_URL` | ver compose | Infraestructura |

## Decisiones de diseño

- **Liderazgo vía Redis SETNX**: similar al NCT, el pool usa un lease en Redis para evitar split-brain. Solo el líder consume `tareas_trp` y publica keepalives.
- **Fragmentación round-robin**: el rango de nonces recibido del TrP se divide en chunks iguales entre miners disponibles (fresh + no busy).
- **Keepalive de miners**: TTL de 15 segundos; miners stale son purgados automáticamente.
- **Deduplicación de soluciones**: el pool mantiene un set `_solved` de ventanas ya resueltas para evitar publicar duplicados.
- **Indistinguibilidad del pool**: para el NCT/TrP, el pool es un worker más (publica con `winning_node_or_pool = pool_id`).
- **HTTP simple**: el servidor HTTP usa `http.server` estándar (sin framework) para minimizar dependencias.
