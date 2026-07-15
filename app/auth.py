"""API-key authentication.

Requests must carry ``X-API-Key: <key>`` unless the path is exempt (health
check and Shopify webhooks, which are authenticated by HMAC in production).

Set the expected key via ``GBOX_API_KEY``. When unset, auth is disabled (local
dev / tests) so the suite needs no key.
"""

from __future__ import annotations

import os

from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

API_KEY_ENV = "GBOX_API_KEY"
API_KEY_NAME = "X-API-Key"

_EXEMPT_PREFIXES = ("/health", "/webhooks/")


def _expected_key() -> str | None:
    return os.getenv(API_KEY_ENV) or None


api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


async def require_api_key(
    request: Request,
    api_key: str | None = Security(api_key_header),
) -> str | None:
    """Global dependency: enforce the API key except on exempt paths."""
    path = request.url.path
    if any(path.startswith(p) for p in _EXEMPT_PREFIXES):
        return None
    expected = _expected_key()
    if expected is None:
        return None  # auth disabled when no key configured
    if api_key and api_key == expected:
        return api_key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API key",
        headers={API_KEY_NAME: API_KEY_NAME},
    )
