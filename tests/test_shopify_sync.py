"""Tests for Shopify sync into the Data Pool (no network; client is faked)."""

from __future__ import annotations

import asyncio

import pytest

from app.services.shopify_sync import ShopifySync

FAKE_PRODUCTS = [
    {
        "id": 101,
        "title": "Widget",
        "handle": "widget",
        "variants": [{"price": "9.99", "inventory_quantity": 3}],
    }
]
FAKE_ORDERS = [{"id": 9001, "total_price": "19.98", "line_items": []}]
FAKE_INVENTORY = [{"inventory_item_id": 555, "available": 12, "location_id": 1}]


@pytest.fixture
def fake_client(monkeypatch):
    from app.services import shopify as shopify_mod

    class FakeClient(shopify_mod.ShopifyClient):
        def fetch_all(self):
            return {
                "products": FAKE_PRODUCTS,
                "orders": FAKE_ORDERS,
                "inventory_levels": FAKE_INVENTORY,
            }

    monkeypatch.setattr(shopify_mod, "ShopifyClient", FakeClient)
    import app.services.shopify_sync as sync_mod

    monkeypatch.setattr(sync_mod, "ShopifyClient", FakeClient)
    return FakeClient


@pytest.fixture(autouse=True)
def _init_legacy_db():
    from app import db

    db.init_db()


def test_sync_all_stores_in_data_pool(engine, fake_client) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.services.data_pool import DataPool

    async def _run():
        sess = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()
        # Seed a shop row in legacy db so product upsert resolves shop_id.
        from app import db

        if not db.fetchone(
            "SELECT id FROM shops WHERE shop_domain = ?", ("fake.myshopify.com",)
        ):
            db.insert("shops", shop_domain="fake.myshopify.com", access_token="tok")
        sync = ShopifySync(sess, "fake.myshopify.com", "tok")
        result = await sync.sync_all()
        pool = DataPool(sess)
        search = await pool.search("shopify")
        return result, search

    result, search = asyncio.run(_run())
    assert result == {"products": 1, "orders": 1, "inventory_levels": 1}
    assert search["counts"]["datasets"] >= 3
    assert search["counts"]["files"] >= 3


def test_webhook_order_ingest(engine, fake_client) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.services.data_pool import DataPool

    async def _run():
        sess = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()
        sync = ShopifySync(sess, "fake.myshopify.com", "tok")
        trace_id = await sync.ingest_order({"id": 42})
        pool = DataPool(sess)
        trace = await pool.get_trace(trace_id)
        return trace_id, trace

    trace_id, trace = asyncio.run(_run())
    assert trace_id == "shopify/order/42"
    assert trace["event"] == "orders/create"
    assert trace["order"]["id"] == 42
