# AUDITORIA.md — VoxChain (auditoría 2026-06-20)

> Generado por Claude Code (claude-sonnet-4-6). Toda afirmación se respalda con evidencia concreta (ruta de archivo o hash de commit).

---

## 1. Resumen ejecutivo

El integrante (MattZander24, según `variables.tf`) desarrolló un sistema funcional y coherente. **Pilar 1 está completo** en código CUDA (5 programas `.cu`) con tests, comparativa parcial y documentación de hits. **Pilar 2 está mayoritariamente completo**: NCT, TrP, Pool Coordinator, worker, RabbitMQ con 5 flujos documentados, Redis con persistencia, Bully distribuido y 91/91 tests pasando. **Pilar 3 tiene la infraestructura declarada** (OpenTofu, 4 pipelines CI/CD, manifiestos K8s, monitoring) pero carece de tres entregables críticos: resultados/gráficos de los experimentos de carga, informe detallado completo y el video explicativo. El avance estimado es **Pilar 1: ~85%**, **Pilar 2: ~90%**, **Pilar 3: ~65%**. Dado que la fecha de entrega es el **23/06/2026 (3 días)**, el riesgo es alto: los experimentos de carga requieren un entorno productivo en GCP que no fue posible verificar en este entorno. Si el cluster ya está desplegado, el tiempo restante alcanza para ejecutar y documentar los experimentos. Si no, el riesgo es crítico.

---

## 2. Tabla de cumplimiento

