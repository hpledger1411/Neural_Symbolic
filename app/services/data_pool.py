"""Data Pool service: file storage, dataset management, trace storage, search.

Built on top of VirtualDrive (blob storage). The Data Pool is the single
ingress/egress for data flowing through the engine:

    Shopify -> Data Pool -> Forecast -> Rules -> Trace -> Feedback -> Insights

Search matches across stored files and registered datasets by path/name/kind
and free-text over metadata.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import or_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_dataset import Dataset
from app.models_drive import DriveObject
from app.services.virtual_drive import VirtualDrive


class DataPool:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.drive = VirtualDrive(session)

    # --- Files -----------------------------------------------------------
    async def put_file(
        self, path: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> DriveObject:
        return await self.drive.put(path, data, kind="file", content_type=content_type)

    async def get_file(self, path: str) -> bytes | None:
        return await self.drive.get_data(path)

    # --- Traces ----------------------------------------------------------
    async def put_trace(self, trace_id: str, payload: dict) -> DriveObject:
        return await self.drive.put(
            f"traces/{trace_id}.json",
            json.dumps(payload).encode(),
            kind="trace",
            content_type="application/json",
        )

    async def get_trace(self, trace_id: str) -> dict | None:
        data = await self.drive.get_data(f"traces/{trace_id}.json")
        return json.loads(data) if data is not None else None

    # --- Datasets --------------------------------------------------------
    async def register_dataset(
        self, name: str, kind: str, file_path: str, meta: dict | None = None
    ) -> Dataset:
        ds = Dataset(
            name=name,
            kind=kind,
            file_path=file_path,
            meta=json.dumps(meta) if meta else None,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(ds)
        await self.session.commit()
        await self.session.refresh(ds)
        return ds

    async def list_datasets(self, kind: str | None = None) -> list[Dataset]:
        stmt = select(Dataset).order_by(Dataset.created_at.desc())
        if kind is not None:
            stmt = stmt.where(Dataset.kind == kind)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_dataset(self, name: str) -> Dataset | None:
        return await self.session.scalar(select(Dataset).where(Dataset.name == name))

    # --- Search ----------------------------------------------------------
    async def search(self, query: str, limit: int = 50) -> dict:
        """Search files and datasets by path/name/kind and metadata text."""
        q = f"%{query.lower()}%"
        file_stmt = (
            select(DriveObject)
            .where(
                or_(
                    DriveObject.path.ilike(q),
                    DriveObject.kind.ilike(q),
                )
            )
            .order_by(DriveObject.updated_at.desc())
            .limit(limit)
        )
        files = (await self.session.execute(file_stmt)).scalars().all()

        ds_stmt = (
            select(Dataset)
            .where(
                or_(
                    Dataset.name.ilike(q),
                    Dataset.kind.ilike(q),
                    Dataset.meta.ilike(q),
                )
            )
            .order_by(Dataset.created_at.desc())
            .limit(limit)
        )
        datasets = (await self.session.execute(ds_stmt)).scalars().all()

        return {
            "query": query,
            "files": [
                {
                    "path": f.path,
                    "kind": f.kind,
                    "size_bytes": f.size_bytes,
                    "updated_at": f.updated_at.isoformat(),
                }
                for f in files
            ],
            "datasets": [
                {
                    "name": d.name,
                    "kind": d.kind,
                    "file_path": d.file_path,
                    "created_at": d.created_at.isoformat(),
                }
                for d in datasets
            ],
            "counts": {"files": len(files), "datasets": len(datasets)},
        }
