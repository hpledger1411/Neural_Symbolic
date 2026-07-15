"""Tests for the Statsmodels ExponentialSmoothing Forecaster and ForecastingService."""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.forecaster import ForecastInput, Forecaster
from app.services.forecasting import ForecastingService


def test_forecaster_flat_series_forecasts_mean() -> None:
    f = Forecaster()
    out = f.predict(ForecastInput(product_id="p1", history=[20] * 14))
    assert out.predicted_demand == 20.0
    assert 0.0 <= out.confidence <= 1.0


def test_forecaster_trend_upward() -> None:
    f = Forecaster()
    # Linearly increasing demand should forecast above the last observation.
    hist = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
    out = f.predict(ForecastInput(product_id="p1", history=hist))
    assert out.predicted_demand > 14.0
    assert 0.0 <= out.confidence <= 1.0


def test_forecaster_short_history_falls_back_to_mean() -> None:
    f = Forecaster()
    out = f.predict(ForecastInput(product_id="p1", history=[5, 7]))
    assert out.predicted_demand == 6.0
    assert out.confidence == 2 / 5


def test_forecaster_empty_history() -> None:
    f = Forecaster()
    out = f.predict(ForecastInput(product_id="p1", history=[]))
    assert out.predicted_demand == 0.0
    assert out.confidence == 0.0


def test_forecasting_service_records_model_performance(engine) -> None:
    async def _run():
        sess = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()
        svc = ForecastingService(sess, model_name="forecaster", model_version="v1")
        row = await svc.forecast_product(
            shop_id=1,
            product_id="p1",
            history=[10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23],
        )
        return row

    row = asyncio.run(_run())
    assert row.shop_id == 1
    assert row.product_id == "p1"
    assert row.model_name == "forecaster"
    assert row.predicted_value > 23.0  # upward trend forecast
