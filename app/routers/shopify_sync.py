"""Shopify sync + webhook endpoints.

- POST /shops/{id}/sync        -> full pull of products/orders/inventory into Data Pool
- POST /webhooks/shopify/orders/create
- POST /webhooks/shopify/inventory_levels/update
- POST /webhooks/shopify/products/update

Webhooks are verified by HMAC in production; here they ingest the JSON body
into the Data Pool and return a trace id.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app import db
from app.database import get_session
from app.services.shopify_sync import ShopifySync

router = APIRouter(tags=["shopify"])


class WebhookBody(BaseModel):
    pass


def _client_for_shop(shop_id: int) -> tuple[int, str, str]:
    shop = db.fetchone(
        "SELECT id, shop_domain, access_token FROM shops WHERE id = ?", (shop_id,)
    )
    if not shop or not shop["access_token"]:
        raise HTTPException(status_code=404, detail="shop not found or missing token")
    return shop["id"], shop["shop_domain"], shop["access_token"]


@router.post("/shops/{shop_id}/sync")
async def sync_shop(shop_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    _, domain, token = _client_for_shop(shop_id)
    sync = ShopifySync(session, domain, token)
    return await sync.sync_all()


@router.post("/webhooks/shopify/orders/create")
async def webhook_order_create(
    request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    body = await request.json()
    shop_domain = request.headers.get("X-Shopify-Shop-Domain", "")
    shop = db.fetchone(
        "SELECT id, access_token FROM shops WHERE shop_domain = ?", (shop_domain,)
    )
    if not shop:
        raise HTTPException(status_code=404, detail="unknown shop domain")
    sync = ShopifySync(session, shop_domain, shop["access_token"])
    trace_id = await sync.ingest_order(body)
    return {"trace_id": trace_id, "event": "orders/create"}


@router.post("/webhooks/shopify/inventory_levels/update")
async def webhook_inventory_update(
    request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    body = await request.json()
    shop_domain = request.headers.get("X-Shopify-Shop-Domain", "")
    shop = db.fetchone(
        "SELECT id, access_token FROM shops WHERE shop_domain = ?", (shop_domain,)
    )
    if not shop:
        raise HTTPException(status_code=404, detail="unknown shop domain")
    sync = ShopifySync(session, shop_domain, shop["access_token"])
    trace_id = await sync.ingest_inventory(body)
    return {"trace_id": trace_id, "event": "inventory_levels/update"}


@router.post("/webhooks/shopify/products/update")
async def webhook_product_update(
    request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    body = await request.json()
    shop_domain = request.headers.get("X-Shopify-Shop-Domain", "")
    shop = db.fetchone(
        "SELECT id, access_token FROM shops WHERE shop_domain = ?", (shop_domain,)
    )
    if not shop:
        raise HTTPException(status_code=404, detail="unknown shop domain")
    sync = ShopifySync(session, shop_domain, shop["access_token"])
    trace_id = await sync.ingest_product(body)
    return {"trace_id": trace_id, "event": "products/update"}
