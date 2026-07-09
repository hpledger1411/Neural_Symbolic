# Neuro-Symbolic Predictive Engine

A hybrid AI engine combining symbolic rule-based logic with neural time-series forecasting for predictive inventory, demand, and trend analysis in online retail.

## Features

- **Hybrid Architecture**: Combines symbolic rules engine with neural forecasting
- **Real-time Predictions**: Demand forecasting, seasonal pattern detection, anomaly detection
- **Customizable Workflows**: JSON-based rule engine for business logic
- **Virtual Drive**: Database-backed data pool for rules, configs, and historical data
- **Adaptive Learning**: Auto-tunes neural weights globally and rule thresholds based on feedback
- **Comprehensive Debugging**: Execution traces showing neural + symbolic reasoning paths
- **Performance Tracking**: Continuous model and rule effectiveness monitoring
- **Async-first**: FastAPI with PostgreSQL for high concurrency
- **Explainability**: Reasoning traces showing neural signals + symbolic rules

## Architecture

```
Backend Stack:

┌─────────────────────────────────────────────────────────────────┐
│ API Layer (FastAPI, async)                                       │
│  └─ /predictions, /workflows, /data-pool, /debug, /learning     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Engine Layer                                                     │
├─────────────────────────────────────────────────────────────────┤
│ ┌──────────────────────────────────────────────────────────┐    │
│ │ Neuro-Symbolic Engine (orchestrates both layers)        │    │
│ └──────────────────────────────────────────────────────────┘    │
│  ├─ Forecaster (neural)           → Exponential smoothing      │
│  ├─ RulesEngine (symbolic)        → JSON conditions/actions    │
│  ├─ Hybrid Combination            → Weighted predictions       │
│  ├─ DebugTracer                   → Execution traces           │
│  ├─ AdaptiveLearner               → Auto-tune weights/rules    │
│  ├─ PerformanceTracker            → Metrics & analytics        │
│  └─ VirtualDrive                  → Data pool storage          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Database Layer (PostgreSQL + SQLAlchemy async ORM)              │
├─────────────────────────────────────────────────────────────────┤
│ Core Tables:         Performance Tracking:                       │
│ ├─ products          ├─ model_performance                        │
│ ├─ inventory         ├─ global_model_weights                     │
│ ├─ orders            ├─ rule_performance                         │
│ ├─ trends            ├─ execution_traces                         │
│ ├─ predictions       ├─ feedback_events                          │
│ └─ workflow_rules    └─ virtual_drive_files                      │
└─────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
backend/
├─ api/
│  ├─ main.py                  # FastAPI app
│  ├─ schemas.py               # Pydantic models
│  └─ routes/                  # API endpoints (to be added)
│     ├─ predictions.py        # Forecast endpoints
│     ├─ workflows.py          # Rule CRUD
│     ├─ data_pool.py          # Virtual drive
│     ├─ debug.py              # Debug viewer
│     └─ learning.py           # Learning/feedback
├─ engine/
│  ├─ neuro_symbolic.py        # Core hybrid engine
│  ├─ rules_engine.py          # Symbolic workflow logic
│  ├─ forecaster.py            # Neural time-series
│  ├─ virtual_drive.py         # Data pool
│  ├─ debug_tracer.py          # Execution traces 🆕
│  ├─ adaptive_learner.py      # Auto-tuning 🆕
│  └─ performance_tracker.py   # Metrics & analytics 🆕
├─ models/
│  ├─ product.py               # Product catalog
│  ├─ inventory.py             # Stock levels
│  ├─ order.py                 # Customer orders
│  ├─ trend.py                 # Demand patterns
│  ├─ workflow_rule.py         # JSON rules
│  ├─ prediction.py            # Engine predictions
│  ├─ virtual_drive.py         # File storage
│  ├─ execution_trace.py       # Debug logs 🆕
│  ├─ feedback_event.py        # Actual outcomes 🆕
│  └─ model_performance.py     # Metrics 🆕
├─ utils/
│  ├─ parsers.py               # JSON utilities
│  └─ validators.py            # Data validation
├─ config.py                   # Settings
├─ database.py                 # AsyncSession factory
requirements.txt
.env.example
```

## Adaptive Learning System

### Neural Weight Auto-Tuning

The engine automatically adjusts the contribution of neural vs. symbolic layers:

```python
# Example: As store grows and patterns become clearer
Day 1:   Neural weight = 0.60 (less historical data)
         Symbolic weight = 0.40

Day 30:  Neural weight = 0.70 (improved forecasting)
         Symbolic weight = 0.30

Day 90:  Neural weight = 0.75 (highly accurate trends)
         Symbolic weight = 0.25
```

**Triggers:**
- Accuracy exceeds 80% → increase neural weight
- Accuracy below 60% → decrease neural weight
- High drift detected → signal for retraining

### Symbolic Rule Threshold Auto-Tuning

Rule thresholds automatically adjust based on outcomes:

```json
{
  "rule": "Reorder Alert",
  "current_threshold": 50,  // Reorder when inventory < 50
  "effectiveness": 0.72,
  
  // Auto-tuned after feedback:
  "recommended_threshold": 45,  // Too many false positives
  "reason": "Rule triggering too often, loosening threshold"
}
```

### Feedback Loop Process

