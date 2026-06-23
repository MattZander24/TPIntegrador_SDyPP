"""Router for worker and pool management endpoints."""

from __future__ import annotations

import json
import httpx
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header

from voxchain_api.config import config
from voxchain_api.models import (
    PoolHealth,
    PoolPolicy,
    WorkerStatus,
    WorkerSwitchRequest,
)
from voxchain_api.services.redis_reader import RedisReader
from voxchain_api.services.rabbitmq_publisher import RabbitMQPublisher

router = APIRouter(prefix="/api/workers", tags=["workers"])


# Worker admin URLs - these should be configured via environment variables
# Use Docker service names when running in docker-compose
WORKER_ADMIN_URLS = [
    "http://worker-pool-coordinator:9090",
    "http://worker-1:9090",
    "http://worker-2:9090",
]

# Mapping from worker_id to Docker service name for pool coordinators
POOL_COORDINATOR_MAPPING = {
    "pool-coordinator-1": "worker-pool-coordinator",
    "worker-2": "worker-2",  # worker-2 can also become a pool coordinator
}

# Mapping from owner_id to their owned workers
# Updated for the demo scenario where each user corresponds to a node in k3s-cluster
OWNER_WORKERS_MAPPING = {
    "default": ["worker-1", "worker-2", "pool-coordinator-1"],  # For local dev
    "valentin": ["worker-standalone"],
    "gustavo": ["worker-pool-coordinator"],
    "matt": ["worker-pool-miner-1"],
    "profesor1": ["worker-pool-miner-2"],
    "profesor2": ["worker-pool-miner-3"],
}

# Combined list of all registered worker IDs
ALL_REGISTERED_WORKER_IDS = [
    "worker-1", "worker-2", "pool-coordinator-1",
    "worker-standalone", "worker-pool-coordinator",
    "worker-pool-miner-1", "worker-pool-miner-2", "worker-pool-miner-3"
]


def get_owner_id(owner_id: str = Header(None, alias="X-Owner-Id")) -> str:
    """Get the owner ID from the header, default to 'default' for local dev."""
    if owner_id is None:
        return "default"
    return owner_id


def verify_worker_ownership(worker_id: str, owner_id: str) -> bool:
    """Verify that the owner has permission to modify the worker."""
    owned_workers = OWNER_WORKERS_MAPPING.get(owner_id, [])
    if worker_id not in owned_workers:
        raise HTTPException(status_code=403, detail="You do not have permission to modify this worker")
    return True


def get_redis_reader() -> RedisReader:
    return RedisReader()


def get_rabbitmq_publisher() -> RabbitMQPublisher:
    return RabbitMQPublisher()


@router.get("/status", response_model=list[WorkerStatus])
async def get_all_workers_status(redis: RedisReader = Depends(get_redis_reader)):
    """Get status of all registered workers."""
    statuses = []
    redis_client = redis.store.r

    for worker_id in ALL_REGISTERED_WORKER_IDS:
        # 1. Try to read from Redis (for production/remote k3s cluster)
        try:
            status_data = redis_client.get(f"worker:status:{worker_id}")
            if status_data:
                data = json.loads(status_data)
                statuses.append(WorkerStatus(**data))
                continue
        except Exception:
            pass

        # 2. Fallback to HTTP (for local development/backwards compatibility)
        local_url_mapping = {
            "worker-1": "http://worker-1:9090",
            "worker-2": "http://worker-2:9090",
            "pool-coordinator-1": "http://worker-pool-coordinator:9090"
        }
        base_url = local_url_mapping.get(worker_id)
        if base_url:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{base_url}/status", timeout=1.0)
                    if response.status_code == 200:
                        data = response.json()
                        statuses.append(WorkerStatus(**data))
            except Exception:
                continue
    return statuses


@router.get("/{worker_id}/status", response_model=WorkerStatus)
async def get_worker_status(worker_id: str, redis: RedisReader = Depends(get_redis_reader)):
    """Get status of a specific worker by ID."""
    redis_client = redis.store.r

    # 1. Try to read from Redis
    try:
        status_data = redis_client.get(f"worker:status:{worker_id}")
        if status_data:
            data = json.loads(status_data)
            return WorkerStatus(**data)
    except Exception:
        pass

    # 2. Fallback to HTTP
    local_url_mapping = {
        "worker-1": "http://worker-1:9090",
        "worker-2": "http://worker-2:9090",
        "pool-coordinator-1": "http://worker-pool-coordinator:9090"
    }
    base_url = local_url_mapping.get(worker_id)
    if base_url:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{base_url}/status", timeout=1.0)
                if response.status_code == 200:
                    data = response.json()
                    return WorkerStatus(**data)
        except Exception:
            pass

    raise HTTPException(status_code=404, detail="Worker not found")


