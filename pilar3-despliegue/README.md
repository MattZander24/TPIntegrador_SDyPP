# Pilar 3 — Despliegue, prueba y escalabilidad

## Arquitectura

```
GCP — GKE (Cluster 1)                    GPU Cluster — k3s (Cluster 2)
┌──────────────────────────────┐         ┌───────────────────────────┐
│ Namespace: voxchain          │         │ Namespace: g-git-push-cv  │
│                              │         │                           │
│ RabbitMQ ───LB:5671 (AMQPS)──┼─────────┼──► Worker Deployment      │
│ Redis (interno)              │ TLS     │   - KEDA ScaledObject     │
│ NCT primary + standby        │ self-   │   - HPA (max 10)          │
│ TrP                          │ signed  │   - GPU tolerations       │
│ voxchain-api :8000           │         │   - CA cert volume        │
│ voxchain-frontend :443       │         │                           │
└──────────────────────────────┘         └───────────────────────────┘
```

## Guía de setup paso a paso

### Paso 1: Certs TLS autofirmados

```bash
cd pilar3-despliegue
./kubernetes/scripts/generate-certs.sh ./certs
```

Esto genera:
- `certs/ca.crt` → para workers GPU y KEDA
- `certs/rabbitmq-cert.pem` + `certs/rabbitmq-key.pem` → para RabbitMQ

### Paso 2: Subir secrets a GCP Secret Manager

```bash
gcloud secrets create rabbitmq-user --data-file=<(echo -n "voxchain-worker")
gcloud secrets create rabbitmq-pass --data-file=<(echo -n "CHANGE_ME")
gcloud secrets create rabbitmq-tls-crt --data-file=./certs/rabbitmq-cert.pem
gcloud secrets create rabbitmq-tls-key --data-file=./certs/rabbitmq-key.pem
gcloud secrets create rabbitmq-ca-crt --data-file=./certs/ca.crt
```

### Paso 3: Terraform — Crear cluster GKE

```bash
cd pilar3-despliegue/terraform/gke
cp terraform.tfvars.example terraform.tfvars
# Editar terraform.tfvars si es necesario
tofu init
tofu plan    # Revisar lo que va a crear
tofu apply   # ~15 min, crea VPC + GKE + nodepools + ESO + Artifact Registry + kube-prometheus-stack
```

El Terraform también despliega **kube-prometheus-stack** (Prometheus + Grafana + Alertmanager)
en el namespace `monitoring`. Grafana viene con:
- Admin password: `voxchain`
- Ingress en `grafana.voxchain.local` (requiere configuración de DNS o editar hosts)
- PVC de 10Gi para dashboards persistentes

Al final, correr `tofu output` para obtener:
- `artifact_registry` (URL para las imágenes Docker)
- `get_credentials` (comando kubectl)

### Paso 4: Configurar GitHub Actions Secrets

| Secret | Valor |
|--------|-------|
| `GCP_WIF_PROVIDER` | `projects/.../locations/global/workloadIdentityPools/github-actions/providers/github-provider` (de `tofu output`) |
| `GCP_SERVICE_ACCOUNT` | `voxchain-cicd@voxchain.iam.gserviceaccount.com` |
| `K3S_KUBECONFIG` | Contenido de `~/.kube/config` del cluster k3s (base64) |
| `RABBITMQ_USER` | `voxchain-worker` |
| `RABBITMQ_PASS` | El password que usaste en el Paso 2 |
| `RABBITMQ_CA_CERT` | Contenido de `certs/ca.crt` |

### Paso 5: Reemplazar REGISTRY en los deployments

En todos los `*-deployment.yaml` del cluster GCP hay `image: REGISTRY/...`.
Reemplazar `REGISTRY` por el valor de `artifact_registry` del Paso 3.

Ejemplo (si no se hace en CI/CD):
```bash
# southamerica-east1-docker.pkg.dev/voxchain/voxchain-images
find pilar3-despliegue/kubernetes -name "*.yaml" -exec \
  sed -i 's|REGISTRY|southamerica-east1-docker.pkg.dev/voxchain/voxchain-images|g' {} \;
```

### Paso 6: Aplicar manifests al cluster GCP

