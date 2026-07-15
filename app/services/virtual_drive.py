"""VirtualDrive service: persistent artifact / state store.

Stores engine artifacts (model weights, rule configs, policy snapshots) as
``DriveObject`` rows. Small blobs are kept inline (``data``); the interface is
backend-agnostic so a future object store can be swapped in without changing
callers. Every write returns a ``path`` that uniquely addresses the object.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_drive import DriveObject


class VirtualDrive:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def put(
        self,
        path: str,
        data: bytes,
        kind: str,
        content_type: str = "application/octet-stream",
    ) -> DriveObject:
        """Write (or overwrite) an object at ``path``."""
        existing = await self.session.scalar(
            select(DriveObject).where(DriveObject.path == path)
        )
        if existing is not None:
            existing.data = data
            existing.kind = kind
            existing.content_type = content_type
            existing.size_bytes = len(data)
            existing.updated_at = datetime.now(timezone.utc)
            obj = existing
        else:
            obj = DriveObject(
                path=path,
                kind=kind,
                content_type=content_type,
                data=data,
                size_bytes=len(data),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)
        return obj

    async def get(self, path: str) -> DriveObject | None:
        return await self.session.scalar(
            select(DriveObject).where(DriveObject.path == path)
        )

    async def get_data(self, path: str) -> bytes | None:
        obj = await self.get(path)
        return obj.data if obj is not None else None

    async def list_objects(self, kind: str | None = None) -> list[DriveObject]:
        stmt = select(DriveObject).order_by(DriveObject.updated_at.desc())
        if kind is not None:
            stmt = stmt.where(DriveObject.kind == kind)
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete(self, path: str) -> bool:
        obj = await self.get(path)
        if obj is None:
            return False
        await self.session.delete(obj)
        await self.session.commit()
        return True

    async def latest(self, kind: str) -> DriveObject | None:
        """Most recently updated object of a given kind (e.g. latest ruleset)."""
        stmt = (
            select(DriveObject)
            .where(DriveObject.kind == kind)
            .order_by(DriveObject.updated_at.desc())
            .limit(1)
        )
        return await self.session.scalar(stmt)
