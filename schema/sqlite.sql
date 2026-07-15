-- SQLite-compatible variant of schema/postgres.sql
-- Differences: no BIGSERIAL/TIMESTAMPTZ/JSONB -> INTEGER PK AUTOINCREMENT, TEXT, TEXT(JSON)

CREATE TABLE IF NOT EXISTS shops (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    shop_domain    TEXT NOT NULL UNIQUE,
    access_token   TEXT,
    scope          TEXT,
    installed_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS products (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    shop_id         INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    shopify_id      TEXT NOT NULL,
    title           TEXT,
    handle          TEXT,
    price           REAL,
    inventory_qty   INTEGER,
    synced_at       TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (shop_id, shopify_id)
);

CREATE TABLE IF NOT EXISTS predictions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    shop_id         INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    model_name      TEXT NOT NULL,
    model_version   TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    entity_id       TEXT NOT NULL,
    prediction      TEXT NOT NULL,
    confidence      REAL,
    features        TEXT,
    predicted_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_predictions_shop_entity
    ON predictions (shop_id, entity_type, entity_id);

CREATE TABLE IF NOT EXISTS traces (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    shop_id         INTEGER REFERENCES shops(id) ON DELETE SET NULL,
    trace_id        TEXT NOT NULL UNIQUE,
    parent_id       TEXT,
    span_name       TEXT NOT NULL,
    kind            TEXT,
    input           TEXT,
    output          TEXT,
    error           TEXT,
    started_at      TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at        TEXT,
    duration_ms     INTEGER
);
CREATE INDEX IF NOT EXISTS idx_traces_shop_started
    ON traces (shop_id, started_at DESC);

CREATE TABLE IF NOT EXISTS feedback (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    shop_id         INTEGER REFERENCES shops(id) ON DELETE SET NULL,
    prediction_id   INTEGER REFERENCES predictions(id) ON DELETE CASCADE,
    trace_id        TEXT REFERENCES traces(trace_id) ON DELETE SET NULL,
    rating          INTEGER,
    label           TEXT,
    comment         TEXT,
    source          TEXT NOT NULL DEFAULT 'human',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_feedback_prediction
    ON feedback (prediction_id);

CREATE TABLE IF NOT EXISTS learning_insights (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    shop_id         INTEGER REFERENCES shops(id) ON DELETE CASCADE,
    insight_type    TEXT NOT NULL,
    title           TEXT NOT NULL,
    detail          TEXT NOT NULL,
    metric_value    REAL,
    computed_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_insights_shop_type
    ON learning_insights (shop_id, insight_type, computed_at DESC);