| # | Requisito | Estado | Evidencia | Nota |
|---|-----------|--------|-----------|------|
| **PILAR 1** |
| 1.1 | Minero CUDA en C/C++ | ✓ | `pilar1-minero/gpu/src/01_hello.cu`…`05_brute_force_range.cu` | 5 archivos `.cu` |
| 1.2 | Versión CPU compatible | ✓ | `pilar1-minero/cpu/src/brute_force.py` | Python, misma interfaz CLI |
| 1.3 | Hit #1 — setup CUDA | ✓ | `docs/informe/hit1-setup.md` | Documenta entorno Google Colab T4 |
| 1.4 | Hit #2 — hola mundo CUDA | ✓ | `pilar1-minero/gpu/src/01_hello.cu` | Kernel GPU con salida por hilo |
| 1.5 | Hit #3 — librerías CUDA (Thrust) | ✓ | `pilar1-minero/gpu/src/02_thrust_vector.cu`, `docs/informe/hit3-thrust-cccl.md` | — |
| 1.6 | Hit #4 — MD5 en GPU | ✓ | `pilar1-minero/gpu/src/03_md5_hash.cu`, `gpu/include/md5.cuh` | Implementación propia de MD5 |
| 1.7 | Hit #5 — fuerza bruta de prefijo | ✓ | `pilar1-minero/gpu/src/04_brute_force.cu` | Kernel con early-exit atómico |
| 1.8 | Hit #6 — mediciones longitud de prefijo vs tiempo | ◐ | `pilar1-minero/benchmarks/run_prefix_bench.py`, `docs/informe/hit6-prefix-bench.md`, `docs/informe/cierre-etapa-inicial.md` | No existe `05_prefix_bench.cu` (README lo nombra así pero en disco es `05_brute_force_range.cu`). Resultados CPU son estimados teóricos, no mediciones reales. |
| 1.9 | Hit #7 — fuerza bruta con límites de rango | ✓ | `pilar1-minero/gpu/src/05_brute_force_range.cu` | Acepta `min` y `max` como parámetros |
| 1.10 | Comparativa CPU vs GPU (cierre etapa inicial) | ◐ | `docs/informe/cierre-etapa-inicial.md` | Tiempos GPU reales (T4); tiempos CPU son estimados teóricos (~1 MH/s) sin medición real |
| 1.11 | String base = desafío de gobierno | ✓ | `common/blockchain/challenge.py:36`, `worker/worker_pkg/miner.py:50-51` | `law_id + text_hash + voting_window_id + action` |
| 1.12 | Compila desde terminal sin IDE | ✓ | `pilar1-minero/gpu/Makefile` | `make 04` compila y ejecuta; no verificable sin GPU en este entorno |
| **PILAR 2** |
| 2.1 | P1 — minero resuelve desafío de gobierno con dificultad n/n+1 | ✓ | `common/blockchain/challenge.py:39-49` (`n_zeros_for_action`) | Dificultad fija, sin ajuste dinámico |
| 2.2 | P1 — dificultad fijada por NCT, no por carga | ✓ | `nct-coordinator/nct/coordinator.py:47-57` | `n_zeros` como parámetro de construcción |
| 2.3 | P2 — cola `propuestas → NCT` | ✓ | `common/messaging/base.py:14` (`QUEUE_PROPUESTAS`) | — |
| 2.4 | P2 — tópico `NCT → red` con desafío activo | ✓ | `common/messaging/base.py:15-17` (`EXCHANGE_DESAFIO`) | Exchange tipo `topic` |
| 2.5 | P2 — cola `red → NCT` con nonce ganador | ✓ | `common/messaging/base.py:18` (`QUEUE_RESPUESTA_NONCE`) | — |
| 2.6 | P2 — no hay cuarto flujo NCT no documentado | ✓ | `common/messaging/base.py:20-29` | `QUEUE_TAREAS` y `QUEUE_KEEPALIVE` son flujos internos TrP→worker, no al NCT |
| 2.7 | P2 — flujos Bully (heartbeat + election) | ✓ | `common/messaging/base.py:22-29` (`EXCHANGE_HEARTBEAT`, `QUEUE_ELECTION`) | 5 flujos totales, concordantes con AGENT.md §5 |
| 2.8 | P3 — Redis con persistencia | ✓ | `kubernetes/infrastructure/redis-statefulset.yaml:21` | `--appendonly yes`; PVC 10Gi |
| 2.9 | P3 — cadena de bloques en Redis | ✓ | `common/storage/redis_store.py` | `append_block`, `last_block_hash` |
| 2.10 | P3 — cooldowns por autor en Redis | ✓ | `common/storage/redis_store.py` (`set_cooldown`, `is_in_cooldown`) | — |
| 2.11 | P3 — estado de ventana activa en Redis | ✓ | `common/storage/redis_store.py` (`set_active_window`, `clear_active_window`) | — |
| 2.12 | P3 — esquema Redis concuerda con AGENT.md §7 | ✓ | `common/storage/redis_store.py` | Campos `law_id`, `text_hash`, `author_pubkey`, `voting_window_id`, `action`, `n_zeros_required`, `deadline`, `partial_hash_base`, `winning_nonce` presentes |
| 2.13 | P4 — NCT gestiona solo ventanas | ✓ | `nct-coordinator/nct/coordinator.py:1-11` (docstring) | No arbitra contenido |
| 2.14 | P4 — round-robin por autor distinto | ✓ | `nct-coordinator/nct/queue_logic.py`, test `test_round_robin_entre_dos_autores` | — |
| 2.15 | P4 — una sola ventana activa a la vez | ✓ | `nct-coordinator/nct/coordinator.py:175` (`if self._active is not None: return`) | — |
| 2.16 | P4 — verifica nonce antes del deadline | ✓ | `coordinator.py:234-236` | Chequea `now() > deadline_epoch` |
| 2.17 | P4 — descarta soluciones tardías | ✓ | `coordinator.py:256-259` | `try_seal_window` atómico con SETNX en Redis |
| 2.18 | P5 — Pool subdivide rango entre mineros | ✓ | `pool-coordinator/pool_coordinator/coordinator.py:139-143` | División del espacio entre miners registrados |
| 2.19 | P5 — Pool recibe keep-alives | ✓ | `pool_coordinator/coordinator.py:103-108` (`handle_heartbeat`) | — |
| 2.20 | P5 — Pool indistinguible del NCT | ✓ | `pool_coordinator/coordinator.py:170-177` | Publica `publish_nonce_response` como un worker |
| 2.21 | P5 — profundidad fija 2 niveles (minero → pool → NCT) | ✓ | `worker/worker_pkg/pool_miner.py`, `pool_coordinator/coordinator.py` | Dos modos en `worker/main.py` (`rabbitmq` vs `pool-miner`) |
| 2.22 | Tolerancia a fallos del NCT — Bully por esfuerzo | ✓ | `nct-coordinator/nct/bully.py` | Mini-PoW entre candidatos |
| 2.23 | Tolerancia — pérdida documentada de ventana en curso | ✓ | `nct-coordinator/nct/coordinator.py:325-326` (`clear_active_window`); AGENT.md §4 y comentarios en código | — |
| 2.24 | Mínimo 2 réplicas por servicio | ◐ | Ver detalle en §3 | voxchain-api=2 ✓, frontend=2 ✓; NCT: 2 instancias pero en pods separados (primary+standby, no replicas del mismo Deployment ◐); Redis=1 ✗, RabbitMQ=1 ✗, TrP=1 ✗ |
| 2.25 | Tests unitarios e integración | ✓ | `pilar2-distribuido/` (91 tests, 0 fallos) | 91 passed in 159s |
| **PILAR 3** |
| 3.1 | K8s en GKE vía OpenTofu | ✓ | `pilar3-despliegue/terraform/gke/main.tf` | Cluster zonal `southamerica-east1-a` |
| 3.2 | Nodegroup infra (Redis, RabbitMQ) | ✓ | `main.tf:85-127` (`infra` node pool con taint `pool=infra`) | — |
| 3.3 | Nodegroup apps | ✓ | `main.tf:129-164` (`apps` node pool) | — |
| 3.4 | VMs externas para cómputo intensivo | ✓ | `kubernetes/gpu-cluster/` + `04-gpu-workers.yml` | Cluster k3s separado para GPU workers |
| 3.5 | Pipeline 1 — infra K8s | ✓ | `.github/workflows/01-infra.yml` | OpenTofu plan/apply manual vía `workflow_dispatch` |
| 3.6 | Pipeline 2 — Redis/RabbitMQ | ✓ | `.github/workflows/02-services.yml` | Automático ante cambios en `kubernetes/infrastructure/` |
| 3.7 | Pipeline 3 — apps | ✓ | `.github/workflows/03-apps.yml` | Build + deploy de todas las apps |
| 3.8 | Pipeline 4 — VMs worker | ✓ | `.github/workflows/04-gpu-workers.yml` | Deploy en k3s |
| 3.9 | gitleaks en pipeline (falla build si detecta secret) | ✓ | `.github/workflows/ci-checks.yml:7-16` | `gitleaks/gitleaks-action@v2` en PR y push a `main`/`dev` |
| 3.10 | Zero static keys / Workload Identity OIDC | ◐ | `main.tf:233-283` (`google_iam_workload_identity_pool`) | WIF para CI/CD ✓; Grafana admin password `"voxchain"` hardcodeada en `main.tf:321` ✗ |
| 3.11 | Despliegue en entorno público accesible desde Internet | ? | `kubernetes/applications/voxchain-api-ingress.yaml`, `voxchain-frontend-ingress.yaml` | Ingress configurado pero URL pública no verificable sin acceso al cluster GCP |
| 3.12 | Endpoint público de health (JSON) por servicio | ✓ | `common/health.py:1-18`, `/health` en todos los servicios | Retorna JSON `{"servicio": "ok/down"}` |
| 3.13 | Logs en memoria y disco | ✓ | `common/logging_setup.py`, `LOG_DIR` env var en todos los deployments | FileHandler + StreamHandler |
| 3.14 | Escalado dinámico de mineros CPU (HPA/VMs) | ✓ | `kubernetes/gpu-cluster/worker-hpa.yaml` (max=10), `pool-miner-hpa.yaml` (max=10) | HPA por CPU utilization 70% |
| 3.15 | Experimentos de carga — bulk 1–100.000 | ◐ | `load-tests/scenarios/test_bulk.py` | Script existe; resultados/gráficos **ausentes** del repo |
| 3.16 | Experimentos de carga — prefijos 1–8 | ◐ | `load-tests/scenarios/test_difficulty.py` | Script existe; resultados/gráficos **ausentes** |
| 3.17 | Experimentos de carga — fragmentación 1%–50% | ◐ | `load-tests/scenarios/test_fragmentation.py` | Script existe; resultados/gráficos **ausentes** |
| 3.18 | Experimentos de carga — ingreso/egreso nodos GPU | ✗ | No encontrado | No hay script ni documentación de este experimento |
| **ENTREGABLES FORMALES** |
| F.1 | Repositorio público | ? | `pilar3-despliegue/terraform/gke/variables.tf` (github_repository = `MattZander24/TPIntegrador_SDyPP`) | No verificable sin acceso a la red desde este entorno |
| F.2 | Carpeta + README por Pilar (instrucciones + diagrama + decisiones) | ✓ | `pilar1-minero/README.md`, `pilar2-distribuido/README.md`, `pilar3-despliegue/README.md` | Los tres tienen instrucciones, diagramas ASCII y decisiones de diseño |
| F.3 | Informe detallado (métricas, tiempos, gráficos, diagramas, conclusiones, herramientas IA) | ◐ | `docs/informe/` (5 archivos) | Solo cubre Pilar 1 (hits 1,3,4,6 y comparativa parcial). Falta todo Pilar 2 y Pilar 3 |
| F.4 | Video explicativo en el repo | ✗ | `docs/video/.gitkeep` | Directorio existe pero está vacío |
| F.5 | Tests unitarios e integración | ✓ | `pilar2-distribuido/` — 91 tests, 0 fallos | — |
| **SEGURIDAD** |
| S.1 | `.env`/secrets fuera del repo e historial | ✓ | `.gitignore` cubre `.env`, `*.pem`, `*.key` | `terraform.tfvars` **NO está gitignoreado** (contiene solo `project_id`, no credenciales) |
| S.2 | gitleaks en pipeline | ✓ | `ci-checks.yml:7-16` | — |
| S.3 | Zero static keys (Workload Identity / OIDC) | ◐ | `main.tf:233-283` | Grafana admin password `"voxchain"` hardcodeada en `main.tf:321` |
| S.4 | Vault para secretos de infra | ✗ | — | Reemplazado por GCP Secret Manager + External Secrets Operator. Desviación de AGENT.md §6.1 (ver §4) |
| S.5 | Claves privadas individuos nunca en Redis/Vault/backend | ✓ | Búsqueda en todo `pilar2-distribuido/` | No hay código que persista claves privadas |

