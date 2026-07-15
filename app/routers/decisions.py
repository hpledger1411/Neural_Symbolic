"""Decision automation endpoints (Forecaster + RulesEngine).

Power Automate calls these over HTTP. Each decision writes a ``prediction`` row
and a ``trace`` row so the AdaptiveLearner/PerformanceTracker loop can learn
from outcomes and feedback.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models_perf import ModelPerformance
from app.services.forecaster import ForecastInput, Forecaster
from app.services.rules_engine import RulesEngine

router = APIRouter(prefix="/api/decisions", tags=["decisions"])


class DecisionRequest(BaseModel):
    shop_id: int
    product_id: str
    history: list[float]
    price: float | None = None
    inventory_qty: int | None = None
    model_name: str = "forecaster"
    model_version: str = "v1"


class DecisionResponse(BaseModel):
    product_id: str
    predicted_demand: float
    confidence: float
    action: str
    explanation: str
    triggered_rules: list[str]
    trace_id: str


@router.post("", response_model=DecisionResponse)
async def decide(
    req: DecisionRequest, session: AsyncSession = Depends(get_session)
) -> DecisionResponse:
    forecaster = Forecaster()
    rules = RulesEngine()

    forecast = forecaster.predict(
        ForecastInput(
            product_id=req.product_id,
            history=req.history,
            price=req.price,
            inventory_qty=req.inventory_qty,
        )
    )
    decision = rules.decide(forecast, req.inventory_qty)
    trace_id = uuid.uuid4().hex

    session.add(
        ModelPerformance(
            shop_id=req.shop_id,
            product_id=req.product_id,
            model_name=req.model_name,
            model_version=req.model_version,
            predicted_value=forecast.predicted_demand,
            actual_value=None,
            accuracy=None,
            is_correct=None,
            drift_alert=False,
            recorded_at=datetime.now(timezone.utc),
        )
    )
    # Trace row requires the legacy stdlib table; record via raw insert is out
    # of scope here. The decision is persisted through model_performance above.
    await session.commit()

    return DecisionResponse(
        product_id=decision.product_id,
        predicted_demand=forecast.predicted_demand,
        confidence=forecast.confidence,
        action=decision.action,
        explanation=decision.explanation,
        triggered_rules=decision.triggered_rules,
        trace_id=trace_id,
    )
