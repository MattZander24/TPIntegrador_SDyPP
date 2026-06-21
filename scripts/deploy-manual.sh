#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────────
# deploy-manual.sh — Despliegue manual completo a GKE y/o k3s
# ─────────────────────────────────────────────────────────────────
#
# Requisitos:
#   - docker, gcloud, kubectl instalados
#   - `gcloud auth login` ejecutado (con acceso al proyecto voxchain)
#   - Contextos k3s configurados según corresponda:
#       valentin@k3s-cluster, gustavo@k3s-cluster, SDyPP-2026-GCP-cluster
#
# Uso:
#   ./scripts/deploy-manual.sh                              # GKE + k3s (cluster=valentin)
#   ./scripts/deploy-manual.sh --gke                        # solo GKE
#   ./scripts/deploy-manual.sh --k3s [--cluster <nombre>]   # solo k3s
#
# Clusters disponibles para --k3s:
#   valentin    → valentin@k3s-cluster    (default)
#   gustavo     → gustavo@k3s-cluster
#   profesores  → SDyPP-2026-GCP-cluster
#
# Lo que hace cada modo:
#
# --gke:
#   1. Build & push de todas las imágenes (nct, trp, api, frontend,
#      worker, pool-coordinator) a Artifact Registry.
#   2. kubectl set image para los deployments con deploy: true.
#   3. kubectl apply -f de infra/, applications/, hpa/, monitoring/.
#   4. Verifica rollout de cada deployment.
#
# --k3s:
#   1. Obtiene credenciales RabbitMQ desde GCP Secret Manager.
#   2. Obtiene IP del LoadBalancer de RabbitMQ desde GKE.
#   3. Crea/actualiza ConfigMap worker-config y secrets en k3s.
#   4. Aplica manifests: worker, pool-coordinator, pool-miner, HPAs.
#   5. Verifica rollout de cada deployment.
#
# --all (default): ejecuta --gke primero, luego --k3s.
#
# Los secrets (rabbitmq-user, rabbitmq-pass, rabbitmq-ca-crt) se
# obtienen automáticamente desde Secret Manager — no requiere env vars.
# ─────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

REGION="southamerica-east1"
ZONE="${REGION}-a"
PROJECT_ID="voxchain"
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/voxchain-images"
GKE_CTX="gke_${PROJECT_ID}_${ZONE}_voxchain"
NAMESPACE_GKE="voxchain"
NAMESPACE_K3S="g-git-push-cv"

# Map de nombres de cluster → contexto kubectl
declare -A K3S_CONTEXTS
K3S_CONTEXTS[valentin]="valentin@k3s-cluster"
K3S_CONTEXTS[gustavo]="gustavo@k3s-cluster"
K3S_CONTEXTS[profesores]="SDyPP-2026-GCP-cluster"

MODE=""
CLUSTER="valentin"

# ── parse args ───────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --gke) MODE="--gke"; shift ;;
        --k3s) MODE="--k3s"; shift ;;
        --all) MODE="--all"; shift ;;
        --cluster) CLUSTER="${2:-valentin}"; shift 2 ;;
        *) die "Argumento desconocido: $1 (usá --gke, --k3s, --all, --cluster)" ;;
    esac
done
MODE="${MODE:---all}"

# Validar cluster
K3S_CTX="${K3S_CONTEXTS[$CLUSTER]:-}"
if [[ -z "$K3S_CTX" ]]; then
    die "Cluster desconocido: '$CLUSTER'. Válidos: ${!K3S_CONTEXTS[*]}"
fi

# ── util ──────────────────────────────────────────────────────
info()  { echo -e "\e[1;34m•\e[0m $*"; }
ok()    { echo -e "\e[1;32m✓\e[0m $*"; }
warn()  { echo -e "\e[1;33m⚠\e[0m $*"; }
die()   { echo -e "\e[1;31m✗\e[0m $*"; exit 1; }

require() {
    command -v "$1" >/dev/null 2>&1 || die "falta $1 — instalalo primero"
}

