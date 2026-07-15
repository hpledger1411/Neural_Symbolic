"""Shops and Shopify sync endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from app import db
from app.models import ShopIn, ProductIn

router = APIRouter(prefix="/shops", tags=["shops"])


@router.post("")
def create_shop(shop: ShopIn):
    sid = db.insert("shops", **shop.model_dump())
    return db.fetchone("SELECT * FROM shops WHERE id = ?", (sid,))


@router.get("")
def list_shops():
    return db.fetchall("SELECT id, shop_domain, scope, installed_at FROM shops")


@router.post("/{shop_id}/sync-products")
def sync_products(shop_id: int):
    shop = db.fetchone(
        "SELECT shop_domain, access_token FROM shops WHERE id = ?", (shop_id,)
    )
    if not shop or not shop["access_token"]:
        return {"error": "shop not found or missing access token"}
    from app.services.shopify import ShopifyClient

    client = ShopifyClient(shop["shop_domain"], shop["access_token"])
    count = client.sync_products_to_db()
    return {"synced": count}
