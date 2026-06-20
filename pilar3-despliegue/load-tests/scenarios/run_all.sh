#!/usr/bin/env bash
set -euo pipefail

API_URL="${1:-http://localhost:8000}"
OUT_DIR="${2:-./resultados}"

mkdir -p "$OUT_DIR"

echo "=== VoxChain — Batería de pruebas de carga ==="
echo "API: $API_URL"
echo "Resultados: $OUT_DIR"
echo ""

echo "--- Bulk ---"
python test_bulk.py --api-url "$API_URL" \
  --sizes "1,10,100,1000" \
  --output "$OUT_DIR/resultados_bulk.csv"
echo ""

echo "--- Dificultad ---"
python test_difficulty.py --api-url "$API_URL" \
  --max-zeros 6 \
  --output "$OUT_DIR/resultados_dificultad.csv"
echo ""

echo "--- Fragmentación ---"
python test_fragmentation.py --api-url "$API_URL" \
  --nonce-space 50000000 \
  --fragments-pct "1,5,10,25,50" \
  --output "$OUT_DIR/resultados_fragmentacion.csv"
echo ""

echo "=== Completado ==="
ls -lh "$OUT_DIR"