---

## 3. Hallazgos por Pilar

### Pilar 1 — Minero CPU + GPU CUDA

**Positivo:**
- Cinco programas `.cu` autónomos y bien estructurados, cada uno con su kernel CUDA propio.
- La implementación de `md5.cuh` es propia (no usa librería externa), correcta para el dominio.
- El puente Pilar 1 → Pilar 2 está bien diseñado: `worker_pkg/miner.py` invoca como subproceso el binario CUDA o cae a Python con la misma interfaz CLI, sin reimplementar el hashing en Python.
- El campo `partial_hash_base = law_id + text_hash + voting_window_id + action` es exactamente lo que exige AGENT.md §5.

**Discrepancias en nombres de archivo (README vs disco):**
- `pilar1-minero/README.md` tabla de Hits:
  - Hit #6 → `05_prefix_bench.cu` (no existe en disco; existe `05_brute_force_range.cu`)
  - Hit #7 → `06_brute_force_range.cu` (no existe)
- El archivo `05_brute_force_range.cu` cubre técnicamente Hit #7 (búsqueda por rango). Hit #6 (mediciones por longitud) no tiene `.cu` dedicado; lo cubre el script Python `benchmarks/run_prefix_bench.py` y la doc parcial en `docs/informe/hit6-prefix-bench.md`.

