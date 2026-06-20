#!/usr/bin/env bash
set -euo pipefail

OUT="${1:-./certs}"
mkdir -p "$OUT"

CA_KEY="$OUT/ca-key.pem"
CA_CERT="$OUT/ca-cert.pem"
SERVER_KEY="$OUT/server-key.pem"
SERVER_CSR="$OUT/server.csr"
SERVER_CERT="$OUT/server-cert.pem"

openssl genrsa -out "$CA_KEY" 4096

openssl req -x509 -new -nodes -key "$CA_KEY" -sha256 -days 3650 \
  -out "$CA_CERT" \
  -subj "/CN=VoxChain CA"

openssl genrsa -out "$SERVER_KEY" 2048

openssl req -new -key "$SERVER_KEY" -out "$SERVER_CSR" \
  -subj "/CN=rabbitmq.voxchain.svc.cluster.local"

cat > "$OUT/san.ext" <<EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage=digitalSignature,nonRepudiation,keyEncipherment,dataEncipherment
extendedKeyUsage=serverAuth,clientAuth
subjectAltName=@alt_names

[alt_names]
DNS.1 = rabbitmq.voxchain.svc.cluster.local
DNS.2 = rabbitmq
DNS.3 = localhost
DNS.4 = *.voxchain.svc.cluster.local
IP.1 = 127.0.0.1
EOF

openssl x509 -req -in "$SERVER_CSR" -CA "$CA_CERT" -CAkey "$CA_KEY" \
  -CAcreateserial -out "$SERVER_CERT" -days 3650 -sha256 \
  -extfile "$OUT/san.ext"

cp "$CA_CERT" "$OUT/ca.crt"
cp "$SERVER_CERT" "$OUT/rabbitmq-cert.pem"
cp "$SERVER_KEY" "$OUT/rabbitmq-key.pem"

rm -f "$SERVER_CSR" "$OUT/san.ext" "$OUT/ca-cert.srl"

echo "Certs generated in $OUT"
echo "  ca.crt              → confiar en clientes externos (workers GPU)"
echo "  rabbitmq-cert.pem   → server cert para RabbitMQ"
echo "  rabbitmq-key.pem    → server key para RabbitMQ"
