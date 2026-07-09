"""Performance tracking and analytics for the predictive engine."""
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
import numpy as np
from backend.models.model_performance import ModelPerformance, GlobalModelWeights, RulePerformance
from backend.models.feedback_event import FeedbackEvent
from backend.models.prediction import Prediction
from backend.models.workflow_rule import WorkflowRule

logger = logging.getLogger(__name__)


class PerformanceTracker:
    """Tracks and aggregates performance metrics across models and rules."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def track_rule_performance(
        self,
        workflow_rule_id: str,
        product_id: Optional[str],
        did_fire: bool,
        action_result: str,  # successful | neutral | negative
        roi: Optional[float] = None,
    ) -> RulePerformance:
        """Track individual rule execution outcome."""
        try:
            # Get or create rule performance for today
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)

            stmt = select(RulePerformance).where(
                and_(
                    RulePerformance.workflow_rule_id == workflow_rule_id,
                    RulePerformance.product_id == product_id,
                    RulePerformance.evaluation_period_start == today_start,
                )
            )
            result = await self.db.execute(stmt)
            perf = result.scalars().first()

            if not perf:
                # Create new performance record for today
                perf = RulePerformance(
                    workflow_rule_id=workflow_rule_id,
                    product_id=product_id,
                    evaluation_period_start=today_start,
                    evaluation_period_end=today_end,
                )
                self.db.add(perf)

            # Update metrics
            perf.total_executions += 1
            if did_fire:
                perf.times_rule_fired += 1
                
                if action_result == "successful":
                    perf.times_action_successful += 1
                elif action_result == "neutral":
                    perf.times_action_neutral += 1
                elif action_result == "negative":
                    perf.times_action_negative += 1
            
            # Calculate effectiveness
            perf.success_rate = (perf.successful_executions / perf.total_executions * 100) if perf.total_executions > 0 else 0
            perf.effectiveness_score = (
                perf.times_action_successful / perf.times_rule_fired
            ) if perf.times_rule_fired > 0 else 0
            
            if roi is not None:
                perf.roi = roi

            await self.db.commit()
            await self.db.refresh(perf)
            return perf
        except Exception as e:
            logger.error(f"Failed to track rule performance: {str(e)}")
            await self.db.rollback()
            return None

    async def get_model_comparison(
        self,
        days: int = 30,
        product_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compare performance of different model versions."""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            stmt = select(ModelPerformance).where(
                ModelPerformance.evaluation_period_start >= cutoff_date
            )
            if product_id:
                stmt = stmt.where(ModelPerformance.product_id == product_id)

            result = await self.db.execute(stmt)
            performances = result.scalars().all()

            if not performances:
                return {"message": "No performance data available"}

            # Group by model type and version
            comparison = {}
            for perf in performances:
                key = f"{perf.model_type}_v{perf.model_version}"
                comparison[key] = {
                    "model_type": perf.model_type,
                    "version": perf.model_version,
                    "accuracy_percent": perf.accuracy_percent,
                    "mae": perf.mae,
                    "mape": perf.mape,
                    "rmse": perf.rmse,
                    "direction_accuracy": perf.direction_accuracy,
                    "drift_detected": perf.drift_detected,
                    "predictions_evaluated": perf.predictions_evaluated,
                    "created_at": perf.created_at.isoformat(),
                }

            return comparison
        except Exception as e:
            logger.error(f"Failed to get model comparison: {str(e)}")
            return {"error": str(e)}

    async def get_rule_effectiveness_ranking(
        self,
        days: int = 30,
        min_executions: int = 5,
    ) -> List[Dict[str, Any]]:
        """Rank rules by effectiveness."""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            stmt = select(RulePerformance).where(
                and_(
                    RulePerformance.evaluation_period_start >= cutoff_date,
                    RulePerformance.total_executions >= min_executions,
                )
            ).order_by(desc(RulePerformance.effectiveness_score))

            result = await self.db.execute(stmt)
            performances = result.scalars().all()

            ranking = [
                {
                    "rule_id": str(perf.workflow_rule_id),
                    "product_id": str(perf.product_id) if perf.product_id else "global",
                    "effectiveness_score": perf.effectiveness_score,
                    "success_rate": perf.success_rate,
                    "total_executions": perf.total_executions,
                    "successful_actions": perf.times_action_successful,
                    "neutral_actions": perf.times_action_neutral,
                    "negative_actions": perf.times_action_negative,
                    "roi": perf.roi,
                }
                for perf in performances
            ]

            return ranking
        except Exception as e:
            logger.error(f"Failed to get rule effectiveness ranking: {str(e)}")
            return []

    async def get_drift_alerts(
        self,
        drift_threshold: float = 0.15,  # 15% change triggers alert
    ) -> List[Dict[str, Any]]:
        """Get models with detected drift."""
        try:
            stmt = select(ModelPerformance).where(
                and_(
                    ModelPerformance.drift_detected == True,
                    ModelPerformance.drift_magnitude > drift_threshold,
                )
            ).order_by(desc(ModelPerformance.drift_magnitude))

            result = await self.db.execute(stmt)
            drifts = result.scalars().all()

            alerts = [
                {
                    "model_type": drift.model_type,
                    "model_version": drift.model_version,
                    "product_id": str(drift.product_id) if drift.product_id else "global",
                    "drift_magnitude": drift.drift_magnitude,
                    "previous_accuracy": drift.performance_before,
                    "detected_at": drift.evaluation_period_end.isoformat(),
                    "recommendation": "Consider retraining or rolling back to previous version",
                }
                for drift in drifts
            ]

            return alerts
        except Exception as e:
            logger.error(f"Failed to get drift alerts: {str(e)}")
            return []

    async def get_global_metrics(
        self,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Get aggregate metrics across all models and rules."""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            # Feedback metrics
            stmt = select(FeedbackEvent).where(FeedbackEvent.created_at >= cutoff_date)
            result = await self.db.execute(stmt)
            feedbacks = result.scalars().all()

            # Model performance
            stmt = select(ModelPerformance).where(
                ModelPerformance.evaluation_period_start >= cutoff_date
            )
            result = await self.db.execute(stmt)
            model_perfs = result.scalars().all()

            # Rule performance
            stmt = select(RulePerformance).where(
                RulePerformance.evaluation_period_start >= cutoff_date
            )
            result = await self.db.execute(stmt)
            rule_perfs = result.scalars().all()

            # Calculate metrics
            total_feedback = len(feedbacks)
            correct = sum(1 for f in feedbacks if f.prediction_correct) if feedbacks else 0
            avg_accuracy = (correct / total_feedback * 100) if total_feedback else 0
            
            avg_mape = np.mean([mp.mape for mp in model_perfs]) if model_perfs else 0
            avg_rule_effectiveness = np.mean([rp.effectiveness_score for rp in rule_perfs]) if rule_perfs else 0

            return {
                "period_days": days,
                "feedback_samples": total_feedback,
                "overall_accuracy_percent": avg_accuracy,
                "avg_mape": avg_mape,
                "models_evaluated": len(model_perfs),
                "rules_tracked": len(rule_perfs),
                "average_rule_effectiveness": avg_rule_effectiveness,
                "drift_detected_count": sum(1 for mp in model_perfs if mp.drift_detected),
                "models_needing_retraining": sum(1 for mp in model_perfs if mp.accuracy_percent < 70),
            }
        except Exception as e:
            logger.error(f"Failed to get global metrics: {str(e)}")
            return {"error": str(e)}
