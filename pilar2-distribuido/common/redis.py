"""Utilidad para crear una conexión Redis."""

from __future__ import annotations

import logging

log = logging.getLogger("voxchain.common.redis")


def create_redis(url: str):
    import redis
    r = redis.Redis.from_url(url, decode_responses=True)
    log.info("conectado a Redis (%s)", url)
    return r