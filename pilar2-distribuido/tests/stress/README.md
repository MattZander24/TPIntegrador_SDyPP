# VoxChain — Suite de Stress Tests

Tests de carga, estrés, soak y chaos diseñados para ejecutarse contra el cluster
GKE real. Cada escenario evalúa sus resultados contra SLOs definidos y genera un
reporte JSON + CSV con veredicto `PASS/FAIL`.

---

## Prerequisitos

```bash
# 1. Instalar dependencias Python
pip install locust requests pika

# 2. Configurar credenciales del cluster GKE
gcloud container clusters get-credentials <cluster-name> \
  --zone southamerica-east1-a --project <project-id>

# 3. Port-forwards (una terminal por forward):
kubectl port-forward svc/redis    6379:6379 -n voxchain
kubectl port-forward svc/rabbitmq 5672:5672 -n voxchain
```

---

## Configuración

Todas las variables se leen del entorno. Las más importantes:

| Variable | Default | Descripción |
|---|---|---|
| `VOXCHAIN_API_URL` | `http://localhost:8000` | URL del Ingress GKE (**obligatorio**) |
| `REDIS_URL` | `redis://localhost:6379/0` | Para métricas directas (port-forward) |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | Para mining race (port-forward) |
| `K8S_NAMESPACE` | `voxchain` | Namespace de Kubernetes |
| `NCT_PRIMARY_LABEL` | `app=nct-coordinator,nct-mode=primary` | Label selector del NCT primary |
| `LOCUST_USERS` | `20` | Usuarios concurrentes en load test |
| `LOCUST_RUN_TIME` | `5m` | Duración del load test |
| `SOAK_DURATION_SECONDS` | `1800` | Duración del soak (30 min) |
| `RACE_CONCURRENT_WORKERS` | `30` | Workers en el mining race |
| `USE_SIGNATURES` | `false` | Firmar propuestas con ECDSA (overhead real) |
| `SLO_P95_MS` | `500` | Umbral P95 latencia (ms) |
| `SLO_ERROR_RATE_PCT` | `1.0` | Umbral tasa de error HTTP (%) |
| `SLO_FAILOVER_SECS` | `30` | Umbral tiempo de failover del NCT (s) |

---

## Escenarios

### Escenario 1 — Load Test (`locustfile.py`)

Carga HTTP realista con 3 tipos de usuarios: `ProposalUser`, `ReaderUser`, `PowerUser`.
Evalúa throughput del API, latencia P95 y tasa de errores.

```bash
# Dashboard interactivo en http://localhost:8089
locust -f locustfile.py --host $VOXCHAIN_API_URL

# Headless con CSV
locust -f locustfile.py --headless \
  --users 20 --spawn-rate 2 --run-time 5m \
  --host $VOXCHAIN_API_URL \
  --csv stress-results/locust \
  --html stress-results/locust_report.html
```

También podés seleccionar un solo tipo de usuario:
```bash
locust -f locustfile.py --class-picker --host $VOXCHAIN_API_URL
```

### Escenario 2 — Mining Race (`scenarios/mining_race.py`)

30 workers publican el mismo nonce simultáneamente. Verifica que `window_sealed`
y el CAS Lua de `append_block` garanticen exactamente 1 bloque por ventana.

```bash
# Requiere port-forward de RabbitMQ
python scenarios/mining_race.py --workers 30 --n-zeros 1

# Con más concurrencia (para estresar Redis)
RACE_CONCURRENT_WORKERS=100 python scenarios/mining_race.py
```

**Métrica clave:** `bloques_por_ventana` debe ser exactamente 1.

### Escenario 3 — Failover under Load (`scenarios/failover_under_load.py`)

Mata el NCT primario mientras hay propuestas en vuelo. Mide cuánto tarda
el standby en asumir el liderazgo y si el sistema se recupera solo.

```bash
# Requiere kubectl configurado con acceso al cluster
python scenarios/failover_under_load.py

# Ajustar warm-up si la dificultad es alta
python scenarios/failover_under_load.py --warmup-blocks 1 --proposal-interval 1.0
```

