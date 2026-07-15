"""Dataset ORM model for the Data Pool.

A dataset is a named, queryable collection registered in the pool. It points at
one or more stored files (DriveObject paths) and carries free-form metadata
used by search and by the Forecaster for training/evaluation.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(256), nullable=False, unique=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    meta: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