@router.post("/{worker_id}/switch-mode", response_model=dict)
async def switch_worker_mode(
    worker_id: str, 
    request: WorkerSwitchRequest, 
    owner_id: str = Depends(get_owner_id),
    redis: RedisReader = Depends(get_redis_reader),
    publisher: RabbitMQPublisher = Depends(get_rabbitmq_publisher)
):
    """Switch a worker to a different mode (standalone, pool-coordinator, pool-worker)."""
    verify_worker_ownership(worker_id, owner_id)

    # 1. Publish command to RabbitMQ to notify the worker of the change
    try:
        cmd = {
            "type": "switch_mode",
            "mode": request.target,
            "pool_url": request.pool_url or ""
        }
        publisher.messaging.publish_worker_command(worker_id, cmd)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to publish switch-mode command to RabbitMQ: {e}")
    finally:
        publisher.close()

    # 2. Update expected status in Redis for immediate UI response
    redis_client = redis.store.r
    try:
        status_data = redis_client.get(f"worker:status:{worker_id}")
        status = json.loads(status_data) if status_data else {}
        status["mode"] = request.target
        status["worker_id"] = worker_id
        status["running"] = True
        if request.target == "pool-worker":
            status["pool_url"] = request.pool_url
        elif request.target == "pool-coordinator":
            status["pool_url"] = f"http://{worker_id}:9001"
        else:
            status["pool_url"] = ""
        redis_client.set(f"worker:status:{worker_id}", json.dumps(status), ex=15)
    except Exception:
        pass

    # 3. Fallback/Dual invocation via HTTP for local dev
    local_url_mapping = {
        "worker-1": "http://worker-1:9090",
        "worker-2": "http://worker-2:9090",
        "pool-coordinator-1": "http://worker-pool-coordinator:9090"
    }
    base_url = local_url_mapping.get(worker_id)
    if base_url:
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{base_url}/switch-mode",
                    json=request.model_dump(),
                    timeout=2.0,
                )
        except Exception:
            pass

    return {"ok": True, "mode": request.target}


@router.get("/pool/{pool_id}/health", response_model=PoolHealth)
async def get_pool_health(pool_id: str, redis: RedisReader = Depends(get_redis_reader)):
    """Get health status of a specific pool coordinator."""
    redis_client = redis.store.r

    # 1. Try to read from Redis
    try:
        health_data = redis_client.get(f"pool:health:{pool_id}")
        if health_data:
            data = json.loads(health_data)
            return PoolHealth(**data)
    except Exception:
        pass

    # 2. Fallback to HTTP
    service_name = POOL_COORDINATOR_MAPPING.get(pool_id, pool_id)
    pool_url = f"http://{service_name}:9001"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{pool_url}/health", timeout=2.0)
            if response.status_code == 200:
                return PoolHealth(**response.json())
    except Exception:
        pass
    raise HTTPException(status_code=404, detail="Pool not found")


@router.post("/pool/{pool_id}/policy")
async def set_pool_policy(
    pool_id: str, 
    policy: PoolPolicy, 
    owner_id: str = Depends(get_owner_id),
    redis: RedisReader = Depends(get_redis_reader)
):
    """Set voting policy for a specific pool coordinator."""
    verify_worker_ownership(pool_id, owner_id)

    # 1. Write the policy to Redis so the remote coordinator can read it periodically
    redis_client = redis.store.r
    try:
        redis_client.set(f"pool:policy:{pool_id}", json.dumps(policy.model_dump()))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save policy to Redis: {e}")

    # 2. Fallback to HTTP for local dev
    service_name = POOL_COORDINATOR_MAPPING.get(pool_id, pool_id)
    pool_url = f"http://{service_name}:9001"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{pool_url}/pool/policy",
                json=policy.model_dump(),
                timeout=2.0,
            )
            if response.status_code == 200:
                return response.json()
    except Exception:
        pass

    return {"ok": True, "policy": policy.model_dump()}
