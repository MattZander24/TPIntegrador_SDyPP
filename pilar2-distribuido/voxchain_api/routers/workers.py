"""Router for worker and pool management endpoints."""

from __future__ import annotations

import httpx

from fastapi import APIRouter, Depends, HTTPException, Header

from voxchain_api.config import config
from voxchain_api.models import (
    PoolHealth,
    PoolPolicy,
    WorkerStatus,
    WorkerSwitchRequest,
)

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
# In production, this should come from a database or auth service
OWNER_WORKERS_MAPPING = {
    "default": ["worker-1", "worker-2", "pool-coordinator-1"],  # For local dev, all workers belong to default owner
}


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


@router.get("/status", response_model=list[WorkerStatus])
async def get_all_workers_status():
    """Get status of all registered workers."""
    statuses = []
    for base_url in WORKER_ADMIN_URLS:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{base_url}/status", timeout=2.0)
                if response.status_code == 200:
                    data = response.json()
                    statuses.append(WorkerStatus(**data))
        except Exception:
            # Worker may be down or unreachable
            continue
    return statuses


@router.get("/{worker_id}/status", response_model=WorkerStatus)
async def get_worker_status(worker_id: str):
    """Get status of a specific worker by ID."""
    for base_url in WORKER_ADMIN_URLS:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{base_url}/status", timeout=2.0)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("worker_id") == worker_id:
                        return WorkerStatus(**data)
        except Exception:
            continue
    raise HTTPException(status_code=404, detail="Worker not found")


@router.post("/{worker_id}/switch-mode", response_model=dict)
async def switch_worker_mode(
    worker_id: str, 
    request: WorkerSwitchRequest, 
    owner_id: str = Depends(get_owner_id)
):
    """Switch a worker to a different mode (standalone, pool-coordinator, pool-worker)."""
    verify_worker_ownership(worker_id, owner_id)
    for base_url in WORKER_ADMIN_URLS:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{base_url}/status", timeout=2.0)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("worker_id") == worker_id:
                        # Found the worker, now switch its mode
                        # Increased timeout to 15s to allow worker to restart when changing to pool-coordinator
                        switch_response = await client.post(
                            f"{base_url}/switch-mode",
                            json=request.model_dump(),
                            timeout=15.0,
                        )
                        if switch_response.status_code == 200:
                            return switch_response.json()
                        elif switch_response.status_code == 400:
                            raise HTTPException(
                                status_code=400, detail=switch_response.json().get("error")
                            )
        except Exception:
            continue
    raise HTTPException(status_code=404, detail="Worker not found")


@router.get("/pool/{pool_id}/health", response_model=PoolHealth)
async def get_pool_health(pool_id: str):
    """Get health status of a specific pool coordinator."""
    # Map pool_id to Docker service name
    service_name = POOL_COORDINATOR_MAPPING.get(pool_id, pool_id)
    # Pool coordinators expose HTTP on port 9001 by default
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
    owner_id: str = Depends(get_owner_id)
):
    """Set voting policy for a specific pool coordinator."""
    verify_worker_ownership(pool_id, owner_id)
    # Map pool_id to Docker service name
    service_name = POOL_COORDINATOR_MAPPING.get(pool_id, pool_id)
    pool_url = f"http://{service_name}:9001"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{pool_url}/pool/policy",
                json=policy.model_dump(),
                timeout=5.0,
            )
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 400:
                raise HTTPException(
                    status_code=400, detail=response.json().get("error")
                )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
