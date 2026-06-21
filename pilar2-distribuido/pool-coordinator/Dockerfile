FROM python:3.12-slim

WORKDIR /app

COPY pilar2-distribuido /app/pilar2-distribuido
RUN pip install --no-cache-dir -r pilar2-distribuido/requirements.txt

ENV PYTHONPATH=/app/pilar2-distribuido

EXPOSE 8080 9001

CMD ["python", "-m", "pool_coordinator.main"]