**Comparativa CPU vs GPU incompleta:**
- `docs/informe/cierre-etapa-inicial.md` tiene tiempos reales de GPU (T4 en Colab) pero los tiempos de CPU son estimados teóricos ("~1 MH/s"), no ejecuciones reales del script `brute_force.py`. El enunciado pide "ejecútelos en GPU y en CPU" explícitamente.

### Pilar 2 — Infraestructura distribuida

**Positivo:**
- NCT completamente implementado y testeado: round-robin, ventana activa única, cooldowns, dificultad fija n/n+1, cierre atómico con SETNX en Redis para evitar race conditions entre réplicas.
- Bully mejorado (bully.py) con mini-PoW entre candidatos y adquisición de lease atómica vía Lua script en Redis.
- El `step_down()` del NCT cierra correctamente las colas de trabajo de RabbitMQ (no solo ignora mensajes en memoria), evitando el bug de mensajes robados al round-robin.
- Pool Coordinator completo con keep-alives, subdivisión de rango y liderazgo Redis.

**Réplicas (requisito P1: "al menos 2 réplicas por servicio"):**
- `nct-primary-deployment.yaml:replicas: 1` + `nct-standby-deployment.yaml:replicas: 1` → son dos pods NCT pero en Deployments separados por diseño (active/standby). Técnicamente es 2 instancias del NCT en total, aunque no 2 réplicas del mismo Deployment.
- `redis-statefulset.yaml:replicas: 1` → Redis sin clustering. Punto único de falla.
- `rabbitmq-statefulset.yaml:replicas: 1` → RabbitMQ sin clustering. Punto único de falla.
- `transaction-pool-deployment.yaml:replicas: 1` → TrP sin redundancia (tiene HPA pero mínimo=1).
- `voxchain-api-deployment.yaml:replicas: 2` ✓
- `voxchain-frontend-deployment.yaml:replicas: 2` ✓

