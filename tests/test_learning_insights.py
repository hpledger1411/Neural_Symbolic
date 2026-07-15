"""Tests for decision automation (Forecaster + RulesEngine) and learning insights.

Synchronous tests; async service code and httpx.AsyncClient calls are driven via
asyncio.run so no pytest-asyncio plugin is required. Sessions and all their
usage happen inside a single asyncio.run to avoid cross-event-loop binding.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.adaptive_learner import AdaptiveLearner
from app.services.forecaster import ForecastInput, Forecaster
from app.services.rules_engine import RulesEngine
from tests.helpers import seed_performances


def test_forecaster_basic() -> None:
    f = Forecaster()
    out = f.predict(ForecastInput(product_id="p1", history=[10, 12, 14]))
    assert out.predicted_demand == 12.0
    assert 0.0 <= out.confidence <= 1.0


def test_rules_engine_reorder() -> None:
    f = Forecaster()
    r = RulesEngine()
    forecast = f.predict(ForecastInput(product_id="p1", history=[20] * 14))
    decision = r.decide(forecast, inventory_qty=0)
    assert decision.action == "reorder"
    assert "rule:high_demand_reorder" in decision.triggered_rules


def test_rules_engine_guardrail_hold() -> None:
    f = Forecaster()
    r = RulesEngine()
    forecast = f.predict(ForecastInput(product_id="p1", history=[50, 50, 50]))
    decision = r.decide(forecast, inventory_qty=99)
    assert decision.action == "hold"
    assert "guardrail:stock_adequate" in decision.triggered_rules


def test_rules_engine_low_confidence_review() -> None:
    f = Forecaster()
    r = RulesEngine()
    forecast = f.predict(ForecastInput(product_id="p1", history=[1]))
    decision = r.decide(forecast, inventory_qty=0)
    assert decision.action == "review"
    assert "rule:low_confidence_review" in decision.triggered_rules


def test_overall_accuracy_empty(engine) -> None:
    async def _run():
        sess = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()
        return await PerformanceTracker(sess).overall_accuracy()

    from app.services.performance_tracker import PerformanceTracker

    assert asyncio.run(_run()) == 0.0


def test_insights_payload_shape(engine) -> None:
    from app.services.performance_tracker import PerformanceTracker

    async def _run():
        sess = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()
        await seed_performances(
            sess,
            [
                {"product_id": "p1", "accuracy": 0.9, "is_correct": True},
                {
                    "product_id": "p2",
                    "accuracy": 0.3,
                    "is_correct": False,
                    "drift_alert": True,
                },
                {"product_id": "p1", "accuracy": 0.8, "is_correct": True},
            ],
        )
        return await AdaptiveLearner(sess).learning_insights()

    out = asyncio.run(_run())
    assert set(out) >= {
        "overall_accuracy",
        "worst_performing_products",
        "neural_weight_trend",
        "drift_alert_count",
    }
    assert out["overall_accuracy"] == (0.9 + 0.3 + 0.8) / 3
    assert out["drift_alert_count"] == 1
    assert out["worst_performing_products"][0]["product_id"] == "p2"
    assert len(out["neural_weight_trend"]) >= 1


def test_worst_performing_products_ranks_lowest(engine) -> None:
    from app.services.performance_tracker import PerformanceTracker

    async def _run():
        sess = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()
        await seed_performances(
            sess,
            [
                {"product_id": "good", "accuracy": 0.95, "is_correct": True},
                {"product_id": "bad", "accuracy": 0.1, "is_correct": False},
            ],
        )
        return await PerformanceTracker(sess).worst_performing_products(limit=5)

    worst = asyncio.run(_run())
    assert worst[0]["product_id"] == "bad"
    assert worst[0]["mean_accuracy"] == 0.1


def test_endpoint_contract(client) -> None:
    resp = asyncio.run(client.get("/api/learning/insights"))
    assert resp.status_code == 200
    body = resp.json()
    for key in (
        "overall_accuracy",
        "worst_performing_products",
        "neural_weight_trend",
        "drift_alert_count",
    ):
        assert key in body
    assert isinstance(body["worst_performing_products"], list)
    assert isinstance(body["neural_weight_trend"], list)


def test_decision_endpoint_reorder(client) -> None:
    payload = {
        "shop_id": 1,
        "product_id": "p1",
        "history": [20] * 14,
        "inventory_qty": 0,
    }
    resp = asyncio.run(client.post("/api/decisions", json=payload))
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "reorder"
    assert body["predicted_demand"] == 20.0
    assert "rule:high_demand_reorder" in body["triggered_rules"]


def test_decision_endpoint_guardrail(client) -> None:
    payload = {
        "shop_id": 1,
        "product_id": "p2",
        "history": [50, 50, 50],
        "inventory_qty": 99,
    }
    resp = asyncio.run(client.post("/api/decisions", json=payload))
    assert resp.status_code == 200
    assert resp.json()["action"] == "hold"


def test_endpoint_with_seeded_data(client, engine) -> None:
    async def _seed():
        sess = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()
        await seed_performances(
            sess,
            [
                {
                    "product_id": "p1",
                    "accuracy": 0.7,
                    "is_correct": True,
                    "drift_alert": True,
                },
                {
                    "product_id": "p2",
                    "accuracy": 0.2,
                    "is_correct": False,
                    "drift_alert": True,
                },
            ],
        )
        await sess.close()

    asyncio.run(_seed())
    resp = asyncio.run(client.get("/api/learning/insights?shop_id=1&since_days=30"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["drift_alert_count"] == 2
    assert body["overall_accuracy"] == (0.7 + 0.2) / 2
    assert "recommendations" in body
    assert any("drift" in r.lower() for r in body["recommendations"])


def test_since_days_validation(client) -> None:
    resp = asyncio.run(client.get("/api/learning/insights?since_days=0"))
    assert resp.status_code == 422


def test_virtualdrive_put_get_list(client) -> None:
    import base64

    payload = {
        "path": "rules/active.json",
        "kind": "ruleset",
        "data": base64.b64encode(b'{"version": 1}').decode(),
        "content_type": "application/json",
    }
    put = asyncio.run(client.put("/api/drive", json=payload))
    assert put.status_code == 200
    meta = put.json()
    assert meta["kind"] == "ruleset"
    assert meta["size_bytes"] == 14

    lst = asyncio.run(client.get("/api/drive"))
    assert lst.status_code == 200
    assert any(o["path"] == "rules/active.json" for o in lst.json())

    latest = asyncio.run(client.get("/api/drive/latest/ruleset"))
    assert latest.status_code == 200
    assert latest.json()["path"] == "rules/active.json"

    data = asyncio.run(client.get("/api/drive/rules/active.json/data"))
    assert data.status_code == 200
    assert base64.b64decode(data.json()["data"]) == b'{"version": 1}'

    deleted = asyncio.run(client.delete("/api/drive/rules/active.json"))
    assert deleted.status_code == 200
    missing = asyncio.run(client.get("/api/drive/rules/active.json"))
    assert missing.status_code == 404


def test_virtualdrive_overwrite(client) -> None:
    import base64

    payload = {
        "path": "models/forecaster",
        "kind": "model",
        "data": base64.b64encode(b"v1").decode(),
    }
    asyncio.run(client.put("/api/drive", json=payload))
    payload["data"] = base64.b64encode(b"v2-updated").decode()
    resp = asyncio.run(client.put("/api/drive", json=payload))
    assert resp.status_code == 200
    assert resp.json()["size_bytes"] == 10


def test_data_pool_files_traces_datasets_search(client) -> None:
    import base64

    # File
    fput = asyncio.run(
        client.put(
            "/api/data-pool/files",
            json={
                "path": "raw/sales.csv",
                "data": base64.b64encode(b"a,b\n1,2\n").decode(),
            },
        )
    )
    assert fput.status_code == 200
    fget = asyncio.run(client.get("/api/data-pool/files/raw/sales.csv"))
    assert fget.status_code == 200
    assert base64.b64decode(fget.json()["data"]) == b"a,b\n1,2\n"

    # Dataset
    dput = asyncio.run(
        client.post(
            "/api/data-pool/datasets",
            json={
                "name": "sales-2026",
                "kind": "timeseries",
                "file_path": "raw/sales.csv",
                "meta": {"unit": "day"},
            },
        )
    )
    assert dput.status_code == 200
    dlst = asyncio.run(client.get("/api/data-pool/datasets"))
    assert any(d["name"] == "sales-2026" for d in dlst.json())

    # Trace
    tput = asyncio.run(
        client.put(
            "/api/data-pool/traces",
            json={"trace_id": "tr1", "payload": {"span": "forecast", "ok": True}},
        )
    )
    assert tput.status_code == 200
    tget = asyncio.run(client.get("/api/data-pool/traces/tr1"))
    assert tget.json()["payload"]["span"] == "forecast"

    # Search
    s = asyncio.run(client.get("/api/data-pool/search?q=sales"))
    body = s.json()
    assert body["counts"]["files"] >= 1
    assert body["counts"]["datasets"] >= 1


def test_data_pool_missing_file_404(client) -> None:
    resp = asyncio.run(client.get("/api/data-pool/files/nope.csv"))
    assert resp.status_code == 404
