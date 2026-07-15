"""Async SQLAlchemy engine and session factory for Gbox.

Production targets PostgreSQL (set DATABASE_URL to a postgresql+asyncpg:// URI).
For local dev and tests it falls back to aiosqlite so nothing external is required.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

DEFAULT_URL = "sqlite+aiosqlite:///./gbox.db"
DATABASE_URL = os.getenv("GBOX_DATABASE_URL", DEFAULT_URL)

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an AsyncSession."""
    async with SessionLocal() as session:
        yield session


async def init_models() -> None:
    """Create all tables. Import models so they register on Base.metadata."""
    from app import models_perf, models_drive, models_dataset  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
