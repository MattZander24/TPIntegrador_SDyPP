# Pilar 3 — Despliegue, prueba y escalabilidad

## Componentes

| Directorio       | Contenido                                      |
|------------------|------------------------------------------------|
| `kubernetes/`    | Manifiestos K8s (infra, apps, HPA)            |
| `terraform/`     | Infraestructura como código con OpenTofu      |
| `load-tests/`    | Pruebas de carga y resultados                  |
| `scripts/`       | Scripts auxiliares                             |

## Pipelines CI/CD

1. `01-infra.yml` — Cluster GKE con OpenTofu
2. `02-services.yml` — Redis + RabbitMQ
3. `03-apps.yml` — NCT, TrP, Workers
4. `04-vms.yml` — VMs worker externas

## Pruebas (Pilar 3.3)

- Tamaños de bulk: 1, 10, 100, 1K, 10K, 100K transacciones
- Dificultades: prefijo 1 a 8 caracteres
- Fragmentación TrP: 1% a 50%
- Entrada/salida de nodos GPU

## Decisiones de diseño

- OpenTofu declarativo para reproducibilidad
- HPA para escalado automático de workers
- GKE como orquestador base
