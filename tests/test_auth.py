"""API-key authentication tests.

When GBOX_API_KEY is set, protected routes require a matching X-API-Key header;
/health and /webhooks/* are exempt. With no key configured, auth is disabled.
"""

from __future__ import annotations

import asyncio
import os

import pytest


@pytest.fixture
def authed_app(monkeypatch):
    monkeypatch.setenv("GBOX_API_KEY", "secret-key")
    import importlib

    from app import auth as auth_mod

    importlib.reload(auth_mod)
    # Reload main so the global dependency picks up the new key.
    import app.main as main_mod

    importlib.reload(main_mod)
    return main_mod.app


@pytest.fixture
def authed_client(authed_app, engine):
    import httpx

    maker = __import__("sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"])
    from app.database import get_session

    session_maker = maker.async_sessionmaker(
        engine, expire_on_commit=False, class_=maker.AsyncSession
    )

    async def _override():
        async with session_maker() as sess:
            yield sess

    authed_app.dependency_overrides[get_session] = _override
    transport = httpx.ASGITransport(app=authed_app)
    ac = httpx.AsyncClient(transport=transport, base_url="http://test")
    yield ac
    authed_app.dependency_overrides.clear()


def test_health_exempt_without_key(authed_client) -> None:
    resp = asyncio.run(authed_client.get("/health"))
    assert resp.status_code == 200


def test_protected_requires_key(authed_client) -> None:
    resp = asyncio.run(authed_client.get("/api/learning/insights"))
    assert resp.status_code == 401


def test_protected_with_valid_key(authed_client) -> None:
    resp = asyncio.run(
        authed_client.get("/api/learning/insights", headers={"X-API-Key": "secret-key"})
    )
    assert resp.status_code == 200


def test_protected_with_wrong_key(authed_client) -> None:
    resp = asyncio.run(
        authed_client.get("/api/learning/insights", headers={"X-API-Key": "nope"})
    )
    assert resp.status_code == 401
