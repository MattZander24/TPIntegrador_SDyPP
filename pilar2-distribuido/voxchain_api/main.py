"""Main FastAPI application for voxchain-api."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from voxchain_api.config import config
from voxchain_api.routers import chain, health, laws, windows
from voxchain_api.services.redis_reader import RedisReader

# Lifespan manager for SSE background task
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage lifespan of the application."""
    # Startup
    redis = RedisReader()
    app.state.redis = redis
    app.state.sse_clients = set()

    # Start SSE polling task
    sse_task = asyncio.create_task(sse_polling_task(app))
    app.state.sse_task = sse_task

    yield

    # Shutdown
    sse_task.cancel()
    try:
        await sse_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="VoxChain API",
    description="API Gateway for VoxChain governance blockchain",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(chain.router)
app.include_router(laws.router)
app.include_router(windows.router)
app.include_router(health.router)


async def sse_polling_task(app: FastAPI):
    """Background task that polls Redis for changes and broadcasts to SSE clients."""
    redis = app.state.redis

    # Track previous state
    prev_chain_length = redis.chain_length()
    prev_active_window = redis.get_active_window()
    prev_laws = {law["law_id"]: law.get("status") for law in redis.get_laws()}

    while True:
        try:
            await asyncio.sleep(2)  # Poll every 2 seconds

            # Check for new blocks
            current_chain_length = redis.chain_length()
            if current_chain_length > prev_chain_length:
                # Get the new block(s)
                chain = redis.get_chain()
                new_blocks = chain[prev_chain_length:]
                for block in new_blocks:
                    await broadcast_sse_event(
                        app, "block_added", {"block": block}
                    )
                prev_chain_length = current_chain_length

            # Check for window changes
            current_active_window = redis.get_active_window()
            current_window_id = (
                current_active_window["voting_window_id"] if current_active_window else None
            )
            prev_window_id = (
                prev_active_window["voting_window_id"] if prev_active_window else None
            )

            if current_window_id != prev_window_id:
                if current_active_window and not prev_active_window:
                    await broadcast_sse_event(
                        app, "window_opened", {"window": current_active_window}
                    )
                elif not current_active_window and prev_active_window:
                    await broadcast_sse_event(app, "window_closed", {})
                elif current_active_window and prev_active_window:
                    await broadcast_sse_event(
                        app, "window_opened", {"window": current_active_window}
                    )
                prev_active_window = current_active_window

            # Check for law status changes
            current_laws = {law["law_id"]: law.get("status") for law in redis.get_laws()}
            for law_id, status in current_laws.items():
                if law_id in prev_laws and prev_laws[law_id] != status:
                    await broadcast_sse_event(
                        app, "law_updated", {"law_id": law_id, "status": status}
                    )
            prev_laws = current_laws

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"SSE polling error: {e}")
            await asyncio.sleep(5)  # Wait before retrying


async def broadcast_sse_event(app: FastAPI, event_type: str, data: dict):
    """Broadcast an SSE event to all connected clients."""
    message = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    disconnected = set()
    for client in app.state.sse_clients:
        try:
            await client.put(message)
        except Exception:
            disconnected.add(client)
    # Remove disconnected clients
    app.state.sse_clients -= disconnected


@app.get("/api/events")
async def events_stream():
    """SSE endpoint for real-time events."""
    queue: asyncio.Queue = asyncio.Queue()
    app.state.sse_clients.add(queue)

    async def event_generator():
        try:
            while True:
                message = await queue.get()
                yield message
        except asyncio.CancelledError:
            app.state.sse_clients.discard(queue)
            raise

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "voxchain-api",
        "version": "1.0.0",
        "status": "running",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=config.PORT)
