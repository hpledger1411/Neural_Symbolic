"""API routes for predictions."""
import logging
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID
from backend.database import get_db
from backend.api.schemas import (
    PredictionRequest,
    PredictionResponse,
)
from backend.engine.neuro_symbolic import NeuroSymbolicEngine
from backend.engine.rules_engine import RulesEngine
from backend.engine.forecaster import Forecaster
from backend.engine.debug_tracer import DebugTracer
from backend.models.prediction import Prediction
from sqlalchemy import select
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/demand", response_model=PredictionResponse)
async def predict_demand(
    request: PredictionRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Generate demand forecast for a product."""
    try:
        rules_engine = RulesEngine()
        forecaster = Forecaster()
        engine = NeuroSymbolicEngine(rules_engine, forecaster)
        tracer = DebugTracer(db)
        
        execution_id = f"demand_{request.product_id}_{id(request)}"
        tracer.start_trace(execution_id, "demand_forecast")
        
        result = await engine.predict_demand(
            product_id=str(request.product_id),
            history_data=request.history_data,
            days_ahead=request.days_ahead,
        )
        
        tracer.log_neural_outputs(
            execution_id,
            result["reasoning"]["neural_signals"],
            duration_ms=15.0,
        )
        
        tracer.log_rules_applied(
            execution_id,
            result["reasoning"]["symbolic_rules_applied"],
            duration_ms=8.0,
        )
        
        prediction = Prediction(
            product_id=request.product_id,
            prediction_type="demand",
            predicted_value=result["predicted_value"],
            confidence_score=result["confidence_score"],
            reasoning=result["reasoning"],
            recommendation=result["recommendation"],
            recommendation_severity=result.get("recommendation_severity", "info"),
            prediction_date=datetime.utcnow(),
            target_date=datetime.utcnow() + timedelta(days=request.days_ahead),
        )
        
        db.add(prediction)
        await db.commit()
        await db.refresh(prediction)
        
        await tracer.save_trace(
            execution_id,
            str(request.product_id),
            str(prediction.id),
        )
        
        logger.info(f"Demand prediction created: {prediction.id}")
        
        return {
            "prediction_type": result["prediction_type"],
            "predicted_value": result["predicted_value"],
            "confidence_score": result["confidence_score"],
            "reasoning": result["reasoning"],
            "recommendation": result["recommendation"],
            "recommendation_severity": result.get("recommendation_severity", "info"),
        }
    except Exception as e:
        logger.error(f"Demand prediction failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("/seasonality")
async def detect_seasonality(
    request: PredictionRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Detect seasonal patterns in product demand."""
    try:
        rules_engine = RulesEngine()
        forecaster = Forecaster()
        engine = NeuroSymbolicEngine(rules_engine, forecaster)
        
        result = await engine.detect_seasonal_pattern(
            product_id=str(request.product_id),
            history_data=request.history_data,
        )
        
        logger.info(f"Seasonal pattern detected for {request.product_id}")
        return result
    except Exception as e:
        logger.error(f"Seasonality detection failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("/reorder")
async def recommend_reorder(
    product_id: UUID,
    current_inventory: int,
    lead_time_days: int,
    history_data: List[dict],
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get inventory reorder recommendation."""
    try:
        rules_engine = RulesEngine()
        forecaster = Forecaster()
        engine = NeuroSymbolicEngine(rules_engine, forecaster)
        
        result = await engine.recommend_reorder(
            product_id=str(product_id),
            current_inventory=current_inventory,
            lead_time_days=lead_time_days,
            historical_data=history_data,
        )
        
        prediction = Prediction(
            product_id=product_id,
            prediction_type="reorder",
            predicted_value=result["recommended_quantity"],
            confidence_score=0.85,
            reasoning=result["reasoning"],
            recommendation=f"Reorder {result['recommended_quantity']} units",
            recommendation_severity=result["recommendation_severity"],
            prediction_date=datetime.utcnow(),
            target_date=datetime.utcnow() + timedelta(days=lead_time_days),
        )
        
        db.add(prediction)
        await db.commit()
        
        logger.info(f"Reorder recommendation created for {product_id}")
        return result
    except Exception as e:
        logger.error(f"Reorder recommendation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("/anomaly")
async def detect_anomaly(
    product_id: UUID,
    current_value: float,
    history_data: List[dict],
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Detect anomalies in sales or inventory."""
    try:
        rules_engine = RulesEngine()
        forecaster = Forecaster()
        engine = NeuroSymbolicEngine(rules_engine, forecaster)
        
        result = await engine.detect_anomaly(
            product_id=str(product_id),
            current_value=current_value,
            history_data=history_data,
        )
        
        logger.info(f"Anomaly detection completed for {product_id}")
        return result
    except Exception as e:
        logger.error(f"Anomaly detection failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/history")
async def get_prediction_history(
    product_id: Optional[UUID] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> List[dict]:
    """Get prediction history."""
    try:
        stmt = select(Prediction).limit(limit)
        
        if product_id:
            stmt = stmt.where(Prediction.product_id == product_id)
        
        stmt = stmt.order_by(Prediction.created_at.desc())
        result = await db.execute(stmt)
        predictions = result.scalars().all()
        
        return [
            {
                "id": str(p.id),
                "product_id": str(p.product_id),
                "prediction_type": p.prediction_type,
                "predicted_value": p.predicted_value,
                "confidence_score": p.confidence_score,
                "recommendation": p.recommendation,
                "recommendation_severity": p.recommendation_severity,
                "created_at": p.created_at.isoformat(),
            }
            for p in predictions
        ]
    except Exception as e:
        logger.error(f"Failed to get prediction history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
