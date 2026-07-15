"""VirtualDrive ORM model.

A persistent store for engine artifacts and state: model weights, RulesEngine
config snapshots, decision-policy versions, and arbitrary blobs. Metadata lives
in PostgreSQL; bytes live on a pluggable backend (local filesystem by default,
object storage later) addressed by ``path``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DriveObject(Base):
    __tablename__ = "drive_objects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    path: Mapped[str] = mapped_column(
        String(512), nullable=False, unique=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    content_type: Mapped[str] = mapped_column(
        String(128), nullable=False, default="application/octet-stream"
    )
    data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
