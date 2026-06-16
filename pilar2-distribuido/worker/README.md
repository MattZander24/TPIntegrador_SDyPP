# Worker minero

El worker ejecuta el Proof of Work de gobierno **invocando el minero de Pilar 1**
(no se reimplementa el hashing). Pensado para correr con `replicas: 2` (P1).

## Responsabilidades

- Consume un rango `[range_min, range_max)` de `tareas_trp` (flujo interno 4).
- Ejecuta el PoW como **subproceso**: binario CUDA
  `pilar1-minero/gpu/bin/05_brute_force_range` si hay GPU; si no, fallback al
  minero CPU `pilar1-minero/cpu/src/brute_force.py`. El prefijo es
  `n_zeros_required` caracteres `'0'`.
- Si encuentra un nonce, publica a `respuesta_nonce` (flujo 3, red → NCT).
- Emite **keep-alives** periódicos al TrP (`keepalive_trp`, flujo interno 5).
- **Idempotente** ante reasignación de rangos: no vuelve a publicar para una
  ventana que ya resolvió.

## Estructura

| Archivo                  | Contenido |
|--------------------------|-----------|
| `worker_pkg/miner.py`    | Puente al minero de Pilar 1 (GPU/CPU) y parseo de salida. |
| `worker_pkg/worker.py`   | Lógica del worker (consumo, minado, publicación). |
| `main.py`                | Cablea RabbitMQ + health endpoint + loop + keep-alive. |

## Ejecución

```bash
docker compose up --build worker   # levanta 2 réplicas
```

Health: `GET :8080/health` → `{"worker":"ok","rabbitmq":"ok"}` (red interna).

## Configuración

| Variable | Default | Descripción |
|----------|---------|-------------|
| `MINER_GPU_BIN` | (vacío) | Ruta al binario CUDA; si no existe, se usa CPU. |
| `MINER_CPU_SCRIPT` | `/app/pilar1-minero/cpu/src/brute_force.py` | Minero CPU (fallback). |
| `WORKER_ID` | `worker-<hostname>` | Identidad del worker/pool (gana el bloque). |
| `WORKER_CAPACITY` | 1 | Capacidad reportada en el keep-alive. |
| `RABBITMQ_URL`, `HEALTH_PORT` | ver compose | Infraestructura. |

## Decisiones de diseño

- **El minero es un subproceso, no una librería**: respeta la frontera con Pilar 1
  y permite usar el binario CUDA tal cual. La salida (`Nonce = N`) es común a GPU y
  CPU, así que el parseo es uno solo.
- **Sin Redis en el worker**: el worker es stateless respecto del estado de la
  cadena; la deduplicación de soluciones tardías la hace el NCT.
- En contenedor sin GPU, el fallback CPU es automático (el binario CUDA no existe).
