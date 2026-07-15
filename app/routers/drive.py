"""VirtualDrive endpoints: persistent artifact / state store (Data Pool).

Power Automate can fetch the latest RulesEngine config or push a new model
artifact via these HTTP endpoints. Specific sub-routes are declared BEFORE the
greedy ``/{path:path}`` catch-all so they are not shadowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models_drive import DriveObject
from app.services.virtual_drive import VirtualDrive

router = APIRouter(prefix="/api/drive", tags=["drive"])


class PutRequest(BaseModel):
    path: str
    kind: str
    data: str  # base64-encoded bytes
    content_type: str = "application/octet-stream"


class ObjectMeta(BaseModel):
    id: int
    path: str
    kind: str
    content_type: str
    size_bytes: int
    created_at: str
    updated_at: str


def _meta(obj: DriveObject) -> ObjectMeta:
    return ObjectMeta(
        id=obj.id,
        path=obj.path,
        kind=obj.kind,
        content_type=obj.content_type,
        size_bytes=obj.size_bytes,
        created_at=obj.created_at.isoformat(),
        updated_at=obj.updated_at.isoformat(),
    )


def _b64decode(s: str) -> bytes:
    import base64

    return base64.b64decode(s)


def _b64encode(b: bytes) -> str:
    import base64

    return base64.b64encode(b).decode()


@router.put("", response_model=ObjectMeta)
async def put_object(
    req: PutRequest, session: AsyncSession = Depends(get_session)
) -> ObjectMeta:
    drive = VirtualDrive(session)
    obj = await drive.put(
        path=req.path,
        data=_b64decode(req.data),
        kind=req.kind,
        content_type=req.content_type,
    )
    return _meta(obj)


@router.get("", response_model=list[ObjectMeta])
async def list_objects(
    kind: str | None = Query(default=None), session: AsyncSession = Depends(get_session)
) -> list[ObjectMeta]:
    drive = VirtualDrive(session)
    objs = await drive.list_objects(kind=kind)
    return [_meta(o) for o in objs]


@router.get("/latest/{kind}", response_model=ObjectMeta)
async def latest(kind: str, session: AsyncSession = Depends(get_session)) -> ObjectMeta:
    drive = VirtualDrive(session)
    obj = await drive.latest(kind)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"no object of kind '{kind}'")
    return _meta(obj)


@router.get("/{path:path}/data")
async def get_object_data(
    path: str, session: AsyncSession = Depends(get_session)
) -> dict:
    drive = VirtualDrive(session)
    data = await drive.get_data(path)
    if data is None:
        raise HTTPException(status_code=404, detail="object not found")
    return {
        "path": path,
        "content_type": "application/octet-stream",
        "data": _b64encode(data),
    }


@router.get("/{path:path}", response_model=ObjectMeta)
async def get_object_meta(
    path: str, session: AsyncSession = Depends(get_session)
) -> ObjectMeta:
    drive = VirtualDrive(session)
    obj = await drive.get(path)
    if obj is None:
        raise HTTPException(status_code=404, detail="object not found")
    return _meta(obj)


@router.delete("/{path:path}")
async def delete_object(
    path: str, session: AsyncSession = Depends(get_session)
) -> dict:
    drive = VirtualDrive(session)
    removed = await drive.delete(path)
    if not removed:
        raise HTTPException(status_code=404, detail="object not found")
    return {"deleted": path}
