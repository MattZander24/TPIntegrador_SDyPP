# INSTRUCCIONES DE PRUEBA - TPIntegrador_SDyPP

Este documento describe cómo probar el proyecto VoxChain en todos sus ámbitos: local, en la nube, módulos individuales, integración y escalabilidad.

---

## Índice

1. [Requisitos Previos](#requisitos-previos)
2. [Pilar 1 - Minería CPU y GPU CUDA](#pilar-1---minería-cpu-y-gpu-cuda)
3. [Pilar 2 - Infraestructura Distribuida Local](#pilar-2---infraestructura-distribuida-local)
4. [Pilar 3 - Despliegue en la Nube](#pilar-3---despliegue-en-la-nube)
5. [Pruebas de Carga y Escalabilidad](#pruebas-de-carga-y-escalabilidad)
6. [CI/CD Pipeline](#cicd-pipeline)
7. [Monitoreo y Observabilidad](#monitoreo-y-observabilidad)
8. [Troubleshooting](#troubleshooting)

---

## Requisitos Previos

### Para desarrollo local:
- Docker y Docker Compose
- Python 3.10+
- CUDA Toolkit 12+ (para minería GPU nativa)
- Make (para compilar código CUDA)

### Para despliegue en nube:
- Cuenta de Google Cloud Platform con crédito
- gcloud CLI instalado y configurado
- kubectl instalado
- OpenTofu (o Terraform) instalado
- GitHub account con Actions habilitado

---

## Pilar 1 - Minería CPU y GPU CUDA

### 1.1 Pruebas del Minero CPU

El minero CPU está implementado en Python y sirve como baseline para comparaciones.

```bash
cd pilar1-minero/cpu/src

# Ejecutar minería por fuerza bruta
python brute_force.py --hash "5d41402abc4b2a76b9719d911017c592" --prefix "a" --min 0 --max 1000000
```

**Parámetros:**
- `--hash`: Hash objetivo a encontrar
- `--prefix`: Prefijo que debe tener el resultado
- `--min`: Límite inferior del rango de búsqueda
- `--max`: Límite superior del rango de búsqueda

### 1.2 Pruebas del Minero GPU CUDA

El minero GPU está implementado en CUDA C/C++ y ofrece mejor rendimiento para tareas intensivas.

```bash
cd pilar1-minero/gpu

# Compilar y ejecutar cada hit
make 01    # Hello World CUDA
make 02    # Thrust Vectors
make 03    # MD5 Hash de un string
make 04    # Fuerza bruta (hash + cadena → nonce)
make 05    # Métricas por longitud de prefijo
make 06    # Fuerza bruta con límites de rango
```

**Ejemplo de ejecución del hit #4:**
```bash
./build/04_brute_force "5d41402abc4b2a76b9719d911017c592" "hello"
```

### 1.3 Comparativas CPU vs GPU

```bash
cd pilar1-minero/benchmarks

# Ejecutar benchmarks comparativos
python benchmark_comparison.py
```

**Métricas a observar:**
- Throughput (hashes/segundo)
- Tiempo de ejecución para diferentes longitudes de prefijo
- Consumo de recursos (CPU vs GPU)

---

## Pilar 2 - Infraestructura Distribuida Local

### 2.1 Ejecución Local con Docker Compose

Levanta todos los servicios localmente: RabbitMQ, Redis, NCT, Transaction Pool, Workers, API y Frontend.

```bash
cd pilar2-distribuido
docker compose up --build
```

**Servicios que se levantan:**
- RabbitMQ (puertos 5672, 15672)
- Redis (puerto 6379)
- NCT Coordinator (puerto 8081)
- NCT Standby (sin puerto expuesto)
- Transaction Pool (puerto 8082)
- Workers (2 réplicas, sin puerto expuesto)
- voxchain-api (puerto 8000)
- voxchain-frontend (puerto 4200)

### 2.2 Verificación de Health Endpoints

Todos los servicios exponen endpoints de health en formato JSON:

```bash
# NCT Coordinator
curl http://localhost:8081/health
# Respuesta esperada: {"nct":"ok","redis":"ok","rabbitmq":"ok"}

# Transaction Pool
curl http://localhost:8082/health

# RabbitMQ Management UI
# Usuario: guest, Password: guest
http://localhost:15672
```

### 2.3 Propuesta de Ley (Flujo Completo)

```bash
# Proponer una ley desde el coordinator
docker compose run --rm coordinator \
  python /app/scripts/propose_law.py \
  --text "Presupuesto participativo 2026" \
  --author pk-ciudadano-1
```

**Flujo que se ejecuta:**
1. La propuesta se publica en la cola `propuestas`
2. NCT abre una ventana de votación
3. Transaction Pool fragmenta el espacio de nonces
4. Workers compiten por resolver el PoW
5. El primer worker en encontrar el nonce válido publica la respuesta
6. NCT verifica y sella el bloque en Redis
7. El bloque se encadena con el bloque anterior

### 2.4 Pruebas Unitarias e Integración

```bash
cd pilar2-distribuido

# Crear entorno virtual
python -m venv .venv
. .venv/bin/activate  # Linux/Mac
# o
.venv\Scripts\activate  # Windows

# Instalar dependencias
pip install pytest fakeredis redis pika

# Ejecutar todas las pruebas
pytest

# Ejecutar sólo pruebas de integración
pytest -m integration

# Ejecutar con verbosidad
pytest -v
```

**Pruebas disponibles:**
- `test_e2e.py`: Integración extremo a extremo con bus en memoria y fakeredis
- Verifica el flujo completo: propuesta → ventana → fragmentación → minado → sellado
- Valida encadenamiento de bloques
- Prueba vencimiento de ventanas

### 2.5 Verificación del Estado en Redis

```bash
# Conectarse a Redis
docker exec -it voxchain-pilar2-redis-1 redis-cli

# Ver todas las leyes
KEYS law:*

# Ver una ley específica
HGETALL law:ley-presupuesto

# Ver la cadena de bloques
KEYS block:*

# Ver un bloque específico
HGETALL block:1

# Ver ventanas activas
GET active_window

# Ver contadores
GET window_counter
```

---

## Pilar 3 - Despliegue en la Nube

### 3.1 Configuración Inicial

#### Paso 1: Generar Certificados TLS

```bash
cd pilar3-despliegue
./kubernetes/scripts/generate-certs.sh ./certs
```

Esto genera:
- `certs/ca.crt` → para workers GPU y KEDA
- `certs/rabbitmq-cert.pem` + `certs/rabbitmq-key.pem` → para RabbitMQ

#### Paso 2: Subir Secrets a GCP Secret Manager

```bash
gcloud secrets create rabbitmq-user --data-file=<(echo -n "voxchain-worker")
gcloud secrets create rabbitmq-pass --data-file=<(echo -n "CHANGE_ME")
gcloud secrets create rabbitmq-tls-crt --data-file=./certs/rabbitmq-cert.pem
gcloud secrets create rabbitmq-tls-key --data-file=./certs/rabbitmq-key.pem
gcloud secrets create rabbitmq-ca-crt --data-file=./certs/ca.crt
```

#### Paso 3: Crear Cluster GKE con Terraform

```bash
cd pilar3-despliegue/terraform/gke
cp terraform.tfvars.example terraform.tfvars
# Editar terraform.tfvars si es necesario
tofu init
tofu plan
tofu apply
```

**Tiempo estimado:** ~15 minutos

**Recursos creados:**
- VPC en GCP
- Cluster GKE regional
- Nodepools (infra y apps)
- External Secrets Operator
- Artifact Registry
- kube-prometheus-stack (Prometheus + Grafana)

#### Paso 4: Configurar GitHub Actions Secrets

Configurar los siguientes secrets en el repositorio de GitHub:

| Secret | Valor |
|--------|-------|
| `GCP_WIF_PROVIDER | Output de `tofu output` |
| `GCP_SERVICE_ACCOUNT` | `voxchain-cicd@voxchain.iam.gserviceaccount.com` |
| `K3S_KUBECONFIG` | Contenido de `~/.kube/config` del cluster k3s (base64) |
| `RABBITMQ_USER` | `voxchain-worker` |
| `RABBITMQ_PASS` | Password del Paso 2 |
| `RABBITMQ_CA_CERT` | Contenido de `certs/ca.crt` |

#### Paso 5: Aplicar Manifests al Cluster GCP

```bash
# Obtener credenciales del cluster
gcloud container clusters get-credentials voxchain --region southamerica-east1

# Aplicar manifests
kubectl apply -f pilar3-despliegue/kubernetes/namespace.yaml
kubectl apply -f pilar3-despliegue/kubernetes/infrastructure/
kubectl apply -f pilar3-despliegue/kubernetes/applications/
kubectl apply -f pilar3-despliegue/kubernetes/hpa/
kubectl apply -f pilar3-despliegue/kubernetes/monitoring/
```

#### Paso 6: Verificar Despliegue en GCP

```bash
# Ver pods en el namespace voxchain
kubectl get pods -n voxchain

# Ver servicios
kubectl get svc -n voxchain

# Ver logs de un servicio específico
kubectl logs -n voxchain deployment/nct-coordinator -f

# Ver eventos
kubectl get events -n voxchain
```

### 3.2 Despliegue de Workers GPU en k3s

#### Paso 1: Instalar KEDA en k3s

```bash
kubectl apply --server-side -f https://github.com/kedacore/keda/releases/download/v2.14.0/keda-2.14.0.yaml
```

#### Paso 2: Obtener IP del LoadBalancer de RabbitMQ

```bash
kubectl get svc rabbitmq-external -n voxchain -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
```

#### Paso 3: Desplegar Workers en k3s

```bash
# Crear namespace
kubectl create namespace g-git-push-cv

# Crear configmap con la IP de RabbitMQ
kubectl create configmap worker-config -n g-git-push-cv \
  --from-literal=rabbitmq-host="<IP_DEL_LOADBALANCER>"

# Crear secrets
kubectl create secret generic rabbitmq-ca -n g-git-push-cv \
  --from-file=ca.crt=./certs/ca.crt

kubectl create secret generic rabbitmq-credentials -n g-git-push-cv \
  --from-literal=username="voxchain-worker" \
  --from-literal-password="CHANGE_ME"

# Aplicar manifests
kubectl apply -f pilar3-despliegue/kubernetes/gpu-cluster/worker-deployment.yaml
kubectl apply -f pilar3-despliegue/kubernetes/gpu-cluster/worker-hpa.yaml
kubectl apply -f pilar3-despliegue/kubernetes/gpu-cluster/worker-scaledobject.yaml
```

### 3.3 Verificación del Sistema en la Nube

```bash
# Verificar health endpoints en GCP
kubectl get ingress -n voxchain
# Acceder a la IP del Ingress del frontend

# Verificar workers en k3s
kubectl get pods -n g-git-push-cv

# Ver escalado automático
kubectl describe hpa worker-hpa -n g-git-push-cv
kubectl describe scaledobject worker-scaledobject -n g-git-push-cv
```

---

## Pruebas de Carga y Escalabilidad

### 4.1 Escenarios de Prueba

El proyecto incluye tres escenarios de carga en `pilar3-despliegue/load-tests/scenarios/`:

1. **test_bulk.py**: Pruebas con diferentes volúmenes de transacciones (1 a 100,000)
2. **test_difficulty.py**: Pruebas con diferentes dificultades de prefijo (1 a 8 caracteres)
3. **test_fragmentation.py**: Pruebas con diferentes tamaños de fragmentación (1% a 50%)

### 4.2 Ejecución de Pruebas de Carga

```bash
cd pilar3-despliegue/load-tests/scenarios

# Ejecutar todos los escenarios
./run_all.sh http://<FRONTEND_INGRESS_IP> ../resultados

# Ejecutar un escenario específico
python test_bulk.py --url http://<FRONTEND_INGRESS_IP> --output ../resultados/bulk.json
python test_difficulty.py --url http://<FRONTEND_INGRESS_IP> --output ../resultados/difficulty.json
python test_fragmentation.py --url http://<FRONTEND_INGRESS_IP> --output ../resultados/fragmentation.json
```

### 4.3 Análisis de Resultados

Los resultados se guardan en `pilar3-despliegue/load-tests/resultados/`. Para cada escenario se obtienen:

- Tiempos de respuesta
- Throughput (transacciones/segundo)
- Latencia percentiles (p50, p95, p99)
- Tasa de éxito/fallo
- Métricas de escalado (número de pods)

**Gráficos a generar:**
- Comparativa de tiempos vs volumen de transacciones
- Comparativa de tiempos vs dificultad de prefijo
- Comparativa de tiempos vs tamaño de fragmentación
- Escalado de workers vs carga

---

## CI/CD Pipeline

### 5.1 Workflows de GitHub Actions

El proyecto tiene 4 workflows configurados en `.github/workflows/`:

1. **ci-checks.yml**: Se ejecuta en cada PR
   - Gitleaks (detección de secrets)
   - Pytest (pruebas unitarias e integración)

2. **01-infra.yml**: Disparado manualmente
   - Terraform apply para crear infraestructura GKE

3. **02-services.yml**: Automático al modificar `kubernetes/infrastructure/`
   - Despliegue de Redis y RabbitMQ

4. **03-apps.yml**: Automático al modificar `pilar2-distribuido/`
   - Build y deploy de aplicaciones (NCT, TrP, Workers, API, Frontend)

5. **04-gpu-workers.yml**: Automático al modificar `kubernetes/gpu-cluster/`
   - Despliegue de workers GPU en k3s

### 5.2 Ejecución Manual de Workflows

```bash
# Desde GitHub UI:
# 1. Ir a la pestaña "Actions"
# 2. Seleccionar el workflow
# 3. Clic en "Run workflow"
# 4. Seleccionar branch y ejecutar
```

### 5.3 Verificación de CI/CD

```bash
# Ver estado de los workflows
gh run list

# Ver logs de un workflow específico
gh run view <RUN_ID>

# Verificar que los secrets están configurados
gh secret list
```

---

## Monitoreo y Observabilidad

### 6.1 Prometheus y Grafana

El despliegue incluye kube-prometheus-stack en el namespace `monitoring`.

```bash
# Acceder a Grafana
kubectl port-forward -n monitoring svc/grafana 3000:80
# Usuario: admin
# Password: voxchain

# Dashboards disponibles:
# - VoxChain Overview
# - RabbitMQ Metrics
# - Redis Metrics
# - Worker Performance
# - NCT Coordinator
```

### 6.2 Métricas Expuestas por Servicios

Cada servicio expone métricas en `/metrics`:

- **NCT**: Propuestas procesadas, ventanas abiertas/cerradas, bloques sellados
- **Transaction Pool**: Fragmentos publicados, keep-alives recibidos, capacidad trackeada
- **Worker**: Tareas minadas, nonces encontrados, tiempo de minado
- **API**: Requests por endpoint, latencia, tasa de error

### 6.3 Alertas

Alertmanager está configurado con reglas predefinidas para:

- Alta latencia en NCT
- Workers desconectados
- Colas de RabbitMQ saturadas
- Redis con alta latencia
- Pods en estado CrashLoopBackOff

---

## Troubleshooting

### 7.1 Problemas Comunes en Docker Compose Local

**RabbitMQ no inicia:**
```bash
# Limpiar volúmenes y reiniciar
docker compose down -v
docker compose up --build
```

**Workers no se conectan:**
```bash
# Ver logs de workers
docker compose logs worker

# Verificar RabbitMQ
curl http://localhost:15672
# Usuario: guest, Password: guest
```

**Redis pierde datos:**
```bash
# Verificar persistencia
docker exec voxchain-pilar2-redis-1 redis-cli INFO persistence
```

### 7.2 Problemas en GKE

**Pods no inician:**
```bash
# Ver descripción del pod
kubectl describe pod <POD_NAME> -n voxchain

# Ver logs
kubectl logs <POD_NAME> -n voxchain
```

**ImagePullBackOff:**
```bash
# Verificar que la imagen existe en Artifact Registry
gcloud artifacts images list \
  --location=southamerica-east1 \
  --repository=voxchain-images

# Verificar credenciales de Workload Identity
gcloud iam service-accounts get-iam-policy voxchain-cicd@voxchain.iam.gserviceaccount.com
```

### 7.3 Problemas en k3s (Workers GPU)

**Workers no se conectan a RabbitMQ:**
```bash
# Verificar conectividad desde k3s
kubectl run -it --rm debug --image=curlimages/curl -n g-git-push-cv --restart=Never -- \
  curl -v https://<RABBITMQ_IP>:5671

# Verificar certificados
kubectl describe secret rabbitmq-ca -n g-git-push-cv
```

**KEDA no escala:**
```bash
# Verificar ScaledObject
kubectl describe scaledobject worker-scaledobject -n g-git-push-cv

# Verificar métricas de KEDA
kubectl get --raw '/apis/external.metrics.k8s.io/v1beta1/namespaces/g-git-push-cv/rabbitmq-depth'
```

### 7.4 Problemas de Pruebas

**Pytest falla con errores de conexión:**
```bash
# Verificar que RabbitMQ y Redis están corriendo
docker compose ps

# Ejecutar pruebas con más verbosidad
pytest -v -s
```

**Tests de carga fallan:**
```bash
# Verificar que el sistema está accesible
curl http://<FRONTEND_INGRESS_IP>/health

# Verificar logs de API
kubectl logs -n voxchain deployment/voxchain-api -f
```

---

## Checklist de Pruebas Completo

### Pruebas Locales (Pilar 1)
- [ ] Compilar y ejecutar hits CUDA #1-#6
- [ ] Ejecutar minero CPU con diferentes parámetros
- [ ] Comparar rendimiento CPU vs GPU
- [ ] Verificar correctitud de hashes calculados

### Pruebas Locales (Pilar 2)
- [ ] Levantar docker compose exitosamente
- [ ] Verificar health endpoints de todos los servicios
- [ ] Proponer una ley y verificar flujo completo
- [ ] Verificar bloque sellado en Redis
- [ ] Ejecutar pytest (unit + integración)
- [ ] Verificar encadenamiento de bloques

### Pruebas en Nube (Pilar 3)
- [ ] Crear cluster GKE con Terraform
- [ ] Desplegar infraestructura (Redis, RabbitMQ)
- [ ] Desplegar aplicaciones (NCT, TrP, API, Frontend)
- [ ] Configurar workers GPU en k3s
- [ ] Verificar conectividad entre clusters
- [ ] Probar propuesta de ley en producción
- [ ] Verificar escalado automático con KEDA

### Pruebas de Carga
- [ ] Ejecutar test_bulk.py (1 a 100,000 transacciones)
- [ ] Ejecutar test_difficulty.py (prefijos 1-8)
- [ ] Ejecutar test_fragmentation.py (1%-50%)
- [ ] Generar gráficos comparativos
- [ ] Analizar resultados y conclusiones

### CI/CD
- [ ] Verificar workflow ci-checks en PR
- [ ] Ejecutar workflow 01-infra manualmente
- [ ] Verificar despliegue automático de servicios
- [ ] Verificar despliegue automático de apps
- [ ] Verificar despliegue automático de workers GPU

### Monitoreo
- [ ] Acceder a Grafana y ver dashboards
- [ ] Verificar métricas de todos los servicios
- [ ] Verificar alertas configuradas
- [ ] Simular fallo y verificar notificación

---

## Referencias

- [DOC.md](DOC.md) - Documentación completa del proyecto
- [AGENT.md](AGENT.md) - Especificación del agente VoxChain
- [Pilar 1 README](pilar1-minero/README.md) - Minería CPU y GPU
- [Pilar 2 README](pilar2-distribuido/README.md) - Infraestructura distribuida
- [Pilar 3 README](pilar3-despliegue/README.md) - Despliegue en la nube
