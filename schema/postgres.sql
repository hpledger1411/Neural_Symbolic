-- Gbox Virtual Environment — PostgreSQL schema
-- Portable DDL. Works on PostgreSQL; SQLite variant in schema/sqlite.sql.

CREATE TABLE IF NOT EXISTS shops (
    id              BIGSERIAL PRIMARY KEY,
    shop_domain    TEXT NOT NULL UNIQUE,
    access_token   TEXT,
    scope          TEXT,
    installed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS products (
    id              BIGSERIAL PRIMARY KEY,
    shop_id         BIGINT NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    shopify_id      TEXT NOT NULL,
    title           TEXT,
    handle          TEXT,
    price           NUMERIC(12,2),
    inventory_qty   INTEGER,
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (shop_id, shopify_id)
);

-- Model predictions (e.g. demand forecast, recommendation scores)
CREATE TABLE IF NOT EXISTS predictions (
    id              BIGSERIAL PRIMARY KEY,
    shop_id         BIGINT NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    model_name      TEXT NOT NULL,
    model_version   TEXT NOT NULL,
    entity_type     TEXT NOT NULL,           -- 'product' | 'customer' | 'order'
    entity_id       TEXT NOT NULL,
    prediction      JSONB NOT NULL,           -- the predicted value/object
    confidence      NUMERIC(5,4),             -- 0..1
    features        JSONB,                    -- input features snapshot
    predicted_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_predictions_shop_entity
    ON predictions (shop_id, entity_type, entity_id);

-- Execution traces (agent / pipeline observability)
CREATE TABLE IF NOT EXISTS traces (
    id              BIGSERIAL PRIMARY KEY,
    shop_id         BIGINT REFERENCES shops(id) ON DELETE SET NULL,
    trace_id        TEXT NOT NULL UNIQUE,
    parent_id       TEXT,
    span_name       TEXT NOT NULL,
    kind            TEXT,                      -- 'agent' | 'tool' | 'llm' | 'db'
    input           JSONB,
    output          JSONB,
    error           TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at        TIMESTAMPTZ,
    duration_ms     INTEGER
);
CREATE INDEX IF NOT EXISTS idx_traces_shop_started
    ON traces (shop_id, started_at DESC);

-- Human / automated feedback on predictions or traces
CREATE TABLE IF NOT EXISTS feedback (
    id              BIGSERIAL PRIMARY KEY,
    shop_id         BIGINT REFERENCES shops(id) ON DELETE SET NULL,
    prediction_id   BIGINT REFERENCES predictions(id) ON DELETE CASCADE,
    trace_id        TEXT REFERENCES traces(trace_id) ON DELETE SET NULL,
    rating          SMALLINT,                  -- -1,0,1 or 1..5
    label           TEXT,                      -- 'correct' | 'wrong' | 'helpful'
    comment         TEXT,
    source          TEXT NOT NULL DEFAULT 'human',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_feedback_prediction
    ON feedback (prediction_id);

-- Derived learning insights from predictions + feedback + traces
CREATE TABLE IF NOT EXISTS learning_insights (
    id              BIGSERIAL PRIMARY KEY,
    shop_id         BIGINT REFERENCES shops(id) ON DELETE CASCADE,
    insight_type    TEXT NOT NULL,             -- 'accuracy' | 'drift' | 'bias' | 'suggestion'
    title           TEXT NOT NULL,
    detail          JSONB NOT NULL,
    metric_value    NUMERIC,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_insights_shop_type
    ON learning_insights (shop_id, insight_type, computed_at DESC);
