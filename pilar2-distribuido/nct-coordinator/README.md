# NCT — Nodo Coordinador de Tareas

El NCT gestiona **exclusivamente** las ventanas de votación de VoxChain
(AGENT.md 3.3 y P4). No arbitra el contenido de las leyes ni ajusta la dificultad
por carga de red.

## Responsabilidades

- Consume `propuestas` (flujo 1) y mantiene la cola de leyes con **round-robin por
  autor** (no FIFO).
- Aplica **cooldown** al encolar: rechaza al autor en cooldown y distingue
  reproposición idéntica (mayor cooldown) de propuesta nueva, por `text_hash`.
- Abre la **ventana siguiente**: genera `voting_window_id`, fija
  `n_zeros_required` = `n` (promulgar) o `n+1` (derogar), `deadline` según el tipo,
  `partial_hash_base = law_id + text_hash + voting_window_id + action`; persiste en
  Redis y publica a `desafio_activo` (flujo 2).
- Consume `respuesta_nonce` (flujo 3): **verifica** el nonce (recalcula el hash,
  chequea prefijo y deadline), **descarta tardíos/duplicados**, sella el bloque,
  actualiza el `status` de la ley y avanza a la siguiente ventana.
- Cierra por **deadline**: ley → `discarded`, ventana → `expired_pending`, sin
  reencolar.
- Sucesión por esfuerzo (Bully mejorado, `nct/bully.py`): piezas de PoW listas;
  coordinación distribuida pendiente (`xfail`).

## Estructura

| Archivo                | Contenido |
|------------------------|-----------|
| `nct/coordinator.py`   | Núcleo (cola, ventanas, verificación, sellado). Agnóstico de transporte/backend. |
| `nct/queue_logic.py`   | Lógica pura: round-robin y cálculo de cooldown. |
| `nct/bully.py`         | Mini-PoW de elección de NCT (coordinación distribuida pendiente). |
| `main.py`              | Cablea RabbitMQ + Redis + health endpoint + loop. |

## Ejecución

```bash
# vía docker-compose (recomendado), desde pilar2-distribuido/
docker compose up --build coordinator

# directo (requiere RabbitMQ y Redis accesibles)
RABBITMQ_URL=amqp://guest:guest@localhost:5672/ REDIS_URL=redis://localhost:6379/0 \
PYTHONPATH=..:. N_ZEROS=4 python main.py
```

Health: `GET :8080/health` → `{"nct":"ok","redis":"ok","rabbitmq":"ok"}`.

## Configuración (variables de entorno)

| Variable | Default | Descripción |
|----------|---------|-------------|
| `N_ZEROS` | 4 | `n` base; derogación usa `n+1`. **No** se ajusta dinámicamente. |
| `WINDOW_SECONDS_PROMULGACION` | 60 | Duración de ventana de promulgación. |
| `WINDOW_SECONDS_DEROGACION` | 90 | Duración de ventana de derogación. |
| `COOLDOWN_WINDOWS_NEW` | `N_ZEROS` | Cooldown tras proponer (en ventanas). |
| `COOLDOWN_WINDOWS_REPROPOSED` | `2*N_ZEROS` | Cooldown mayor por reproposición idéntica. |
| `RABBITMQ_URL`, `REDIS_URL`, `HEALTH_PORT` | ver compose | Infraestructura. |

## Decisiones de diseño

- **Estado de ventana en memoria, no recuperable**: ante caída del NCT la ventana
  se pierde (AGENT.md 4); por eso el `_active` vive en proceso. La cadena, leyes y
  cooldowns sí persisten en Redis.
- **El autor no puede ganar su propia ventana** (3.4): se descarta la respuesta si
  `winning_node_or_pool == author_pubkey` de la ley.
- **Derogación**: reutiliza la ley promulgada cambiando su `action` y reencolándola;
  al sellar pasa a `repealed`.
