# Contexto de build = raíz del repo (ver docker-compose.yml). El worker invoca
# el minero de Pilar 1; acá se vendoriza el minero CPU (fallback). El binario
# CUDA no está disponible sin GPU, así que el worker cae a CPU automáticamente.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app:/app/worker \
    LOG_DIR=/var/log/voxchain \
    MINER_CPU_SCRIPT=/app/pilar1-minero/cpu/src/brute_force.py

WORKDIR /app

COPY pilar2-distribuido/worker/requirements.txt /app/worker/requirements.txt
RUN pip install --no-cache-dir -r /app/worker/requirements.txt

COPY pilar2-distribuido/common /app/common
COPY pilar2-distribuido/worker /app/worker
# Minero CPU de Pilar 1 (no se reimplementa; se copia el archivo existente).
COPY pilar1-minero/cpu /app/pilar1-minero/cpu

RUN mkdir -p /var/log/voxchain

CMD ["python", "/app/worker/main.py"]
