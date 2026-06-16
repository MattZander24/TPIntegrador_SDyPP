"""Fixtures compartidas por todos los tests de Pilar 2."""

import fakeredis
import pytest

from common.messaging import InMemoryBus
from common.storage import VoxChainStore


@pytest.fixture
def store():
    """VoxChainStore respaldado por un Redis en memoria (fakeredis)."""
    return VoxChainStore(fakeredis.FakeRedis(decode_responses=True))


@pytest.fixture
def bus():
    """Bus de mensajería en memoria (despacho síncrono)."""
    return InMemoryBus()
