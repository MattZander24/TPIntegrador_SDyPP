# Contexto de build = raíz del repo (ver docker-compose.yml) para poder copiar
# tanto el paquete compartido `common` como el código del servicio.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app:/app/voxchain-api \
    LOG_DIR=/var/log/voxchain

WORKDIR /app

COPY pilar2-distribuido/voxchain-api/requirements.txt /app/voxchain-api/requirements.txt
RUN pip install --no-cache-dir -r /app/voxchain-api/requirements.txt

COPY pilar2-distribuido/common /app/common
COPY pilar2-distribuido/voxchain-api /app/voxchain-api

RUN mkdir -p /var/log/voxchain

CMD ["python", "/app/voxchain-api/main.py"]