# ── preflight ─────────────────────────────────────────────────
require docker
require gcloud
require kubectl

if [[ "$MODE" == "--all" || "$MODE" == "--gke" || "$MODE" == "--k3s" ]]; then
    info "Verificando autenticación GCP..."
    gcloud auth print-access-token >/dev/null 2>&1 || \
        die "ejecutá 'gcloud auth login' primero"
    gcloud config set project "$PROJECT_ID" >/dev/null
    ok "GCP autenticado"
fi

# ── fetch secrets from Secret Manager ─────────────────────────
fetch_secrets() {
    info "Obteniendo secrets desde GCP Secret Manager..."
    RABBITMQ_USER=$(gcloud secrets versions access latest \
        --secret=rabbitmq-user --project="$PROJECT_ID" 2>/dev/null)
    RABBITMQ_PASS=$(gcloud secrets versions access latest \
        --secret=rabbitmq-pass --project="$PROJECT_ID" 2>/dev/null)
    RABBITMQ_CA_CERT=$(gcloud secrets versions access latest \
        --secret=rabbitmq-ca-crt --project="$PROJECT_ID" 2>/dev/null)

    if [[ -z "$RABBITMQ_USER" || -z "$RABBITMQ_PASS" ]]; then
        die "No se pudieron obtener rabbitmq-user o rabbitmq-pass de Secret Manager"
    fi
    ok "Secrets obtenidos de Secret Manager"
}

# ── GKE ───────────────────────────────────────────────────────
deploy_gke() {
    info "Conectando a GKE..."
    gcloud container clusters get-credentials voxchain --zone "$ZONE"
    kubectl config use-context "$GKE_CTX" >/dev/null
    ok "Contexto GKE: $GKE_CTX"

    # Build matrix: (name, dockerfile, context, container_name, k8s_name, deploy)
    services=(
        "nct:pilar2-distribuido/nct-coordinator/Dockerfile:.::nct:nct-primary:true"
        "transaction-pool:pilar2-distribuido/transaction-pool/Dockerfile:.::trp:transaction-pool:true"
        "voxchain-api:pilar2-distribuido/voxchain_api/Dockerfile:.::api:voxchain-api:true"
        "voxchain-frontend:pilar2-distribuido/voxchain-frontend/Dockerfile:pilar2-distribuido/voxchain-frontend::frontend:voxchain-frontend:true"
        "worker:pilar2-distribuido/worker/Dockerfile:.::worker:none:false"
        "pool-coordinator:pilar2-distribuido/pool-coordinator/Dockerfile:.::pool-coordinator:none:false"
    )

    for svc in "${services[@]}"; do
        IFS=':' read -r name dockerfile context _ container k8s deploy <<< "$svc"
        echo "---"
        info "Build & push: $name"
        docker build -f "$dockerfile" \
            -t "${REGISTRY}/${name}:latest" \
            -t "${REGISTRY}/${name}:$(git rev-parse --short HEAD)" \
            "$context"
        docker push "${REGISTRY}/${name}:latest"
        docker push "${REGISTRY}/${name}:$(git rev-parse --short HEAD)"
        ok "Imagen $name pusheada"

        if [[ "$deploy" == "true" ]]; then
            info "Deploy: $k8s (container=$container)"
            kubectl set image -n "$NAMESPACE_GKE" \
                "deployment/$k8s" \
                "$container=${REGISTRY}/${name}:$(git rev-parse --short HEAD)" \
                --record
            kubectl rollout status -n "$NAMESPACE_GKE" \
                "deployment/$k8s" --timeout=120s
            ok "$k8s rollout completado"
        fi
    done

    info "Aplicando manifiestos de infraestructura..."
    kubectl apply -f pilar3-despliegue/kubernetes/infrastructure/
    ok "Infraestructura GKE aplicada"

    info "Aplicando manifiestos de aplicaciones..."
    kubectl apply -f pilar3-despliegue/kubernetes/applications/
    ok "Aplicaciones GKE aplicadas"

    info "Aplicando HPA y monitoreo..."
    kubectl apply -f pilar3-despliegue/kubernetes/hpa/ 2>/dev/null || true
    kubectl apply -f pilar3-despliegue/kubernetes/monitoring/ 2>/dev/null || true
    ok "HPA y monitoreo aplicados"

    echo "---"
    kubectl get pods -n "$NAMESPACE_GKE" -o wide
}

