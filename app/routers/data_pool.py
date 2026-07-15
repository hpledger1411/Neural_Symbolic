"""Data Pool endpoints: files, datasets, traces, search.

Implements the data ingress/egress hub of the engine pipeline:

    Shopify -> Data Pool -> Forecast -> Rules -> Trace -> Feedback -> Insights
"""

from __future__ import annotations

import base64
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.services.data_pool import DataPool

router = APIRouter(prefix="/api/data-pool", tags=["data-pool"])


class FilePut(BaseModel):
    path: str
    data: str  # base64
    content_type: str = "application/octet-stream"


class DatasetPut(BaseModel):
    name: str
    kind: str
    file_path: str
    meta: dict | None = None


class TracePut(BaseModel):
    trace_id: str
    payload: dict


@router.put("/files", response_model=dict)
async def put_file(req: FilePut, session: AsyncSession = Depends(get_session)) -> dict:
    pool = DataPool(session)
    obj = await pool.put_file(req.path, base64.b64decode(req.data), req.content_type)
    return {"path": obj.path, "size_bytes": obj.size_bytes, "kind": obj.kind}


@router.get("/files/{path:path}")
async def get_file(path: str, session: AsyncSession = Depends(get_session)) -> dict:
    pool = DataPool(session)
    data = await pool.get_file(path)
    if data is None:
        raise HTTPException(status_code=404, detail="file not found")
    return {"path": path, "data": base64.b64encode(data).decode()}


@router.post("/datasets", response_model=dict)
async def register_dataset(
    req: DatasetPut, session: AsyncSession = Depends(get_session)
) -> dict:
    pool = DataPool(session)
    ds = await pool.register_dataset(req.name, req.kind, req.file_path, req.meta)
    return {"name": ds.name, "kind": ds.kind, "file_path": ds.file_path}


@router.get("/datasets", response_model=list[dict])
async def list_datasets(
    kind: str | None = Query(default=None), session: AsyncSession = Depends(get_session)
) -> list[dict]:
    pool = DataPool(session)
    datasets = await pool.list_datasets(kind=kind)
    return [
        {
            "name": d.name,
            "kind": d.kind,
            "file_path": d.file_path,
            "meta": json.loads(d.meta) if d.meta else None,
            "created_at": d.created_at.isoformat(),
        }
        for d in datasets
    ]


@router.put("/traces", response_model=dict)
async def put_trace(
    req: TracePut, session: AsyncSession = Depends(get_session)
) -> dict:
    pool = DataPool(session)
    obj = await pool.put_trace(req.trace_id, req.payload)
    return {"trace_id": req.trace_id, "size_bytes": obj.size_bytes}


@router.get("/traces/{trace_id}")
async def get_trace(
    trace_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    pool = DataPool(session)
    trace = await pool.get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="trace not found")
    return {"trace_id": trace_id, "payload": trace}


@router.get("/search", response_model=dict)
async def search(
    q: str = Query(..., description="Search term"),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> dict:
    pool = DataPool(session)
    return await pool.search(q, limit=limit)
