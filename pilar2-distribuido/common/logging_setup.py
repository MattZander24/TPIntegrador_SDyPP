"""Logging estructurado a stdout y a disco (DOC.md: registros en memoria y disco).

Cada servicio llama ``setup_logging("nct")`` una vez al arrancar. Escribe a
stdout (lo recoge Docker / kubectl logs) y a un archivo rotativo dentro del
contenedor (``LOG_DIR``, por defecto ``/var/log/voxchain``).
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def setup_logging(service_name: str, level: int = logging.INFO) -> logging.Logger:
    log_dir = os.getenv("LOG_DIR", "/var/log/voxchain")
    root = logging.getLogger()
    root.setLevel(level)

    # Evita duplicar handlers si se llama más de una vez.
    for h in list(root.handlers):
        root.removeHandler(h)

    formatter = logging.Formatter(_FORMAT)

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
        # Si el directorio no es escribible (p. ej. tests locales), seguimos
        # sólo con stdout en lugar de fallar el arranque del servicio.
        root.warning("LOG_DIR %s no escribible; sólo stdout", log_dir)

    return logging.getLogger(service_name)
