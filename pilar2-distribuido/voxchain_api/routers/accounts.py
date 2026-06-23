"""Router for demo account management."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from voxchain_api.models import DemoAccount, ReleaseAccountRequest, ReserveAccountRequest
from voxchain_api.services.redis_reader import RedisReader

router = APIRouter(prefix="/api/accounts", tags=["accounts"])

# Demo accounts configuration - these match the workers in demo-deployments.yaml
DEMO_ACCOUNTS = {
    "valentin": {
        "worker_id": "worker-standalone",
        "mode": "standalone",
        "pubkey": "demo_valentin_pubkey_placeholder",  # TODO: Replace with actual pubkey from worker
    },
    "gustavo": {
        "worker_id": "worker-pool-coordinator",
        "mode": "pool-coordinator",
        "pubkey": "demo_gustavo_pubkey_placeholder",
    },
    "matt": {
        "worker_id": "worker-pool-miner-1",
        "mode": "pool-worker",
        "pubkey": "demo_matt_pubkey_placeholder",
    },
    "profesor1": {
        "worker_id": "worker-pool-miner-2",
        "mode": "pool-worker",
        "pubkey": "demo_profesor1_pubkey_placeholder",
    },
    "profesor2": {
        "worker_id": "worker-pool-miner-3",
        "mode": "pool-worker",
        "pubkey": "demo_profesor2_pubkey_placeholder",
    },
}

REDIS_KEY_PREFIX = "demo_account:"


def get_account_state(redis: RedisReader, username: str) -> Optional[dict]:
    """Get account state from Redis."""
    key = f"{REDIS_KEY_PREFIX}{username}"
    data = redis.store.redis_client.get(key)
    if data:
        import json
        return json.loads(data)
    return None


def set_account_state(redis: RedisReader, username: str, state: dict):
    """Set account state in Redis with TTL (30 minutes)."""
    key = f"{REDIS_KEY_PREFIX}{username}"
    import json
    redis.store.redis_client.setex(key, 1800, json.dumps(state))  # 30 min TTL


@router.get("", response_model=list[DemoAccount])
async def list_accounts():
    """List all demo accounts with their current status."""
    redis = RedisReader()
    accounts = []
    
    for username, config in DEMO_ACCOUNTS.items():
        state = get_account_state(redis, username)
        
        if state and state.get("status") == "occupied":
            account = DemoAccount(
                username=username,
                worker_id=config["worker_id"],
                mode=config["mode"],
                pubkey=config["pubkey"],
                status="occupied",
                occupied_by=state.get("occupied_by"),
                occupied_at=state.get("occupied_at"),
            )
        else:
            account = DemoAccount(
                username=username,
                worker_id=config["worker_id"],
                mode=config["mode"],
                pubkey=config["pubkey"],
                status="available",
            )
        accounts.append(account)
    
    return accounts


@router.post("/reserve")
async def reserve_account(request: ReserveAccountRequest):
    """Reserve a demo account for the current session."""
    redis = RedisReader()
    
    # Validate account exists
    if request.username not in DEMO_ACCOUNTS:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Check current state
    state = get_account_state(redis, request.username)
    
    if state and state.get("status") == "occupied":
        # Check if it's occupied by the same session (idempotent)
        if state.get("occupied_by") == request.session_id:
            return {"status": "already_reserved", "username": request.username}
        
        # Account is occupied by someone else
        raise HTTPException(
            status_code=409, 
            detail="Account is currently occupied by another session"
        )
    
    # Reserve the account
    new_state = {
        "status": "occupied",
        "occupied_by": request.session_id,
        "occupied_at": datetime.now(timezone.utc).isoformat(),
    }
    set_account_state(redis, request.username, new_state)
    
    return {
        "status": "reserved",
        "username": request.username,
        "worker_id": DEMO_ACCOUNTS[request.username]["worker_id"],
        "mode": DEMO_ACCOUNTS[request.username]["mode"],
        "pubkey": DEMO_ACCOUNTS[request.username]["pubkey"],
    }


@router.post("/release")
async def release_account(request: ReleaseAccountRequest):
    """Release a demo account from the current session."""
    redis = RedisReader()
    
    # Validate account exists
    if request.username not in DEMO_ACCOUNTS:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Check current state
    state = get_account_state(redis, request.username)
    
    if not state or state.get("status") != "occupied":
        return {"status": "not_occupied", "username": request.username}
    
    # Verify ownership
    if state.get("occupied_by") != request.session_id:
        raise HTTPException(
            status_code=403,
            detail="You can only release accounts occupied by your session"
        )
    
    # Release the account
    key = f"{REDIS_KEY_PREFIX}{request.username}"
    redis.store.redis_client.delete(key)
    
    return {"status": "released", "username": request.username}


@router.get("/{username}", response_model=DemoAccount)
async def get_account(username: str):
    """Get details of a specific demo account."""
    redis = RedisReader()
    
    if username not in DEMO_ACCOUNTS:
        raise HTTPException(status_code=404, detail="Account not found")
    
    config = DEMO_ACCOUNTS[username]
    state = get_account_state(redis, username)
    
    if state and state.get("status") == "occupied":
        return DemoAccount(
            username=username,
            worker_id=config["worker_id"],
            mode=config["mode"],
            pubkey=config["pubkey"],
            status="occupied",
            occupied_by=state.get("occupied_by"),
            occupied_at=state.get("occupied_at"),
        )
    
    return DemoAccount(
        username=username,
        worker_id=config["worker_id"],
        mode=config["mode"],
        pubkey=config["pubkey"],
        status="available",
    )
