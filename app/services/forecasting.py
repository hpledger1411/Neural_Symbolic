"""ForecastingService: run the Forecaster over Data Pool time series.

Builds per-product demand histories from stored Shopify data (or any numeric
series in the Data Pool), forecasts with the Statsmodels ``Forecaster``, and
records each result as a ``model_performance`` row so the AdaptiveLearner /
PerformanceTracker insight loop has real data to evaluate.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models_perf import ModelPerformance
from app.services.forecaster import ForecastInput, Forecaster


class ForecastingService:
    def __init__(
        self,
        session: AsyncSession,
        model_name: str = "forecaster",
        model_version: str = "v1",
    ) -> None:
        self.session = session
        self.forecaster = Forecaster()
        self.model_name = model_name
        self.model_version = model_version

    async def forecast_product(
        self, shop_id: int, product_id: str, history: list[float]
    ) -> ModelPerformance:
        result = self.forecaster.predict(
            ForecastInput(product_id=product_id, history=history)
        )
        row = ModelPerformance(
            shop_id=shop_id,
            product_id=product_id,
            model_name=self.model_name,
            model_version=self.model_version,
            predicted_value=result.predicted_demand,
            actual_value=None,
            accuracy=None,
            is_correct=None,
            drift_alert=False,
            recorded_at=datetime.now(timezone.utc),
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row