1. **Make Prediction** → Store in `predictions` table
2. **Real outcome occurs** → Record actual value
3. **Submit Feedback** → `POST /api/learning/feedback`
   ```json
   {
     "prediction_id": "...",
     "actual_value": 125,
     "feedback_type": "demand",
     "external_factors": {"weather": "rainy", "promo": true}
   }
   ```
4. **Learning Engine Processes** → Calculates error metrics
5. **Auto-Tuning Triggered** → If enough samples collected
   - Neural weights adjusted
   - Rule thresholds updated
   - New weights saved (with version history)
6. **Next Prediction Uses New Weights**

## Debugging & Explainability

### Execution Traces

Every prediction generates a detailed trace:

```python
Trace saved: prediction_uuid
├─ Neural Layer
│  ├─ Inputs: 30 historical data points
│  ├─ Exponential smoothing (α=0.3)
│  ├─ Trend detection: +5.2 units/day
│  ├─ Forecast: 150±20 units, confidence=0.87
│  └─ Execution time: 23.4ms
├─ Symbolic Layer
│  ├─ Rules evaluated: 5
│  ├─ Rules fired: 2 ("seasonal_boost", "high_demand_alert")
│  ├─ Actions: Apply 1.5x multiplier
│  └─ Execution time: 8.7ms
├─ Hybrid Combination
│  ├─ Neural weight: 0.60
│  ├─ Combined value: 155 (150 * 1.03)
│  ├─ Final confidence: 0.82
│  └─ Recommendation: "Order 200 units"
└─ Total execution: 32.1ms
```

### Debug Viewer Endpoint

```bash
GET /api/debug/traces/{prediction_id}

Response:
{
  "decision_path": "...",
  "neural_outputs": {...},
  "rules_applied": [...],
  "reasoning": {...},
  "performance_metrics": {
    "execution_time_ms": 32.1,
    "memory_used_mb": 2.4
  }
}
```

## Performance Monitoring

### Model Performance Metrics

```python
Period: Last 30 days
Demand Forecast Model (v1.2.0):
  • MAE: 12.3 units
  • MAPE: 8.7%
  • Accuracy: 82.4% (within 10%)
  • Direction Accuracy: 89.1%
  • Drift Detected: No
```

### Rule Effectiveness Ranking

```python
1. "Seasonal Peak Alert" - Effectiveness: 0.94
2. "Low Stock Reorder" - Effectiveness: 0.87
3. "Anomaly Detection" - Effectiveness: 0.71
```

### Learning Insights

```python
GET /api/learning/insights

Response:
{
  "overall_accuracy": 82.1,
  "worst_performing_products": [
    {"product_id": "xyz", "avg_error": 23.4}
  ],
  "neural_weight_trend": "↑ (0.60 → 0.68 over 30 days)",
  "drift_alerts": 2,
  "models_needing_retraining": 1
}
```

## Quick Start

### Prerequisites
- Python 3.10+
- PostgreSQL 13+

### Installation

1. **Clone and setup environment**
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # or `venv\Scripts\activate` on Windows
   pip install -r requirements.txt
   ```

2. **Configure database**
   ```bash
   cp .env.example .env
   # Edit .env with your PostgreSQL credentials
   ```

3. **Initialize database**
   ```bash
   python -m alembic init migrations
   python -m alembic revision --autogenerate -m "Initial schema"
   python -m alembic upgrade head
   ```

4. **Run API server**
   ```bash
   python -m uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000
   ```

   API will be available at `http://localhost:8000`
   - Interactive docs: `http://localhost:8000/docs`
   - ReDoc: `http://localhost:8000/redoc`

## API Endpoints

### Predictions
- `POST /api/predictions/demand` - Get demand forecast
- `POST /api/predictions/seasonality` - Detect seasonal patterns
- `POST /api/predictions/reorder` - Get reorder recommendations
- `POST /api/predictions/anomaly` - Detect anomalies

### Workflows
- `GET /api/workflows/rules` - List workflow rules
- `POST /api/workflows/rules` - Create new rule
- `PUT /api/workflows/rules/{id}` - Update rule
- `DELETE /api/workflows/rules/{id}` - Delete rule
- `POST /api/workflows/execute` - Execute workflow

### Data Pool
- `GET /api/data-pool/files` - List virtual drive files
- `POST /api/data-pool/files` - Upload file
- `GET /api/data-pool/files/{id}` - Download file
- `DELETE /api/data-pool/files/{id}` - Delete file

### Learning & Feedback 🆕
- `POST /api/learning/feedback` - Submit prediction outcome
- `GET /api/learning/insights` - Get learning insights
- `GET /api/learning/auto-tune` - Trigger auto-tuning
- `GET /api/learning/rule-performance` - Rule effectiveness

### Debug 🆕
- `GET /api/debug/traces/{prediction_id}` - View execution trace
- `GET /api/debug/model-comparison` - Compare model versions
- `GET /api/debug/drift-alerts` - Active drift alerts
- `GET /api/debug/metrics` - Global performance metrics

## Development

### Run Tests
```bash
pytest
```

### Format Code
```bash
black backend/
flake8 backend/
mypy backend/
```

## Next Steps

- [ ] Implement API route handlers
- [ ] Add WebSocket for real-time predictions & feedback
- [ ] Add authentication (JWT)
- [ ] Create Docker setup
- [ ] Add comprehensive tests
- [ ] Integrate frontend dashboard
- [ ] Add monitoring & alerting
- [ ] Deploy to cloud (AWS/GCP/Azure)

## License

MIT
