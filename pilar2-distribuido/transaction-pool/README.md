# Transaction Pool (TrP)

El TrP es el **pool de minería** de VoxChain (AGENT.md P5): subdivide el espacio de
búsqueda del nonce de la ventana activa en fragmentos y los reparte entre los
workers (patrón *bolsa de tareas / granja de trabajadores*, DOC U7.5).

## Responsabilidades

- Suscrito a `desafio_activo` (flujo 2). Al recibir un desafío, **fragmenta** el
  espacio de nonces `[0, NONCE_SPACE)` en tramos de `FRAGMENT_SIZE` y los publica a
  `tareas_trp` (flujo interno 4), que los workers consumen en competencia.
- Recibe **keep-alives** de los workers por `keepalive_trp` (flujo interno 5) para
  conocer la capacidad disponible (`capacity`, `has_gpu`) y la frescura de cada
  worker.
- **Sin workers GPU**: loguea que se requiere escalar mineros CPU. **No reduce la
  dificultad** — `n_zeros_required` lo fija el NCT y el ajuste dinámico por carga
  está prohibido (AGENT.md 10). El autoescalado real es Pilar 3.

## Estructura

| Archivo                 | Contenido |
|-------------------------|-----------|
| `trp/pool.py`           | Servicio: maneja desafíos y keep-alives, publica tareas. |
| `trp/fragmentation.py`  | Lógica pura de fragmentación de rangos. |
| `main.py`               | Cablea RabbitMQ + health endpoint + loop. |

## Ejecución

```bash
docker compose up --build transaction-pool   # desde pilar2-distribuido/
```

Health: `GET :8080/health` (publicado en `:8082` por compose).

## Configuración

| Variable | Default | Descripción |
|----------|---------|-------------|
| `NONCE_SPACE` | 50000000 | Tamaño total del espacio de nonces a fragmentar. |
| `FRAGMENT_SIZE` | 1000000 | Tamaño de cada fragmento (Pilar 3 lo barre de 1% a 50%). |
| `RABBITMQ_URL`, `HEALTH_PORT` | ver compose | Infraestructura. |

## Decisiones de diseño

- **Bolsa de tareas sobre una sola cola**: en vez de asignar rangos por worker, se
  publican todos los fragmentos a `tareas_trp` y los workers compiten por
  consumirlos (con `prefetch_count=1`). La capacidad emerge naturalmente; los
  keep-alives sirven para decisiones de escalado/observabilidad.
- **El TrP no toca al NCT**: sólo media entre el desafío y los workers; los flujos
  4 y 5 son internos y están documentados antes de implementarse (AGENT.md 10).