**Métrica clave:** `tiempo_failover_s` < `SLO_FAILOVER_SECS` (30s).

### Escenario 5 — Soak Test (`scenarios/soak.py`)

30 minutos de carga continua a ritmo constante. Detecta memory leaks,
acumulación de colas y degradación de latencia a lo largo del tiempo.

```bash
# Soak corto (5 min) para validar la suite rápido
SOAK_DURATION_SECONDS=300 python scenarios/soak.py

# Soak completo (30 min)
python scenarios/soak.py --duration 1800 --redis-url redis://localhost:6379/0
```

Los snapshots se exportan a `stress-results/soak_metrics_<ts>.csv` y `.json`.

---

## Demo de presentación (5 minutos)

Script unificado para mostrar en la defensa del TP. Corre las 4 fases en
~5 minutos con salida visual en tiempo real: barras de progreso, stats en vivo
y veredicto PASS/FAIL por fase.

```bash
cd tests/stress

# Mínimo (solo API):
export VOXCHAIN_API_URL=https://<ingress-ip>
python demo.py

# Con RabbitMQ (mining race real, requiere port-forward):
python demo.py --rmq-url amqp://guest:guest@localhost:5672/

# Con failover (requiere kubectl + kubeconfig del cluster GKE):
python demo.py --rmq-url amqp://... --nct-label app=nct-coordinator,nct-mode=primary

# Sin failover (para presentación sin kubectl disponible):
python demo.py --skip-failover

# Sin mining race (para presentación sin RabbitMQ disponible):
python demo.py --skip-race
```

**Duración de cada fase:**

| Fase | Duración | Qué muestra |
|---|---|---|
| Health Check | ~10s | Estado baseline del cluster (API, NCT, Redis, workers) |
| Load Test | ~90s | 12 usuarios concurrentes, P50/P95/P99 en tiempo real |
| Mining Race | ~30s | 30 workers, 1 nonce, exactamente 1 bloque |
| Failover NCT | ~90s | Kill pod → standby toma control en < 30s |
| **Total** | **~4 min** | |

---

## Runner completo (CI/CD)

```bash
cd tests/stress

# Todos los escenarios
export VOXCHAIN_API_URL=https://<ingress-ip>
export RABBITMQ_URL=amqp://guest:guest@localhost:5672/
export REDIS_URL=redis://localhost:6379/0
bash run_stress.sh

# Solo un escenario
bash run_stress.sh --only load
bash run_stress.sh --only race
bash run_stress.sh --only failover
bash run_stress.sh --only soak
```

---

## Resultados

Cada escenario genera un archivo en `stress-results/<escenario>_<timestamp>.json`:

```json
{
  "scenario": "mining_race",
  "started_at": "2026-06-23T12:00:00Z",
  "passed": true,
  "checks": [
    {"name": "ventana_sellada", "value": true, "threshold": true, "passed": true},
    {"name": "bloques_por_ventana", "value": 1, "threshold": 1, "passed": true}
  ],
  "extra": {
    "n_workers": 30,
    "nonce": 7,
    "blocks_created": 1
  }
}
```

---

## Cómo interpretar los resultados para defensa

| Escenario | Lo que demuestra |
|---|---|
| **Load test PASS** | El API aguanta carga real bajo SLO de latencia |
| **Mining race PASS** | El guard atómico (`window_sealed` SETNX + CAS Lua) es correcto bajo concurrencia extrema |
| **Failover PASS** | El standby toma el control dentro del SLO sin corrupción de la cadena |
| **Soak PASS** | No hay memory leaks ni degradación sostenida en producción |

Si **Mining race FAIL** con `bloques_por_ventana > 1` → bug de atomicidad crítico (A-04).
Si **Failover FAIL** con `tiempo_failover_s > SLO` → ajustar `HEARTBEAT_TIMEOUT` o `dead_threshold`.
Si **Soak FAIL** con `max_queue_depth > SLO` → los workers no alcanzan al NCT, escalar HPA.