**Flujos RabbitMQ adicionales no documentados en AGENT.md:**
- `QUEUE_TAREAS` (TrP → workers) y `QUEUE_KEEPALIVE` (workers → TrP) son flujos internos al pool de minería, no mencionados en AGENT.md §5. AGENT.md §10 exige documentar nuevos flujos. Están declarados en `base.py` y funcionan correctamente, pero AGENT.md no los cubre.

### Pilar 3 — Despliegue, pruebas, escalabilidad

**Positivo:**
- Infraestructura completa y sofisticada: GKE zonal, 2 nodepools con taints, External Secrets Operator sincronizando desde GCP Secret Manager, Workload Identity Federation para CI/CD, kube-prometheus-stack con ServiceMonitors y Grafana dashboard en ConfigMap.
- 4 pipelines CI/CD separados exactamente como exige el enunciado.
- HPA para workers (max 10 réplicas) y pool-miners (max 10 réplicas).
- Cluster k3s separado para GPU workers, conectado por TLS AMQPS.

**Gaps críticos:**
- `pilar3-despliegue/load-tests/scenarios/`: los 3 scripts Python existen y parecen funcionales, pero los archivos CSV de resultados y los gráficos están **ausentes** del repo. No hay evidencia de que se hayan ejecutado contra el cluster productivo.
- El experimento de ingreso/egreso de nodos GPU (DOC.md §3.3 cuarto punto) no tiene script ni documentación.
- `docs/video/` contiene solo `.gitkeep` — el video explicativo no fue subido.

**Namespace inconsistencia:**
- Los manifiestos en `kubernetes/gpu-cluster/` usan `namespace: g-git-push-cv` (que corresponde al cluster k3s). Este nombre es inusual y podría confundir; está documentado en el README de Pilar 3 y parece intencional.

---

## 4. Contradicciones con AGENT.md

| # | Sección AGENT.md | Lo que dice | Lo que hay en el código | Severidad |
|---|---|---|---|---|
| C1 | §6.1 (Vault) | Vault custodia credenciales Redis/RabbitMQ por ambiente | Se usa GCP Secret Manager + External Secrets Operator. Vault no aparece en ningún archivo del repo | Media — cubre el mismo objetivo de seguridad de forma diferente; se debe documentar la decisión en el informe |
| C2 | §10 (flujos RabbitMQ) | "Cualquier nuevo flujo debe documentarse en AGENT.md antes de implementarlo" | `QUEUE_TAREAS` y `QUEUE_KEEPALIVE` (flujos TrP→worker) no están en AGENT.md §5 | Baja — son flujos internos coherentes con el diseño, no cambian la semántica del NCT |
| C3 | §5 (P2 RabbitMQ) | AGENT.md describe 5 flujos exactos | La implementación tiene 7 flujos declarados (3 NCT + 2 Bully + 2 TrP internos). Los 2 extra no contradicen el diseño pero no están documentados | Baja |

