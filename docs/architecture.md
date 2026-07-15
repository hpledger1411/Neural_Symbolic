# Gbox Virtual Environment — Architecture

Gbox is a **neuro-symbolic predictive engine** for commerce virtual-environment
workflow needs. It combines neural forecasting with a symbolic rule/explainability
layer, and drives **decision automation** with human oversight.

## Vision

- **Core functions**
  1. **Shopify demand forecasting** — predict product demand / inventory needs
     from Shopify sales, price, and inventory history (via the Shopify connector
     and `products` table).
  2. **User behavior prediction** — predict customer actions, churn, and
     next-best-action from shop events and `feedback`.
  3. (legacy) learning-insight aggregation over `model_performance`.
  4. **Decision automation** — the engine recommends/triggers decisions; every
     step is recorded as a `trace` and can be confirmed/corrected via `feedback`.
- **Symbolic layer**: **neuro-symbolic hybrid** — a neural forecaster produces
  scores, the `RulesEngine` applies deterministic logic (thresholds, business
  constraints, guardrails) and emits human-readable explanations.
- **Integration**: FastAPI HTTP/Webhook endpoints that Power Automate calls via
  HTTP requests / custom connectors. (Flask is not used.)

## Stack

| Concern        | Choice                                            |
| -------------- | ------------------------------------------------- |
| API            | FastAPI                                           |
| Database       | PostgreSQL (async via `sqlalchemy+asyncpg`)       |
| ORM            | SQLAlchemy 2.0 async (`DeclarativeBase`)          |
| Migrations     | Alembic (async `env.py`)                          |
| Tests          | pytest + httpx `ASGITransport`, in-memory aiosqlite |
| Standards      | Type hints, Black, Mypy (`strict`-friendly), pytest |

The default `DATABASE_URL` falls back to `sqlite+aiosqlite` so the app and test
suite run with **no external services**. Production points at PostgreSQL via
`GBOX_DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/gbox`.

## Layers

```
app/
├── main.py                 # FastAPI app, lifespan (init_db + init_models)
├── database.py             # AsyncEngine, SessionLocal, Base, get_session
├── db.py                   # Legacy stdlib-sqlite helpers (predecessor tables)
├── models_perf.py          # ORM: ModelPerformance (model_performance table)
├── routers/
│   ├── shops.py            # Shopify shop + product sync
│   ├── ml.py               # predictions / traces / feedback / insights
│   └── learning.py         # GET /api/learning/insights
└── services/
    ├── shopify.py          # Shopify Admin API client (stdlib, no SDK)
    ├── insights.py         # Legacy feedback-driven insight generation
    ├── performance_tracker.py   # PerformanceTracker
    └── adaptive_learner.py      # AdaptiveLearner
```

## Module map

| Planned module     | Status      | Where it lives                                              |
| ------------------ | ----------- | ----------------------------------------------------------- |
| Forecaster         | Implemented (stub) | `services/forecaster.py` — neural demand/behavior scoring |
| RulesEngine        | Implemented (stub) | `services/rules_engine.py` — symbolic rules + explanations |
| AdaptiveLearner    | Implemented | `services/adaptive_learner.py` + `routers/learning.py`  |
| PerformanceTracker | Implemented | `services/performance_tracker.py`                       |
| Data Pool          | **Implemented** | `services/data_pool.py` + `routers/data_pool.py` + `VirtualDrive` |
| VirtualDrive       | **Implemented** | `services/virtual_drive.py` + `routers/drive.py` (blob store) |
| DebugTracer        | Implemented (Data Pool traces) | `DataPool.put_trace` + `/api/data-pool/traces` |

## Data model

### `model_performance` (new, SQLAlchemy ORM)

One row per evaluated prediction. Drives all learning insights.

| Column           | Type                  | Notes                                   |
| ---------------- | --------------------- | --------------------------------------- |
| `id`             | `int` PK              |                                         |
| `shop_id`        | `int` (indexed)       | tenant                                  |
| `product_id`     | `str` (indexed)       | entity being predicted                  |
| `model_name`     | `str` (indexed)       | e.g. `forecaster`, `rules_engine`       |
| `model_version`  | `str`                 |                                         |
| `predicted_value`| `float`               | model output                            |
| `actual_value`   | `float?`              | ground truth once known                 |
| `accuracy`       | `float?`              | 0..1, null until evaluated              |
| `is_correct`     | `bool?`               |                                         |
| `drift_alert`    | `bool` (default false)| concept-drift flag                      |
| `recorded_at`    | `timestamptz` (indexed)|                                      |

Unique constraint: `(shop_id, product_id, model_name, recorded_at)`.

### Legacy tables (stdlib sqlite, `app/db.py`)

