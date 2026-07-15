"""Evaluator: close the learning loop by scoring forecasts against actuals.

For each unevaluated ``model_performance`` row (``accuracy IS NULL``), the
Evaluator looks up the realized actual demand for that product and writes back
``accuracy``, ``is_correct`` and ``drift_alert``. Actuals come from:

  * an explicit ``actual`` value (e.g. posted from a Shopify order webhook), or
  * the Data Pool `shopify/orders` payloads aggregated per product.

Accuracy is 1 - relative error, bounded to [0, 1]. A row is flagged
``drift_alert`` when its accuracy drops below ``drift_threshold``. Once rows
are evaluated, ``PerformanceTracker`` / ``AdaptiveLearner`` surface them via
``/api/learning/insights``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_perf import ModelPerformance
from app.services.data_pool import DataPool

CORRECT_TOLERANCE = 0.15  # within 15% of actual => "correct"
DRIFT_THRESHOLD = 0.6  # accuracy below this => concept-drift alert


class Evaluator:
    def __init__(self, session: AsyncSession, pool: DataPool | None = None) -> None:
        self.session = session
        self.pool = pool or DataPool(session)

    async def evaluate_one(
        self, row: ModelPerformance, actual: float | None = None
    ) -> bool:
        """Score a single prediction row. Returns True if it was evaluated."""
        if actual is None:
            actual = await self._actual_for_product(row.product_id)
        if actual is None:
            return False

        predicted = float(row.predicted_value)
        denom = actual if actual != 0 else 1.0
        rel_err = abs(predicted - actual) / abs(denom)
        accuracy = max(0.0, min(1.0, 1.0 - rel_err))

        row.actual_value = actual
        row.accuracy = round(accuracy, 4)
        row.is_correct = rel_err <= CORRECT_TOLERANCE
        row.drift_alert = accuracy < DRIFT_THRESHOLD
        return True

    async def evaluate_pending(self, shop_id: int | None = None) -> int:
        """Evaluate all unevaluated rows. Returns number evaluated."""
        stmt = select(ModelPerformance).where(ModelPerformance.accuracy.is_(None))
        if shop_id is not None:
            stmt = stmt.where(ModelPerformance.shop_id == shop_id)
        rows = (await self.session.execute(stmt)).scalars().all()

        evaluated = 0
        for row in rows:
            if await self.evaluate_one(row):
                evaluated += 1
        if evaluated:
            await self.session.commit()
        return evaluated

    async def _actual_for_product(self, product_id: str) -> float | None:
        """Best-effort actual demand from the most recent shopify/orders dataset."""
        from app.models_dataset import Dataset

        ds = await self.session.scalar(
            select(Dataset).where(Dataset.name == "shopify-orders-latest")
        )
        if ds is None:
            return None
        data = await self.pool.get_file(ds.file_path)
        if data is None:
            return None
        import json

        try:
            orders = json.loads(data)
        except (ValueError, json.JSONDecodeError):
            return None
        return self._aggregate_demand(orders, product_id)

    @staticmethod
    def _aggregate_demand(orders: list[dict], product_id: str) -> float | None:
        """Sum quantity of line items whose product_id matches."""
        total = 0.0
        matched = False
        # Shopify line_items carry product_id; also try a string compare.
        target = str(product_id)
        for order in orders:
            for li in order.get("line_items", []) or []:
                pid = li.get("product_id")
                if pid is not None and str(pid) == target:
                    total += float(li.get("quantity", 0) or 0)
                    matched = True
        return total if matched else None
