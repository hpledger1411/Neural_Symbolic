"""Minimal Shopify Admin API client (stdlib only).

Uses the Admin REST API with a per-shop access token. Swap for the official
shopify-api-python SDK when pip is available. Handles products sync.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

API_VERSION = "2024-04"


@dataclass
class ShopifyClient:
    shop_domain: str
    access_token: str

    def _url(self, path: str) -> str:
        return f"https://{self.shop_domain}/admin/api/{API_VERSION}/{path}"

    def _request(
        self, path: str, method: str = "GET", body: Optional[dict] = None
    ) -> dict:
        url = self._url(path)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("X-Shopify-Access-Token", self.access_token)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            raise RuntimeError(
                f"Shopify {method} {path} -> {e.code}: {e.read().decode()}"
            )

    def get_products(self, limit: int = 50) -> list[dict]:
        data = self._request(f"products.json?limit={limit}")
        return data.get("products", [])

    def get_orders(self, limit: int = 50, since_days: int = 30) -> list[dict]:
        """Fetch recent orders (created_at_min = since_days ago)."""
        from datetime import datetime, timedelta

        since = (datetime.utcnow() - timedelta(days=since_days)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        data = self._request(
            f"orders.json?limit={limit}&status=any&created_at_min={since}"
        )
        return data.get("orders", [])

    def get_inventory_levels(self, limit: int = 250) -> list[dict]:
        """Fetch inventory levels across locations."""
        data = self._request(f"inventory_levels.json?limit={limit}")
        return data.get("inventory_levels", [])

    def sync_products_to_db(self) -> int:
        """Fetch products and upsert into the local DB. Returns count synced."""
        from app import db

        shop = db.fetchone(
            "SELECT id FROM shops WHERE shop_domain = ?", (self.shop_domain,)
        )
        if not shop:
            raise RuntimeError(f"Unknown shop domain {self.shop_domain}")
        shop_id = shop["id"]
        count = 0
        for p in self.get_products():
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
                db._connect  # keep import
                with db._connect() as conn:
                    conn.execute(
                        f"UPDATE products SET {sets}, synced_at = datetime('now') WHERE id = ?",
                        tuple(vals.values()) + (existing["id"],),
                    )
                    conn.commit()
            else:
                db.insert("products", **vals)
            count += 1
        return count

    def fetch_all(self) -> dict:
        """Pull products, orders, and inventory in one call (for Data Pool sync)."""
        return {
            "products": self.get_products(),
            "orders": self.get_orders(),
            "inventory_levels": self.get_inventory_levels(),
        }


def _first_price(product: dict) -> Optional[float]:
    variants = product.get("variants") or []
    if variants and variants[0].get("price"):
        try:
            return float(variants[0]["price"])
        except ValueError:
            return None
    return None


def _first_inventory(product: dict) -> Optional[int]:
    variants = product.get("variants") or []
    if variants and variants[0].get("inventory_quantity") is not None:
        try:
            return int(variants[0]["inventory_quantity"])
        except ValueError:
            return None
    return None