```bash
# Una vez que tofu apply terminó y tenés credenciales:
gcloud container clusters get-credentials voxchain --region southamerica-east1

kubectl apply -f pilar3-despliegue/kubernetes/namespace.yaml
kubectl apply -f pilar3-despliegue/kubernetes/infrastructure/
kubectl apply -f pilar3-despliegue/kubernetes/applications/
kubectl apply -f pilar3-despliegue/kubernetes/hpa/
kubectl apply -f pilar3-despliegue/kubernetes/monitoring/
```

Verificar:
```bash
kubectl get pods -n voxchain
```

### Paso 7: Instalar KEDA en k3s (GPU cluster)

```bash
# En el cluster k3s:
kubectl apply --server-side -f https://github.com/kedacore/keda/releases/download/v2.14.0/keda-2.14.0.yaml
```

### Paso 8: Desplegar workers en k3s

Conocer la IP del LoadBalancer de RabbitMQ en GCP:
```bash
kubectl get svc rabbitmq-external -n voxchain -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
# → 34.XX.XX.XX
```

En el cluster k3s:
```bash
kubectl create namespace g-git-push-cv

kubectl create configmap worker-config -n g-git-push-cv \
  --from-literal=rabbitmq-host="34.XX.XX.XX"

kubectl create secret generic rabbitmq-ca -n g-git-push-cv \
  --from-file=ca.crt=./certs/ca.crt

kubectl create secret generic rabbitmq-credentials -n g-git-push-cv \
  --from-literal=username="voxchain-worker" \
  --from-literal=password="CHANGE_ME"

kubectl apply -f pilar3-despliegue/kubernetes/gpu-cluster/worker-deployment.yaml
kubectl apply -f pilar3-despliegue/kubernetes/gpu-cluster/worker-hpa.yaml
kubectl apply -f pilar3-despliegue/kubernetes/gpu-cluster/worker-scaledobject.yaml
```

### Paso 9: Ejecutar load tests

```bash
cd pilar3-despliegue/load-tests/scenarios
./run_all.sh http://<FRONTEND_INGRESS_IP> ../resultados
```

### Paso 10: Disparar CI/CD (ya configurado)

Los workflows de GitHub Actions están listos en `.github/workflows/`:
- `ci-checks.yml` → en cada PR (gitleaks + pytest)
- `01-infra.yml` → manual (tofu apply)
- `02-services.yml` → automático al tocar `kubernetes/infrastructure/`
- `03-apps.yml` → automático al tocar `pilar2-distribuido/`
- `04-gpu-workers.yml` → automático al tocar `kubernetes/gpu-cluster/`

## CI/CD diagrama

```
PR → ci-checks (gitleaks + pytest)
              ↓ (merge a main)
    ┌─────────┼──────────────┐
    │         │              │
01-infra   02-services   03-apps      04-gpu-workers
(tofu)    (redis+rmq)   (build+deploy)  (k3s deploy)
```

## Componentes

| Directorio       | Contenido |
|------------------|-----------|
| `kubernetes/`    | Manifiestos K8s (infra, apps, HPA, GPU cluster) |
| `terraform/`     | Infraestructura como código con OpenTofu |
| `load-tests/`    | Pruebas de carga (bulk, dificultad, fragmentación) |
| `.secrets/`      | Ejemplos de secrets (cifrar con SOPS si se usa GitOps) |

## Decisiones de diseño

- OpenTofu declarativo para reproducibilidad
- GKE regional (1 nodo/AZ) para HA del plano de control
- Nodepool `infra` tainted para aislar Redis/RabbitMQ
- Nodepool `apps` con autoscaling para NCT, TrP, API, Frontend
- RabbitMQ con TLS autofirmado (AMQPS puerto 5671) para workers externos
- Workers GPU en k3s separado, conectados vía LoadBalancer externo
- KEDA para autoscaling event-driven de workers (por profundidad de cola RabbitMQ)
- External Secrets Operator en GKE para sincronizar secrets de GCP Secret Manager
- Workload Identity Federation para CI/CD (sin keys estáticas)
- HPA para escalado horizontal de API y TrP por CPU
- **Observabilidad (U5.5)**: kube-prometheus-stack (Prometheus + Grafana + Alertmanager)
  desplegado via Helm en el namespace `monitoring`. Cada servicio expone `/metrics`
  con métricas de aplicación (propuestas, bloques, workers, latencia). ServiceMonitors
  configurados para auto-descubrimiento. Dashboard pre-cargado en ConfigMap.
