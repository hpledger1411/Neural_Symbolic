"""Pydantic models for Gbox API."""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Optional


class PredictionIn(BaseModel):
    shop_id: int
    model_name: str
    model_version: str
    entity_type: str
    entity_id: str
    prediction: Any
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    features: Optional[dict] = None


class TraceIn(BaseModel):
    shop_id: Optional[int] = None
    trace_id: str
    parent_id: Optional[str] = None
    span_name: str
    kind: Optional[str] = None
    input: Optional[Any] = None
    output: Optional[Any] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    duration_ms: Optional[int] = None


class FeedbackIn(BaseModel):
    shop_id: Optional[int] = None
    prediction_id: Optional[int] = None
    trace_id: Optional[str] = None
    rating: Optional[int] = None
    label: Optional[str] = None
    comment: Optional[str] = None
    source: str = "human"


class ShopIn(BaseModel):
    shop_domain: str
    access_token: Optional[str] = None
    scope: Optional[str] = None


class ProductIn(BaseModel):
    shop_id: int
    shopify_id: str
    title: Optional[str] = None
    handle: Optional[str] = None
    price: Optional[float] = None
    inventory_qty: Optional[int] = None
