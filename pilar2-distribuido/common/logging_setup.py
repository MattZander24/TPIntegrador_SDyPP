"""Logging estructurado en JSON para Prometheus/Grafana (DOC.md: registros).
Cada servicio llama ``setup_logging("nct")`` una vez al arrancar. Escribe a stdout
(JSON, lo recoge Docker / kubectl / Loki) y opcionalmente a un archivo rotativo.

Variables de entorno:
  LOG_DIR        — directorio para archivos rotativos (default ``/var/log/voxchain``)
  LOG_FORMAT     — ``json`` (default) o ``text`` (para desarrollo local)
  LOG_LEVEL      — nivel de logging (default ``INFO``)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

_EXTRA_ATTRS = frozenset({
    "service",
})


class JsonFormatter(logging.Formatter):
    """Formatea cada registro como una línea JSON.

    Campos incluidos:
      - ``timestamp``  ISO 8601 (UTC)
      - ``level``      nivel del log (INFO, WARNING, …)
      - ``logger``     nombre del logger (voxchain.nct, …)
      - ``service``    nombre del servicio (pasado en setup_logging)
      - ``message``    mensaje formateado
      - ``exception``  traceback completo (sólo si hay excepción)
    """

    def __init__(self, service: str = ""):
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "service": self._service,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def _level_from_env() -> int:
    raw = os.getenv("LOG_LEVEL", "INFO").upper()
    return getattr(logging, raw, logging.INFO)


def setup_logging(service_name: str, level: int | None = None) -> logging.Logger:
    log_dir = os.getenv("LOG_DIR", "/var/log/voxchain")
    log_fmt = os.getenv("LOG_FORMAT", "json")
    effective_level = level if level is not None else _level_from_env()

    root = logging.getLogger()
    root.setLevel(effective_level)

    for h in list(root.handlers):
        root.removeHandler(h)

    if log_fmt == "json":
        formatter: logging.Formatter = JsonFormatter(service=service_name)
    else:
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s"
        )

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    root.addHandler(stream)

    try:
        os.makedirs(log_dir, exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, f"{service_name}.log"),
            maxBytes=5 * 1024 * 1024, backupCount=3,
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        root.warning(
            "LOG_DIR %s no escribible; sólo stdout",
            log_dir,
        )

    return logging.getLogger(service_name)
