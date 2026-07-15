"""Predictions, traces, feedback + insights endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from app import db
from app.models import PredictionIn, TraceIn, FeedbackIn

router = APIRouter(tags=["ml"])


@router.post("/predictions")
def create_prediction(p: PredictionIn):
    pid = db.insert("predictions", **p.model_dump())
    return {"id": pid}


@router.get("/predictions")
def list_predictions(
    shop_id: int | None = None, entity_type: str | None = None, limit: int = 100
):
    clauses: list[str] = []
    params: list[object] = []
    if shop_id is not None:
        clauses.append("shop_id = ?")
        params.append(shop_id)
    if entity_type:
        clauses.append("entity_type = ?")
        params.append(entity_type)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = db.fetchall(
        f"SELECT * FROM predictions {where} ORDER BY predicted_at DESC LIMIT ?",
        (*params, limit),
    )
    for r in rows:
        r["prediction"] = db._jload(r["prediction"])
        r["features"] = db._jload(r["features"])
    return rows


@router.post("/traces")
def create_trace(t: TraceIn):
    tid = db.insert("traces", **t.model_dump())
    return {"id": tid}


@router.get("/traces")
def list_traces(shop_id: int | None = None, limit: int = 100):
    clauses: list[str] = []
    params: list[object] = []
    if shop_id is not None:
        clauses.append("shop_id = ?")
        params.append(shop_id)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = db.fetchall(
        f"SELECT * FROM traces {where} ORDER BY started_at DESC LIMIT ?",
        (*params, limit),
    )
    for r in rows:
        r["input"] = db._jload(r["input"])
        r["output"] = db._jload(r["output"])
    return rows


@router.post("/feedback")
def create_feedback(f: FeedbackIn):
    fid = db.insert("feedback", **f.model_dump())
    return {"id": fid}


@router.get("/feedback")
def list_feedback(prediction_id: int | None = None):
    clauses: list[str] = []
    params: list[object] = []
    if prediction_id is not None:
        clauses.append("prediction_id = ?")
        params.append(prediction_id)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return db.fetchall(
        f"SELECT * FROM feedback {where} ORDER BY created_at DESC", tuple(params)
    )


@router.post("/insights/generate")
def generate(shop_id: int | None = None, since_days: int = 30):
    from app.services.insights import generate_insights

    return generate_insights(shop_id, since_days)


@router.get("/insights")
def list_insights(shop_id: int | None = None):
    clauses: list[str] = []
    params: list[object] = []
    if shop_id is not None:
        clauses.append("shop_id = ?")
        params.append(shop_id)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = db.fetchall(
        f"SELECT * FROM learning_insights {where} ORDER BY computed_at DESC",
        tuple(params),
    )
    for r in rows:
        r["detail"] = db._jload(r["detail"])
    return rows
