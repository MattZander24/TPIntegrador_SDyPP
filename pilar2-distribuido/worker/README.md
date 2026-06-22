# Worker minero

El worker ejecuta el Proof of Work de gobierno **invocando el minero de Pilar 1**
(no se reimplementa el hashing).

## Modos de operación

El worker soporta **tres modos** intercambiables en caliente vía hot-switch:

| Modo | `WORKER_MODE` | Cómo recibe trabajo | Rango de nonces | A quién reporta |
|------|---------------|---------------------|-----------------|-----------------|
| RabbitMQ | `rabbitmq` (default) | Cola `tareas_trp` del TrP | Fragmento del TrP | NCT (`respuesta_nonce`) |
| Pool-miner | `pool-miner` | HTTP al Pool Coordinator | Fragmento del pool | Pool Coordinator |
| Standalone | `standalone` | Topic `desafio_activo` del NCT | Completo `[0, NONCE_SPACE)` | NCT (`respuesta_nonce`) |

### RabbitMQ mode
Consume un rango `[range_min, range_max)` desde `tareas_trp` que el TrP fragmentó.
Emite keep-alives al TrP. Comportamiento original del worker.

### Pool-miner mode
Se conecta vía HTTP al Pool Coordinator. Delega la **decisión de voto** al dueño
del pool: el pool coordinator aplica su `voting_policy` y solo asigna trabajo si
la ley es aceptada. El minero no elige qué minar.

### Standalone mode
Se suscribe directo al exchange `desafio_activo` del NCT. No depende del TrP ni
de ningún pool. Mina el **espacio completo de nonces** (sin fragmentación) y
publica el resultado directamente al NCT. Filtra leyes según
`STANDALONE_REJECTED_ACTIONS` — el usuario decide qué leyes votar.

## Votación y autonomía

- Los mineros dentro de un **pool** delegan el sentido de voto al dueño del pool.
  Si el dueño rechaza una ley vía `POST /pool/policy`, el pool coordinator no
  distribuye trabajo para esa ley y los mineros nunca la procesan.
- Los mineros en modo **standalone** deciden por sí mismos qué leyes minar
  mediante la variable `STANDALONE_REJECTED_ACTIONS`.
- En cualquier momento un minero puede **abandonar su pool** y pasar a standalone
  (o viceversa) mediante hot-switch sin reiniciar el contenedor.

## Hot-switch (cambio de modo en caliente)

El worker expone un servidor HTTP de administración en el puerto `9090`
(variable `ADMIN_PORT`).

```bash
# De pool-miner a standalone
curl -X POST http://worker:9090/switch-mode \
  -d '{"target":"standalone"}'

# De standalone a pool-miner
curl -X POST http://worker:9090/switch-mode \
  -d '{"target":"pool-miner","pool_url":"http://nuevo-pool:9001"}'

# De standalone/ pool-miner a rabbitmq
curl -X POST http://worker:9090/switch-mode \
  -d '{"target":"rabbitmq"}'

# Ver modo actual
curl http://worker:9090/status
```

Al cambiar de modo:
1. El worker actual se detiene limpiamente (señal `stop()`)
2. La conexión RabbitMQ se cierra y se reabre si el nuevo modo la necesita
3. Se inicia el nuevo worker en un thread separado
4. El health endpoint refleja el modo activo

## Estructura

| Archivo | Contenido |
|---------|-----------|
| `main.py` | Punto de entrada, `WorkerManager` con hot-switch, health y admin server |
| `worker_pkg/worker.py` | Worker RabbitMQ: consume `tareas_trp`, mina rangos, publica nonce |
| `worker_pkg/standalone_worker.py` | Worker standalone: consume `desafio_activo`, mina espacio completo |
| `worker_pkg/pool_miner.py` | Worker pool-miner: HTTP al Pool Coordinator |
| `worker_pkg/miner.py` | Puente al minero de Pilar 1 (GPU/CPU) y parseo de salida |
| `worker_pkg/admin_server.py` | Servidor HTTP para hot-switch (`POST /switch-mode`, `GET /status`) |

## Ejecución

```bash
docker compose up --build worker   # levanta 2 réplicas en modo rabbitmq

# Especificar modo
WORKER_MODE=standalone docker compose up --build worker
WORKER_MODE=pool-miner POOL_COORDINATOR_URL=http://pool:9001 docker compose up --build worker
```

Health: `GET :8080/health` → `{"worker_id":"...", "mode":"standalone", "status":"ok"}`.

## Configuración

| Variable | Default | Descripción |
|----------|---------|-------------|
| `MINER_GPU_BIN` | (vacío) | Ruta al binario CUDA; si no existe, se usa CPU. |
| `MINER_CPU_SCRIPT` | `/app/pilar1-minero/cpu/src/brute_force.py` | Minero CPU (fallback). |
| `WORKER_ID` | `worker-<hostname>` | Identidad del worker (gana el bloque). |
| `WORKER_CAPACITY` | 1 | Capacidad reportada en el keep-alive. |
| `WORKER_MODE` | `rabbitmq` | Modo inicial: `rabbitmq`, `pool-miner`, o `standalone`. |
| `POOL_COORDINATOR_URL` | `http://pool-coordinator:9001` | URL del Pool Coordinator (modo pool-miner). |
| `STANDALONE_NONCE_SPACE` | `50000000` | Tamaño del espacio de nonces (modo standalone). |
| `STANDALONE_REJECTED_ACTIONS` | (vacío) | Acciones a rechazar en modo standalone, separadas por coma. Ej: `derogacion` |
| `ADMIN_PORT` | `9090` | Puerto del servidor de administración (hot-switch). |
| `RABBITMQ_URL` | `amqp://guest:guest@rabbitmq:5672/` | Conexión RabbitMQ. |
| `HEALTH_PORT` | `8080` | Puerto del health endpoint. |

## Decisiones de diseño

- **El minero es un subproceso, no una librería**: respeta la frontera con Pilar 1
  y permite usar el binario CUDA tal cual. La salida (`Nonce = N`) es común a GPU y
  CPU, así que el parseo es uno solo.
- **Sin Redis en el worker**: el worker es stateless respecto del estado de la
  cadena; la deduplicación de soluciones tardías la hace el NCT.
- **Hot-switch vía threads**: el loop de consumo RabbitMQ corre en un thread para
  poder cerrarlo limpiamente al cambiar de modo sin reiniciar el proceso.
- **Pool-miner delega voto**: el minero dentro de un pool no elige qué leyes minar,
  esa decisión la centraliza el pool coordinator según la política del dueño.
- **Standalone mina todo el espacio**: sin TrP ni pool, el worker se suscribe al
  desafío del NCT y barre `[0, STANDALONE_NONCE_SPACE)` compitiendo directamente
  contra el resto de la red.
- **En contenedor sin GPU**, el fallback CPU es automático (el binario CUDA no existe).
