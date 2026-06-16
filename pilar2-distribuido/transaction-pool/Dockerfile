# Contexto de build = raíz del repo (ver docker-compose.yml).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app:/app/transaction-pool \
    LOG_DIR=/var/log/voxchain

WORKDIR /app

COPY pilar2-distribuido/transaction-pool/requirements.txt /app/transaction-pool/requirements.txt
RUN pip install --no-cache-dir -r /app/transaction-pool/requirements.txt

COPY pilar2-distribuido/common /app/common
COPY pilar2-distribuido/transaction-pool /app/transaction-pool

RUN mkdir -p /var/log/voxchain

CMD ["python", "/app/transaction-pool/main.py"]
