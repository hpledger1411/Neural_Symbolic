"""Pytest configuration and fixtures for Gbox.

Uses an in-memory aiosqlite database so tests need no external services. The
FastAPI app is exercised through httpx AsyncClient with an overridden async
session dependency. Async setup is driven via asyncio.run (no pytest-asyncio
plugin required). Sessions are created lazily inside the running event loop to
avoid cross-loop binding errors.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base, get_session
from app import (
    models_perf,
    models_drive,
)  # noqa: F401  (register ORM tables on metadata)


@pytest.fixture
def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async def _create():
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create())
    yield eng
    asyncio.run(eng.dispose())


def _maker(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@pytest.fixture
def client(engine):
    import httpx
    from app.main import app

    maker = _maker(engine)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with maker() as sess:
            yield sess

    app.dependency_overrides[get_session] = _override
    transport = httpx.ASGITransport(app=app)
    ac = httpx.AsyncClient(transport=transport, base_url="http://test")
    yield ac
    app.dependency_overrides.clear()
