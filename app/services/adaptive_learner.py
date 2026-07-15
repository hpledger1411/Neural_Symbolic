"""AdaptiveLearner: turns raw performance aggregates into learning insights.

Thin orchestration layer over PerformanceTracker. Keeps the learning decision
logic separate from transport (routers) and storage (ORM).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.performance_tracker import PerformanceTracker


class AdaptiveLearner:
    def __init__(self, session: AsyncSession) -> None:
        self.tracker = PerformanceTracker(session)

    async def learning_insights(
        self, shop_id: int | None = None, since_days: int = 30
    ) -> dict:
        metrics = await self.tracker.collect(shop_id, since_days)
        # AdaptiveLearner attaches a human-readable recommendation when drift
        # is high or accuracy is poor.
        recommendations: list[str] = []
        if metrics["drift_alert_count"] > 0:
            recommendations.append(
                "Concept drift detected; consider retraining the Forecaster."
            )
        if 0 < metrics["overall_accuracy"] < 0.7:
            recommendations.append(
                "Overall accuracy below threshold; review RulesEngine weights."
            )
        if metrics["worst_performing_products"]:
            worst = metrics["worst_performing_products"][0]
            recommendations.append(
                f"Prioritize product {worst['product_id']} (mean accuracy "
                f"{worst['mean_accuracy']:.2f})."
            )
        return {
            "shop_id": shop_id,
            "since_days": since_days,
            **metrics,
            "recommendations": recommendations,
        }
