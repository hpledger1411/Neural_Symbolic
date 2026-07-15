"""Async Shopify sync service.

Pulls Products, Orders, and Inventory from a shop and:
  * stores the raw payloads in the Data Pool (files + datasets) so the
    Forecast -> Rules -> Trace -> Feedback -> Insights pipeline has real data,
  * upserts product rows into the legacy ``products`` table (kept for the
    existing Shopify connector behaviour).

Webhook handlers (order creation, inventory change, product update) call the
same ingest paths so live events land in the Data Pool too.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import db
from app.models_dataset import Dataset
from app.services.data_pool import DataPool
from app.services.shopify import ShopifyClient, _first_inventory, _first_price


class ShopifySync:
    def __init__(
        self, session: AsyncSession, shop_domain: str, access_token: str
    ) -> None:
        self.session = session
        self.client = ShopifyClient(shop_domain, access_token)
        self.pool = DataPool(session)

    async def sync_all(self) -> dict:
        """Full pull of products/orders/inventory into the Data Pool."""
        raw = self.client.fetch_all()
        await self._store_payload("products", raw["products"])
        await self._store_payload("orders", raw["orders"])
        await self._store_payload("inventory", raw["inventory_levels"])
        await self._upsert_products(raw["products"])
        return {
            "products": len(raw["products"]),
            "orders": len(raw["orders"]),
            "inventory_levels": len(raw["inventory_levels"]),
        }

    async def ingest_order(self, order: dict) -> str:
        """Webhook: order creation.

        Stores the raw order, registers a dataset row, and immediately scores
        any pending forecasts for the products in this order (closing the
        learning loop with real demand as the actual).
        """
        from app.services.evaluator import Evaluator

        trace_id = f"shopify/order/{order.get('id')}"
        await self.pool.put_trace(trace_id, {"event": "orders/create", "order": order})
        await self._store_payload("orders", [order])

        # Realized demand per product from this order's line items.
        actuals: dict[str, float] = {}
        for li in order.get("line_items", []) or []:
            pid = li.get("product_id")
            if pid is not None:
                actuals[str(pid)] = actuals.get(str(pid), 0.0) + float(
                    li.get("quantity", 0) or 0
                )
        if actuals:
            evaluator = Evaluator(self.session, self.pool)
            for product_id, actual in actuals.items():
                from app.models_perf import ModelPerformance

                row = await self.session.scalar(
                    select(ModelPerformance)
                    .where(
                        ModelPerformance.product_id == product_id,
                        ModelPerformance.accuracy.is_(None),
                    )
                    .order_by(ModelPerformance.recorded_at.desc())
                    .limit(1)
                )
                if row is not None:
                    await evaluator.evaluate_one(row, actual)
            await self.session.commit()
        return trace_id

    async def ingest_inventory(self, level: dict) -> str:
        """Webhook: inventory change."""
        trace_id = f"shopify/inventory/{level.get('inventory_item_id')}"
        await self.pool.put_trace(
            trace_id, {"event": "inventory_levels/update", "level": level}
        )
        await self._store_payload("inventory", [level])
        return trace_id

    async def ingest_product(self, product: dict) -> str:
        """Webhook: product update."""
        trace_id = f"shopify/product/{product.get('id')}"
        await self.pool.put_trace(
            trace_id, {"event": "products/update", "product": product}
        )
        await self._store_payload("products", [product])
        await self._upsert_products([product])
        return trace_id

    async def _store_payload(self, kind: str, items: list[dict]) -> None:
        if not items:
            return
        path = f"shopify/{kind}/{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
        await self.pool.put_file(
            path, json.dumps(items).encode(), content_type="application/json"
        )
        name = f"shopify-{kind}-latest"
        # Upsert dataset row pointing at the latest file.
        existing = await self.session.scalar(
            select(Dataset).where(Dataset.name == name)
        )
        if existing is not None:
            existing.file_path = path
            existing.created_at = datetime.now(timezone.utc)
        else:
            self.session.add(
                Dataset(
                    name=name,
                    kind=f"shopify_{kind}",
                    file_path=path,
                    meta=json.dumps({"count": len(items)}),
                    created_at=datetime.now(timezone.utc),
                )
            )
        await self.session.commit()

    async def _upsert_products(self, products: list[dict]) -> None:
        shop = db.fetchone(
            "SELECT id FROM shops WHERE shop_domain = ?", (self.client.shop_domain,)
        )
        if not shop:
            return
        shop_id = shop["id"]
        for p in products:
            existing = db.fetchone(
                "SELECT id FROM products WHERE shop_id = ? AND shopify_id = ?",
                (shop_id, str(p["id"])),
            )
            vals = dict(
                shop_id=shop_id,
                shopify_id=str(p["id"]),
                title=p.get("title"),
                handle=p.get("handle"),
                price=_first_price(p),
                inventory_qty=_first_inventory(p),
            )
            if existing:
                sets = ", ".join(f"{k} = ?" for k in vals)
                with db._connect() as conn:
                    conn.execute(
                        f"UPDATE products SET {sets}, synced_at = datetime('now') WHERE id = ?",
                        tuple(vals.values()) + (existing["id"],),
                    )
                    conn.commit()
            else:
                db.insert("products", **vals)