# ── k3s ───────────────────────────────────────────────────────
deploy_k3s() {
    fetch_secrets

    info "Conectando a k3s..."
    kubectl config use-context "$K3S_CTX" >/dev/null
    ok "Contexto k3s: $K3S_CTX"

    echo "---"
    info "Aplicando namespace..."
    kubectl apply -f pilar3-despliegue/kubernetes/gpu-cluster/namespace.yaml

    info "Configurando host de RabbitMQ desde GKE..."
    kubectl config use-context "$GKE_CTX" >/dev/null
    RABBITMQ_HOST=$(kubectl get svc -n "$NAMESPACE_GKE" rabbitmq-external \
        -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
    if [[ -z "$RABBITMQ_HOST" ]]; then
        warn "No se pudo obtener IP de RabbitMQ, usando placeholder"
        RABBITMQ_HOST="placeholder.voxchain.local"
    fi
    kubectl config use-context "$K3S_CTX" >/dev/null

    kubectl create configmap worker-config \
        --namespace "$NAMESPACE_K3S" \
        --from-literal=rabbitmq-host="$RABBITMQ_HOST" \
        --dry-run=client -o yaml | kubectl apply -f -
    ok "worker-config creado (RABBITMQ_HOST=$RABBITMQ_HOST)"

    echo "---"
    info "Aplicando secrets desde Secret Manager..."

    kubectl create secret generic rabbitmq-ca \
        --namespace "$NAMESPACE_K3S" \
        --from-literal=ca.crt="${RABBITMQ_CA_CERT}" \
        --dry-run=client -o yaml | kubectl apply -f -

    kubectl create secret generic rabbitmq-credentials \
        --namespace "$NAMESPACE_K3S" \
        --from-literal=username="${RABBITMQ_USER}" \
        --from-literal=password="${RABBITMQ_PASS}" \
        --dry-run=client -o yaml | kubectl apply -f -
    ok "Secrets creados desde Secret Manager"

    echo "---"
    info "Aplicando manifiestos de GPU cluster..."
    for f in worker-deployment worker-hpa \
             pool-coordinator-deployment pool-coordinator-service \
             pool-miner-deployment pool-miner-hpa; do
        kubectl apply -f "pilar3-despliegue/kubernetes/gpu-cluster/${f}.yaml"
    done
    ok "Manifiestos GPU cluster aplicados"

    echo "---"
    info "Verificando rollouts..."
    for deploy in worker pool-coordinator pool-miner; do
        kubectl rollout status -n "$NAMESPACE_K3S" \
            "deployment/$deploy" --timeout=120s || warn "rollout de $deploy no completó"
    done

    echo "---"
    info "Estado final:"
    kubectl get pods -n "$NAMESPACE_K3S" -o wide
}


# ── main ──────────────────────────────────────────────────────
case "$MODE" in
    --all)
        deploy_gke
        echo ""
        deploy_k3s
        ;;
    --gke)
        deploy_gke
        ;;
    --k3s)
        deploy_k3s
        ;;
    *)
        echo "Uso: $0 [--gke | --k3s | --all] [--cluster <nombre>]"
        echo ""
        echo "  --gke              solo GKE (build, push, deploy)"
        echo "  --k3s              solo k3s (usa imágenes ya en registry)"
        echo "  --all              GKE + k3s (default)"
        echo "  --cluster <nombre> cluster k3s destino: valentin (default), gustavo, profesores"
        exit 1
        ;;
esac

echo ""
ok "Despliegue completado"
