# Gbox Virtual Environment

A **neuro-symbolic predictive engine** for commerce virtual-environment workflow
needs. It forecasts Shopify demand and user behavior with a neural model
(Statsmodels `ExponentialSmoothing`), applies a symbolic rules layer for
explainable decision automation, and continuously improves via a feedback and
evaluation loop that feeds learning insights.

```
Shopify ──▶ Data Pool ──▶ Forecast ──▶ Rules ──▶ Decision/Trace ──▶ Feedback ──▶ Evaluate ──▶ Learning Insights
```

## Stack

| Concern     | Choice                                             |
| ----------- | -------------------------------------------------- |
| API         | FastAPI                                            |
| Database    | PostgreSQL (async via `sqlalchemy+asyncpg`)        |
| ORM         | SQLAlchemy 2.0 async                                |
| Migrations  | Alembic (async `env.py`)                           |
| Forecasting | Statsmodels `ExponentialSmoothing` (Holt-Winters)  |
| Tests       | pytest + httpx `ASGITransport`, in-memory aiosqlite |
| Standards   | Type hints, Black, Mypy, pytest                    |

The app falls back to `sqlite+aiosqlite` (no external services) unless
`GBOX_DATABASE_URL` points at PostgreSQL.

## Modules

| Module           | File(s)                                              | Role |
| ---------------- | ---------------------------------------------------- | ---- |
| Forecaster       | `app/services/forecaster.py`                         | Statsmodels `ExponentialSmoothing` demand/behavior scoring |
| RulesEngine      | `app/services/rules_engine.py`                       | Symbolic rules, guardrails, explanations |
| AdaptiveLearner  | `app/services/adaptive_learner.py`                   | Turns aggregates into insights + recommendations |
| PerformanceTracker | `app/services/performance_tracker.py`             | Aggregates `model_performance` |
| Evaluator        | `app/services/evaluator.py`                          | Scores forecasts vs actuals (closes loop) |
| Data Pool        | `app/services/data_pool.py`, `virtual_drive.py`     | File/dataset/trace storage + search |
| ShopifySync      | `app/services/shopify_sync.py`                      | Pulls products/orders/inventory; webhooks |

## Quick start

```bash
# 1. Install dependencies (system Python is externally managed; use --break-system-packages
#    or a venv)
pip install -r requirements.txt

# 2. (Optional) point at PostgreSQL
export GBOX_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/gbox
alembic upgrade head

# 3. Run
uvicorn app.main:app --port 8000
```

The app creates all tables on startup (`init_models`). With SQLite, no migration
step is required for local runs.

## API

### Learning
- `GET  /api/learning/insights?shop_id=&since_days=`
  Returns `overall_accuracy`, `worst_performing_products`, `neural_weight_trend`,
  `drift_alert_count`, and `recommendations`.
- `POST /api/learning/evaluate` `{ "shop_id": 1, "actuals": { "p1": 100 } }`
  Scores pending forecasts against actuals; actuals optional (Shopify orders used).

### Decisions (Forecaster + RulesEngine)
- `POST /api/decisions`
  ```json
  {
    "shop_id": 1, "product_id": "p1",
    "history": [20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20],
    "inventory_qty": 0
  }
  ```
  Response `action` is one of `reorder` (auto), `hold` (guardrail/default),
  `review` (low confidence → human approval).

### Data Pool
- `PUT    /api/data-pool/files` — store a file (base64)
- `GET    /api/data-pool/files/{path}` — retrieve
- `POST   /api/data-pool/datasets` — register a dataset
- `GET    /api/data-pool/datasets` — list
- `PUT    /api/data-pool/traces` — store an execution trace
- `GET    /api/data-pool/traces/{trace_id}`
- `GET    /api/data-pool/search?q=` — search files + datasets

### VirtualDrive (blob store)
- `PUT/GET/DELETE /api/drive/{path}`, `GET /api/drive`, `GET /api/drive/latest/{kind}`

### Shopify
- `POST /shops/{shop_id}/sync` — pull products, orders, inventory into Data Pool
- `POST /webhooks/shopify/orders/create`
- `POST /webhooks/shopify/inventory_levels/update`
- `POST /webhooks/shopify/products/update`

### Legacy
- `/shops`, `/predictions`, `/traces`, `/feedback`, `/insights` (stdlib-sqlite)

## Authentication

Protected routes require the `X-API-Key` header. Set the expected key via the
`GBOX_API_KEY` environment variable; when it is unset, auth is **disabled**
(local dev / tests).

```bash
export GBOX_API_KEY=your-secret-key
uvicorn app.main:app --port 8000
```

```bash
curl -H "X-API-Key: $GBOX_API_KEY" http://localhost:8000/api/learning/insights
```

Exempt paths (no key required): `/health` and `/webhooks/*` (Shopify webhooks
are authenticated by HMAC signature in production, not the API key).

## Power Automate

`connector/gbox-connector.json` is an OpenAPI (Swagger 2.0) custom-connector
definition. It declares an `apiKey` security scheme on the `X-API-Key` header
and applies it to all operations. Import it into Power Automate, set `host` to
your Gbox URL, and provide the connector's API key; then call the HTTP actions
and branch on the `action` field returned by `/api/decisions`:

- `reorder` → automated action
- `hold` → no action
- `review` → route to a human approval step

## Database schema

Key tables:

- `model_performance` — one row per evaluated prediction (drives insights)
- `drive_objects` — VirtualDrive blobs (files/traces)
- `datasets` — registered Data Pool datasets
- Legacy (stdlib sqlite): `shops`, `products`, `predictions`, `traces`,
  `feedback`, `learning_insights`

Migrations live in `migrations/versions/`.

## Development

```bash
black app tests
mypy app
pytest
```

All three must pass. `mypy` reads `mypy.ini` (statsmodels has no type stubs, so
`ignore_missing_imports` is set).

## Layout

```
app/
  main.py                 FastAPI app + lifespan
  database.py             async engine, session, Base, init_models
  db.py                   legacy stdlib-sqlite helpers
  models_perf.py          ModelPerformance ORM
  models_drive.py         DriveObject ORM
  models_dataset.py       Dataset ORM
  routers/                shops, ml, learning, decisions, drive, data_pool, shopify_sync
  services/               shopify, shopify_sync, forecaster, forecasting,
                          rules_engine, performance_tracker, adaptive_learner,
                          evaluator, data_pool, virtual_drive
connector/gbox-connector.json
docs/architecture.md
migrations/
tests/
requirements.txt
pytest.ini / mypy.ini
```
