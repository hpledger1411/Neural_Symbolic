"""Test helpers for seeding model_performance rows."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models_perf import ModelPerformance


async def seed_performances(
    session: AsyncSession,
    rows: list[dict],
    base_time: datetime | None = None,
) -> None:
    """Insert model_performance rows. Each dict may override recorded_at offset."""
    base_time = base_time or datetime.now(timezone.utc)
    objects: list[ModelPerformance] = []
    for i, r in enumerate(rows):
        offset_days = r.pop("offset_days", 0)
        # Space rows by 1 minute so the unique (shop,product,model,time)
        # constraint never collides within a single seed call.
        recorded_at = base_time - timedelta(days=offset_days, minutes=i)
        obj = ModelPerformance(
            shop_id=r.get("shop_id", 1),
            product_id=r.get("product_id", f"p{i}"),
            model_name=r.get("model_name", "forecaster"),
            model_version=r.get("model_version", "v1"),
            predicted_value=r.get("predicted_value", 0.0),
            actual_value=r.get("actual_value"),
            accuracy=r.get("accuracy"),
            is_correct=r.get("is_correct"),
            drift_alert=r.get("drift_alert", False),
            recorded_at=recorded_at,
        )
        objects.append(obj)
    session.add_all(objects)
    await session.commit()