No se encontraron contradicciones de reglas de negocio (gobierno): dificultad fija ✓, round-robin ✓, pérdida de ventana ✓, cooldowns ✓, claves privadas nunca en backend ✓.

---

## 5. Gaps críticos (bloqueantes para la entrega)

Ordenados por severidad:

| Prioridad | Gap | Impacto |
|---|---|---|
| 🔴 CRÍTICO | **Video explicativo ausente** (`docs/video/.gitkeep`) | Entregable formal explícito del DOC.md; su ausencia es penalizable |
| 🔴 CRÍTICO | **Informe detallado incompleto** — cubre solo Pilar 1 parcialmente | Faltan: análisis de Pilar 2 (NCT, pool, Bully), Pilar 3 (experimentos), herramientas de IA usadas, conclusiones |
| 🔴 CRÍTICO | **Experimentos de carga sin resultados ni gráficos** — scripts existen pero no se corrieron (o no se commitearon resultados) | DOC.md §3.3 exige análisis cuantitativo de bulk, dificultad y fragmentación |
| 🔴 CRÍTICO | **Experimento ingreso/egreso de nodos GPU ausente** | DOC.md §3.3 cuarto escenario; sin script ni documentación |
| 🟡 ALTO | **Comparativa CPU vs GPU con tiempos CPU reales** (solo estimados teóricos) | Cierre etapa inicial del Pilar 1 exige ejecuciones reales en ambas plataformas |
| 🟡 ALTO | **Redis single instance** (replicas:1, sin clustering) | Punto único de falla; enunciado exige ≥2 réplicas por servicio |
| 🟡 ALTO | **RabbitMQ single instance** (replicas:1) | Idem |
| 🟡 ALTO | **TrP replicas:1** (HPA min=1) | Idem |
| 🟠 MEDIO | **Grafana adminPassword hardcodeado** (`main.tf:321`, valor `"voxchain"`) | Viola "zero static keys"; credencial en IaC trackeada en git |
| 🟠 MEDIO | **Vault no implementado** (desviación de AGENT.md §6.1) | No documentado como decisión en informe |
| 🟠 MEDIO | **Nombres de archivo Pilar 1 inconsistentes** con README (`05_prefix_bench.cu` nombrado pero no existe) | Genera confusión al evaluar |
| 🟢 BAJO | `QUEUE_TAREAS`/`QUEUE_KEEPALIVE` no documentados en AGENT.md | Solo documentación, no afecta funcionalidad |
| 🟢 BAJO | `terraform.tfvars` no gitignoreado (contiene solo `project_id`, no credenciales) | Buena práctica; no expone secretos reales |

---

## 6. Backlog priorizado (deadline 23/06/2026 — 3 días)

### Imprescindible (sin esto no se entrega)

1. **Grabar y subir video explicativo** a `docs/video/`. Duración sugerida: 15–20 min. Cubrir: hits CUDA, arquitectura Pilar 2 (flujos RabbitMQ, NCT, pool, Bully), CI/CD y deploy en GCP.

2. **Completar informe detallado** en `docs/informe/`:
   - Sección Pilar 2: arquitectura, decisiones de diseño, resultado de los 91 tests.
   - Sección Pilar 3: resultados de experimentos (ver punto 3), análisis de escalabilidad.
   - Sección transversal: herramientas de IA usadas y cómo ayudaron.
   - Conclusiones generales.

3. **Ejecutar y commitear resultados de los experimentos de carga** (`pilar3-despliegue/load-tests/scenarios/`):
   - `test_bulk.py --sizes 1,10,100,1000,10000,100000` (si el tiempo no permite 100k, documentar hasta dónde se llegó).
   - `test_difficulty.py` con prefijos 1–8.
   - `test_fragmentation.py` con fragmentaciones 1%–50%.
   - Commitear CSVs y, si hay tiempo, gráficos (matplotlib o similar).

4. **Agregar script para experimento ingreso/egreso de nodos GPU** o documentar cómo simularlo (e.g., scale down/up del worker deployment mientras hay ventana activa).

### Deseable (mejora la nota pero no es bloqueante)

