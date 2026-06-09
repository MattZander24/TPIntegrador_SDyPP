# Pilar 2 — Infraestructura de servicios distribuidos

Componentes del sistema distribuido para la blockchain.

## Servicios

| Servicio           | Carpeta              | Rol                                          |
|--------------------|----------------------|----------------------------------------------|
| NCT Coordinator    | `nct-coordinator/`   | Forma bloques, define dificultad, valida PoW |
| Transaction Pool   | `transaction-pool/`  | Subdivide tareas, recibe keep-alives, escala  |
| Worker             | `worker/`            | Consume colas RabbitMQ, ejecuta PoW          |

## Dependencias

- **RabbitMQ** — Colas de tareas de minería
- **Redis** — Persistencia de la blockchain

## Ejecución local

```bash
docker compose up
```

## Decisiones de diseño

- Protocolo asincrónico via RabbitMQ (topic exchange)
- Redis como almacenamiento de bloques (hash por bloque)
- NCT publica tareas → Workers consumen y compiten → NCT valida y persiste