`shops`, `products`, `predictions`, `traces`, `feedback`, `learning_insights`
— populated by the existing `/predictions`, `/traces`, `/feedback`,
`/insights` endpoints. These remain the scaffolding the async modules build on.

## `/api/learning/insights`

`GET /api/learning/insights?shop_id=&since_days=`

Flow:

```
request
  → get_session (AsyncSession)
  → AdaptiveLearner.learning_insights()
       → PerformanceTracker.collect()
            • overall_accuracy()      avg(accuracy) in window
            • worst_performing_products()  products by lowest mean accuracy
            • neural_weight_trend()   per-day mean accuracy (learning curve)
            • drift_alert_count()     rows flagged drift
       → recommendations (drift / low-accuracy / worst product)
```

Response contract:

```json
{
  "shop_id": null,
  "since_days": 30,
  "overall_accuracy": 0.66,
  "worst_performing_products": [
    {"product_id": "p2", "mean_accuracy": 0.3, "samples": 1}
  ],
  "neural_weight_trend": [
    {"date": "2026-07-15", "mean_accuracy": 0.66}
  ],
  "drift_alert_count": 1,
  "recommendations": [
    "Concept drift detected; consider retraining the Forecaster."
  ]
}
```

## Migrations

```bash
export GBOX_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/gbox
alembic upgrade head
```

`alembic upgrade head --sql` renders valid PostgreSQL DDL for `model_performance`
and the `alembic_version` table.

## Quality gates

```bash
black app tests
mypy app
pytest
```

All three pass on the implemented code.

## Power Automate integration

Gbox exposes plain HTTP endpoints Power Automate calls via the **HTTP** action
(or a custom connector). No Flask; FastAPI handles it.

| Power Automate need        | Endpoint                                | Method |
| -------------------------- | --------------------------------------- | ------ |
| Get learning insights      | `/api/learning/insights`                | GET    |
| Trigger a decision         | `/api/decisions`                        | POST   |
| Push human feedback        | `/feedback`                             | POST   |

### Example: Power Automate "HTTP" action

- **Method**: `POST`
- **URI**: `https://<gbox-host>/api/decisions`
- **Headers**: `Content-Type: application/json`
- **Body**:
  ```json
  {
    "shop_id": 1,
    "product_id": "p1",
    "history": [20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20],
    "inventory_qty": 0
  }
  ```
- **Response** (`action` is what Power Automate branches on):
  ```json
  {
    "product_id": "p1",
    "predicted_demand": 20.0,
    "confidence": 1.0,
    "action": "reorder",
    "explanation": "Predicted demand 20.00 >= 10.0 with stock 0; auto-reorder (conf 1.00).",
    "triggered_rules": ["rule:high_demand_reorder"],
    "trace_id": "..."
  }
  ```

`action` is one of `reorder` (auto-action), `hold` (guardrail/ default), or
`review` (low confidence → route to a human approval step in Power Automate).

## Neuro-symbolic decision flow

```
Shopify data / history
        │
        ▼
   Data Pool  ── files / datasets / traces / search  (/api/data-pool)
        │
        ▼
   Forecaster.predict()  ── neural scoring (predicted_demand, confidence)
        │
        ▼
   RulesEngine.decide()  ── symbolic rules + guardrails + explanation
        │
        ▼
   Decision {action, explanation, triggered_rules}
        │
        ├──► POST /api/decisions  (persists ModelPerformance row)
        ├──► Data Pool trace      (PUT /api/data-pool/traces)
        └──► Power Automate branch on action
```

## Build plan (in progress)

1. ✅ **VirtualDrive / Data Pool** — file storage, dataset management, trace
   storage, search. Endpoints: `/api/drive/*`, `/api/data-pool/{files,datasets,traces,search}`.
2. ✅ **Shopify sync** — products, orders, inventory pulled into the Data Pool;
   webhooks (`orders/create`, `inventory_levels/update`, `products/update`)
   ingest live events as traces. Endpoints: `POST /shops/{id}/sync`,
   `POST /webhooks/shopify/*`.
3. ✅ **Forecaster** — Statsmodels `ExponentialSmoothing` (Holt-Winters) replaces
   the stub; `ForecastingService` records predictions as `model_performance` rows
   for the insight loop.
4. ✅ **Learning Insights (real data)** — `Evaluator` scores pending
   `model_performance` rows against actuals (Shopify order quantities or
   explicit `actuals`), writing `accuracy` / `is_correct` / `drift_alert`.
   `POST /api/learning/evaluate` closes the loop; `/api/learning/insights`
   surfaces overall accuracy, worst products, neural-weight trend, drift.
5. ⏳ **Power Automate connector** — `connector/gbox-connector.json` drafted,
   finalized once step 5 wiring is confirmed operational.

