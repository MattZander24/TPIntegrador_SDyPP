#!/usr/bin/env bash
# run_stress.sh — Runner de la suite de stress tests de VoxChain.
#
# Uso rápido (contra GKE con port-forwards activos):
#   export VOXCHAIN_API_URL=https://<ingress-ip>
#   export KUBECONFIG=~/.kube/config      # cluster GKE
#   bash run_stress.sh                    # corre todos los escenarios
#   bash run_stress.sh --only load        # solo el load test (Locust)
#   bash run_stress.sh --only race        # solo el mining race
#   bash run_stress.sh --only failover    # solo el failover
#   bash run_stress.sh --only soak        # solo el soak test
#
# Variables de entorno clave (ver config.py para la lista completa):
#   VOXCHAIN_API_URL       URL del Ingress de GKE (obligatorio)
#   REDIS_URL              redis://localhost:6379/0 (kubectl port-forward)
#   RABBITMQ_URL           amqp://user:pass@localhost:5672/ (kubectl port-forward)
#   K8S_NAMESPACE          namespace de Kubernetes (default: voxchain)
#   NCT_PRIMARY_LABEL      label selector del pod NCT primary
#   LOCUST_USERS           usuarios concurrentes en el load test (default: 20)
#   LOCUST_SPAWN_RATE      tasa de spawn (default: 2)
#   LOCUST_RUN_TIME        duración del load test (default: 5m)
#   SOAK_DURATION_SECONDS  duración del soak test (default: 1800)
#   RACE_CONCURRENT_WORKERS workers en el mining race (default: 30)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ONLY=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --only) ONLY="$2"; shift 2 ;;
    *) echo "Opción desconocida: $1"; exit 1 ;;
  esac
done

RESULTS_DIR="stress-results"
mkdir -p "$RESULTS_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
PASS=0; FAIL=0

run_scenario() {
  local name="$1"; shift
  local cmd=("$@")
  echo -e "\n${YELLOW}━━━ $name ━━━${NC}"
  if "${cmd[@]}"; then
    echo -e "${GREEN}✓ $name PASSED${NC}"
    ((PASS++)) || true
  else
    echo -e "${RED}✗ $name FAILED${NC}"
    ((FAIL++)) || true
  fi
}

# ── Verificar prerequisitos ──────────────────────────────────────────────
echo "Verificando prerequisitos..."

if [[ -z "${VOXCHAIN_API_URL:-}" ]]; then
  echo -e "${RED}ERROR: VOXCHAIN_API_URL no está definida.${NC}"
  echo "       export VOXCHAIN_API_URL=https://<tu-ingress-ip>"
  exit 1
fi

if ! python3 -c "import locust" 2>/dev/null; then
  echo -e "${YELLOW}AVISO: locust no instalado. Instalando...${NC}"
  pip install locust --quiet
fi

if ! python3 -c "import requests" 2>/dev/null; then
  pip install requests --quiet
fi

echo -e "${GREEN}✓ Prerequisitos OK${NC}"
echo "  API_URL: $VOXCHAIN_API_URL"
echo "  REDIS:   ${REDIS_URL:-no configurado (se usará HTTP metrics)}"
echo "  RMQ:     ${RABBITMQ_URL:-no configurado (race test requiere port-forward)}"

# ── Escenario 1 — Load test (Locust) ────────────────────────────────────
if [[ -z "$ONLY" || "$ONLY" == "load" ]]; then
  run_scenario "Load Test (Locust)" \
    locust \
      -f locustfile.py \
      --headless \
      --users "${LOCUST_USERS:-20}" \
      --spawn-rate "${LOCUST_SPAWN_RATE:-2}" \
      --run-time "${LOCUST_RUN_TIME:-5m}" \
      --host "$VOXCHAIN_API_URL" \
      --csv "$RESULTS_DIR/locust" \
      --html "$RESULTS_DIR/locust_report.html" \
      --only-summary
fi

# ── Escenario 2 — Mining race ────────────────────────────────────────────
if [[ -z "$ONLY" || "$ONLY" == "race" ]]; then
  if [[ -z "${RABBITMQ_URL:-}" ]]; then
    echo -e "${YELLOW}⚠ RABBITMQ_URL no definido — skipping mining race.${NC}"
    echo "  Ejecutar: kubectl port-forward svc/rabbitmq 5672:5672 -n ${K8S_NAMESPACE:-voxchain}"
  else
    run_scenario "Mining Race (atomicidad concurrente)" \
      python3 scenarios/mining_race.py \
        --api-url "$VOXCHAIN_API_URL" \
        --rmq-url "$RABBITMQ_URL" \
        --workers "${RACE_CONCURRENT_WORKERS:-30}" \
        --n-zeros 1
  fi
fi

# ── Escenario 3 — Failover under load ───────────────────────────────────
if [[ -z "$ONLY" || "$ONLY" == "failover" ]]; then
  if ! kubectl cluster-info &>/dev/null; then
    echo -e "${YELLOW}⚠ kubectl no configurado — skipping failover test.${NC}"
  else
    run_scenario "Failover under Load (NCT)" \
      python3 scenarios/failover_under_load.py \
        --api-url "$VOXCHAIN_API_URL" \
        --namespace "${K8S_NAMESPACE:-voxchain}" \
        --nct-label "${NCT_PRIMARY_LABEL:-app=nct-coordinator,nct-mode=primary}"
  fi
fi

# ── Escenario 5 — Soak test ──────────────────────────────────────────────
if [[ -z "$ONLY" || "$ONLY" == "soak" ]]; then
  run_scenario "Soak Test (${SOAK_DURATION_SECONDS:-1800}s)" \
    python3 scenarios/soak.py \
      --api-url "$VOXCHAIN_API_URL" \
      ${REDIS_URL:+--redis-url "$REDIS_URL"} \
      --duration "${SOAK_DURATION_SECONDS:-1800}" \
      --output-dir "$RESULTS_DIR"
fi

# ── Resumen final ────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "RESUMEN: ${GREEN}$PASS PASSED${NC}  ${RED}$FAIL FAILED${NC}"
echo "Resultados en: $SCRIPT_DIR/$RESULTS_DIR/"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

[[ $FAIL -eq 0 ]]
