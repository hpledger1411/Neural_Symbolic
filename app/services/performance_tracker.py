"""PerformanceTracker: aggregate model_performance rows into learning metrics.

Pure aggregation over the SQLAlchemy async session. The AdaptiveLearner consumes
these aggregates to decide what to retrain / re-weight.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_perf import ModelPerformance


class PerformanceTracker:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def overall_accuracy(
        self, shop_id: int | None = None, since_days: int = 30
    ) -> float:
        """Mean accuracy across all evaluated rows in the window.

        Rows without an actual value (not yet evaluated) are excluded. Returns
        0.0 when there is no evaluated data.
        """
        since = datetime.now(timezone.utc) - timedelta(days=since_days)
        stmt = select(func.avg(ModelPerformance.accuracy)).where(
            ModelPerformance.recorded_at >= since,
            ModelPerformance.accuracy.isnot(None),
        )
        if shop_id is not None:
            stmt = stmt.where(ModelPerformance.shop_id == shop_id)
        result = await self.session.scalar(stmt)
        return float(result) if result is not None else 0.0

    async def worst_performing_products(
        self, shop_id: int | None = None, since_days: int = 30, limit: int = 10
    ) -> list[dict]:
        """Products ranked by lowest mean accuracy (most wrong predictions)."""
        since = datetime.now(timezone.utc) - timedelta(days=since_days)
        stmt = (
            select(
                ModelPerformance.product_id,
                func.avg(ModelPerformance.accuracy).label("mean_acc"),
                func.count(ModelPerformance.id).label("n"),
            )
            .where(
                ModelPerformance.recorded_at >= since,
                ModelPerformance.accuracy.isnot(None),
            )
            .group_by(ModelPerformance.product_id)
        )
        if shop_id is not None:
            stmt = stmt.where(ModelPerformance.shop_id == shop_id)
        stmt = stmt.order_by(func.avg(ModelPerformance.accuracy).asc()).limit(limit)
        rows = (await self.session.execute(stmt)).all()
        return [
            {
                "product_id": r.product_id,
                "mean_accuracy": float(r.mean_acc),
                "samples": int(r.n),
            }
            for r in rows
        ]

    async def neural_weight_trend(
        self, shop_id: int | None = None, since_days: int = 30
    ) -> list[dict]:
        """Per-day mean accuracy trend (the 'neural weight' learning curve)."""
        since = datetime.now(timezone.utc) - timedelta(days=since_days)
        stmt = (
            select(
                func.date(ModelPerformance.recorded_at).label("day"),
                func.avg(ModelPerformance.accuracy).label("mean_acc"),
            )
            .where(
                ModelPerformance.recorded_at >= since,
                ModelPerformance.accuracy.isnot(None),
            )
            .group_by(func.date(ModelPerformance.recorded_at))
            .order_by(func.date(ModelPerformance.recorded_at).asc())
        )
        if shop_id is not None:
            stmt = stmt.where(ModelPerformance.shop_id == shop_id)
        rows = (await self.session.execute(stmt)).all()
        return [{"date": str(r.day), "mean_accuracy": float(r.mean_acc)} for r in rows]

    async def drift_alert_count(
        self, shop_id: int | None = None, since_days: int = 30
    ) -> int:
        """Number of rows flagged with a drift_alert in the window."""
        since = datetime.now(timezone.utc) - timedelta(days=since_days)
        stmt = select(func.count(ModelPerformance.id)).where(
            ModelPerformance.recorded_at >= since,
            ModelPerformance.drift_alert.is_(True),
        )
        if shop_id is not None:
            stmt = stmt.where(ModelPerformance.shop_id == shop_id)
        result = await self.session.scalar(stmt)
        return int(result) if result is not None else 0

    async def collect(self, shop_id: int | None = None, since_days: int = 30) -> dict:
        """Run every aggregate and bundle into the insights payload."""
        return {
            "overall_accuracy": await self.overall_accuracy(shop_id, since_days),
            "worst_performing_products": await self.worst_performing_products(
                shop_id, since_days
            ),
            "neural_weight_trend": await self.neural_weight_trend(shop_id, since_days),
            "drift_alert_count": await self.drift_alert_count(shop_id, since_days),
        }
