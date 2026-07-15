"""Learning insights endpoints (AdaptiveLearner / PerformanceTracker / Evaluator)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.services.adaptive_learner import AdaptiveLearner
from app.services.data_pool import DataPool
from app.services.evaluator import Evaluator

router = APIRouter(prefix="/api/learning", tags=["learning"])


class EvaluateRequest(BaseModel):
    shop_id: int | None = None
    actuals: dict[str, float] | None = None


@router.get("/insights")
async def learning_insights(
    session: AsyncSession = Depends(get_session),
    shop_id: int | None = Query(default=None, description="Filter by shop"),
    since_days: int = Query(
        default=30, ge=1, le=365, description="Lookback window in days"
    ),
) -> dict:
    """Aggregate the model_performance table into learning insights.

    Returns overall_accuracy, worst_performing_products, neural_weight_trend,
    drift_alert count, plus adaptive recommendations. Only rows that have been
    evaluated (actuals scored) contribute to accuracy.
    """
    learner = AdaptiveLearner(session)
    return await learner.learning_insights(shop_id=shop_id, since_days=since_days)


@router.post("/evaluate")
async def evaluate(
    req: EvaluateRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    """Score pending forecasts against actuals, closing the learning loop.

    ``actuals`` maps product_id -> realized demand for any products whose
    outcome is known now (e.g. from a just-received Shopify order). Remaining
    pending rows are scored from the Data Pool's shopify/orders datasets.
    """
    evaluator = Evaluator(session, DataPool(session))
    if req.actuals:
        from app.models_perf import ModelPerformance

        # Apply explicit actuals to the most recent unevaluated row per product.
        for product_id, actual in req.actuals.items():
            row = await session.scalar(
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
        await session.commit()
    evaluated = await evaluator.evaluate_pending(shop_id=req.shop_id)
    return {"evaluated": evaluated}
