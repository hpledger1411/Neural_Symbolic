"""FastAPI application entrypoint for Gbox Virtual Environment."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app.auth import require_api_key
from app.db import init_db
from app.database import init_models
from app.routers import shops, ml, learning, decisions, drive, data_pool, shopify_sync


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await init_models()
    yield


app = FastAPI(
    title="Gbox Virtual Environment",
    version="0.1.0",
    lifespan=lifespan,
    dependencies=[Depends(require_api_key)],
)
app.include_router(shops.router)
app.include_router(ml.router)
app.include_router(learning.router)
app.include_router(decisions.router)
app.include_router(drive.router)
app.include_router(data_pool.router)
app.include_router(shopify_sync.router)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