5. **Medir tiempos CPU reales** en `docs/informe/cierre-etapa-inicial.md` ejecutando `brute_force.py` con los mismos prefijos que se midieron en GPU.

6. **Escalar Redis** a ≥2 instancias (Redis Sentinel o cluster) en `redis-statefulset.yaml`. Alternativa rápida: agregar una réplica de Redis standalone para lectura y documentarlo como limitación conocida.

7. **RabbitMQ mirrored/quorum queue**: agregar `rabbitmq-statefulset.yaml` con `replicas: 3` y política de quorum queue. Si no hay tiempo, documentar como limitación.

8. **Eliminar Grafana adminPassword hardcodeado** de `main.tf:321`: moverlo a un secret de GCP Secret Manager y referenciarlo vía External Secrets.

9. **Documentar en AGENT.md** los flujos `QUEUE_TAREAS` y `QUEUE_KEEPALIVE` como flujos internos del TrP (§5 P5).

10. **Documentar en el informe** la decisión de usar GCP Secret Manager en lugar de Vault (como lo exige AGENT.md §6.1).

---

## 7. Anexo de verificación

### Comandos ejecutados

```
git log --oneline --all --stat | head -80
git log --since="2026-06-01" --oneline | wc -l
git branch -a
find . -type f (excluyendo .git, .venv, node_modules, site-packages)
cat AGENT.md, DOC.md
cat pilar1-minero/gpu/src/01_hello.cu ... 05_brute_force_range.cu
cat pilar1-minero/cpu/src/brute_force.py
cat pilar1-minero/gpu/Makefile
cat pilar2-distribuido/common/blockchain/challenge.py
cat pilar2-distribuido/nct-coordinator/nct/coordinator.py
cat pilar2-distribuido/nct-coordinator/nct/bully.py
cat pilar2-distribuido/common/messaging/rabbitmq.py
cat pilar2-distribuido/common/messaging/base.py
cat pilar2-distribuido/pool-coordinator/pool_coordinator/coordinator.py
cat pilar2-distribuido/worker/worker_pkg/worker.py, miner.py
cat pilar2-distribuido/transaction-pool/trp/pool.py
cat pilar3-despliegue/terraform/gke/main.tf
cat pilar3-despliegue/terraform/gke/terraform.tfvars
cat pilar3-despliegue/kubernetes/applications/*-deployment.yaml | grep replicas
cat pilar3-despliegue/kubernetes/infrastructure/redis-statefulset.yaml
cat pilar3-despliegue/kubernetes/infrastructure/rabbitmq-statefulset.yaml
cat pilar3-despliegue/kubernetes/gpu-cluster/worker-hpa.yaml
cat pilar3-despliegue/kubernetes/gpu-cluster/pool-miner-hpa.yaml
cat pilar3-despliegue/load-tests/scenarios/test_bulk.py
cat .github/workflows/ci-checks.yml, 01-infra.yml, ...
cat .gitignore
cat pilar3-despliegue/.secrets/rabbitmq-credentials.yaml
cd pilar2-distribuido && .venv/bin/pytest -v --tb=short (previa instalación de prometheus-client)
```

### No verificable en este entorno

| Elemento | Razón |
|---|---|
| Compilación de `.cu` (Hits 2–7) | nvcc/CUDA Toolkit no instalado en esta máquina |
| Ejecución de los mineros GPU | Sin GPU NVIDIA disponible |
| URL pública del cluster GCP | Sin acceso a la red desde este entorno; el cluster puede estar destruido o pausado por costos |
| Estado real del cluster (pods running, ingress IP) | Idem |
| gitleaks en historial completo | No instalado en el entorno; se verificó el pipeline CI en `.github/workflows/ci-checks.yml` |
| Ejecución de load tests | Requiere cluster GCP activo |
| `pool-coordinator/tests/test_coordinator.py` | El venv no tiene todas las dependencias del pool-coordinator instaladas; se corrió el conjunto principal de 91 tests que sí pasan |

---

*Auditoría realizada el 2026-06-20. Rama auditada: `dev` (commit `f61b3d0`). Integrante que desarrolló el trabajo: Gustavo Contardi (según git config) y MattZander24 (según Terraform variables). 53 commits totales en el repo.*
