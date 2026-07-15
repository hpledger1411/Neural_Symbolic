"""Tests for the Evaluator and the real-data learning insights loop."""

from __future__ import annotations

import asyncio

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models_perf import ModelPerformance
from app.services.data_pool import DataPool
from app.services.evaluator import Evaluator
from app.services.forecasting import ForecastingService


def _seed_prediction(sess, shop_id, product_id, predicted):
    row = ModelPerformance(
        shop_id=shop_id,
        product_id=product_id,
        model_name="forecaster",
        model_version="v1",
        predicted_value=predicted,
        actual_value=None,
        accuracy=None,
        is_correct=None,
        drift_alert=False,
        recorded_at=datetime.now(timezone.utc),
    )
    sess.add(row)
    return row


def test_evaluator_pending_without_actuals(engine) -> None:
    from datetime import datetime, timezone

    async def _run():
        sess = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()
        _seed_prediction(sess, 1, "p1", predicted=100.0)
        await sess.commit()
        ev = Evaluator(sess, DataPool(sess))
        # No shopify-orders dataset in the Data Pool => nothing to score.
        return await ev.evaluate_pending()

    assert asyncio.run(_run()) == 0


def test_evaluator_explicit_actual(engine) -> None:
    from datetime import datetime, timezone

    async def _run():
        sess = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()
        row = _seed_prediction(sess, 1, "pX", predicted=90.0)
        await sess.commit()
        ev = Evaluator(sess, DataPool(sess))
        ok = await ev.evaluate_one(row, actual=100.0)
        await sess.commit()
        refreshed = await sess.get(ModelPerformance, row.id)
        return ok, refreshed.accuracy, refreshed.is_correct, refreshed.drift_alert

    ok, acc, correct, drift = asyncio.run(_run())
    assert ok is True
    # rel_err = 0.1 -> accuracy 0.9, within tolerance => correct, no drift.
    assert abs(acc - 0.9) < 1e-6
    assert correct is True
    assert drift is False


def test_evaluator_drift_on_bad_forecast(engine) -> None:
    from datetime import datetime, timezone

    async def _run():
        sess = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()
        row = _seed_prediction(sess, 1, "pBad", predicted=200.0)
        await sess.commit()
        ev = Evaluator(sess, DataPool(sess))
        await ev.evaluate_one(row, actual=10.0)
        await sess.commit()
        refreshed = await sess.get(ModelPerformance, row.id)
        return refreshed.accuracy, refreshed.drift_alert

    acc, drift = asyncio.run(_run())
    assert acc < 0.6
    assert drift is True


def test_endpoint_evaluate_then_insights(client) -> None:
    # Forecast a product, then report actual and read real insights.
    payload = {
        "shop_id": 1,
        "product_id": "pReal",
        "history": [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23],
    }
    dec = asyncio.run(client.post("/api/decisions", json=payload))
    assert dec.status_code == 200

    ev = asyncio.run(
        client.post("/api/learning/evaluate", json={"actuals": {"pReal": 100.0}})
    )
    assert ev.status_code == 200
    # The explicit actual for pReal is applied even if no pending-from-Data-Pool rows.
    assert ev.json()["evaluated"] >= 0

    ins = asyncio.run(client.get("/api/learning/insights?shop_id=1"))
    assert ins.status_code == 200
    body = ins.json()
    # pReal was evaluated (actual reported) -> overall_accuracy is a real number.
    assert 0.0 <= body["overall_accuracy"] <= 1.0
    # The evaluated forecast contributes to the trend series.
    assert body["neural_weight_trend"]
    # pReal appears among evaluated products (worst or not).
    ids = [p["product_id"] for p in body["worst_performing_products"]]
    assert "pReal" in ids
