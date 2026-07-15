"""Learning insights generation from predictions + feedback + traces."""

from __future__ import annotations

from datetime import datetime, timedelta

from app import db


def _load_json(row: dict, *keys):
    out = {}
    for k in keys:
        out[k] = db._jload(row.get(k))
    return out


def generate_insights(shop_id: int | None = None, since_days: int = 30) -> list[dict]:
    """Compute simple but useful insights and persist them.

    - accuracy: prediction correctness from positive/negative feedback labels
    - drift: predictions per model over recent window
    - bias: average confidence vs. realized correctness
    """
    since = (datetime.now() - timedelta(days=since_days)).isoformat()
    shop_clause = "" if shop_id is None else " AND p.shop_id = ?"
    params = () if shop_id is None else (shop_id,)

    insights: list[dict] = []
    with db._connect() as conn:
        rows = conn.execute(
            f"""
            SELECT p.id, p.shop_id, p.model_name, p.model_version, p.confidence,
                   f.label, f.rating
            FROM predictions p
            LEFT JOIN feedback f ON f.prediction_id = p.id
            WHERE p.predicted_at >= ? {shop_clause}
            """,
            (since, *params),
        ).fetchall()

    by_model: dict[str, dict] = {}
    for r in rows:
        key = f"{r['model_name']}:{r['model_version']}"
        agg = by_model.setdefault(
            key, {"n": 0, "correct": 0, "wrong": 0, "conf_sum": 0.0}
        )
        agg["n"] += 1
        agg["conf_sum"] += r["confidence"] or 0.0
        if r["label"] == "correct":
            agg["correct"] += 1
        elif r["label"] == "wrong":
            agg["wrong"] += 1

    for key, agg in by_model.items():
        n = agg["n"]
        accuracy = (
            (agg["correct"] / (agg["correct"] + agg["wrong"]))
            if (agg["correct"] + agg["wrong"])
            else None
        )
        avg_conf = agg["conf_sum"] / n if n else None
        sid = _persist(
            shop_id,
            "accuracy",
            f"Model {key} accuracy",
            {
                "model": key,
                "samples": n,
                "correct": agg["correct"],
                "wrong": agg["wrong"],
                "avg_confidence": round(avg_conf, 4) if avg_conf is not None else None,
            },
            accuracy,
        )
        row = db.fetchone("SELECT * FROM learning_insights WHERE id = ?", (sid,))
        if row is not None:
            insights.append(row)

        if accuracy is not None and avg_conf is not None and avg_conf - accuracy > 0.15:
            sid = _persist(
                shop_id,
                "bias",
                f"Overconfidence in {key}",
                {
                    "model": key,
                    "avg_confidence": round(avg_conf, 4),
                    "accuracy": round(accuracy, 4),
                },
                round(avg_conf - accuracy, 4),
            )
            row = db.fetchone("SELECT * FROM learning_insights WHERE id = ?", (sid,))
            if row is not None:
                insights.append(row)

    return insights


def _persist(shop_id, insight_type, title, detail, metric_value) -> int:
    return db.insert(
        "learning_insights",
        shop_id=shop_id,
        insight_type=insight_type,
        title=title,
        detail=detail,
        metric_value=metric_value,
    )
