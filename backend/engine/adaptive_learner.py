"""Adaptive learning engine that improves model and rules based on feedback."""
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
import numpy as np
from backend.models.feedback_event import FeedbackEvent
from backend.models.model_performance import ModelPerformance, GlobalModelWeights, RulePerformance
from backend.models.workflow_rule import WorkflowRule
from backend.models.prediction import Prediction

logger = logging.getLogger(__name__)


class AdaptiveLearner:
    """Learns from prediction feedback and auto-tunes model weights and rule thresholds."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.learning_rate = 0.01
        self.momentum = 0.9
        self.min_samples_for_update = 50  # Need at least 50 feedback samples

    async def record_feedback(
        self,
        prediction_id: str,
        product_id: str,
        predicted_value: float,
        actual_value: float,
        feedback_type: str,
        external_factors: Optional[Dict[str, Any]] = None,
        contributing_factors: Optional[str] = None,
        accuracy_threshold: float = 10.0,
    ) -> FeedbackEvent:
        """Record actual outcome for a prediction to enable learning."""
        try:
            # Get original prediction
            stmt = select(Prediction).where(Prediction.id == prediction_id)
            result = await self.db.execute(stmt)
            prediction = result.scalars().first()

            if not prediction:
                logger.warning(f"Prediction {prediction_id} not found")
                return None

            # Calculate error metrics
            error = actual_value - predicted_value
            error_percentage = (error / actual_value * 100) if actual_value != 0 else 0
            abs_error_percentage = abs(error_percentage)
            
            # Determine if prediction was correct
            prediction_correct = abs_error_percentage <= accuracy_threshold

            # Calculate days until feedback (prediction horizon)
            days_until = None
            if prediction.prediction_date and prediction.target_date:
                days_until = (prediction.target_date - prediction.prediction_date).days

            # Create feedback event
            feedback = FeedbackEvent(
                prediction_id=prediction_id,
                product_id=product_id,
                predicted_value=predicted_value,
                actual_value=actual_value,
                error=error,
                error_percentage=error_percentage,
                absolute_error_percentage=abs_error_percentage,
                prediction_correct=prediction_correct,
                accuracy_threshold_percent=accuracy_threshold,
                feedback_type=feedback_type,
                feedback_date=datetime.utcnow(),
                prediction_date=prediction.prediction_date,
                days_until_feedback=days_until,
                external_factors=external_factors,
                contributing_factors=contributing_factors,
                should_retrain=abs_error_percentage > accuracy_threshold * 2,  # Big errors trigger retraining
                learning_signal_strength=min(1.0, abs_error_percentage / 50.0),  # Normalize
            )

            self.db.add(feedback)
            await self.db.commit()
            await self.db.refresh(feedback)

            logger.info(
                f"Feedback recorded: prediction={prediction_id}, "
                f"predicted={predicted_value:.2f}, actual={actual_value:.2f}, "
                f"error={error_percentage:.2f}%, correct={prediction_correct}"
            )

            return feedback
        except Exception as e:
            logger.error(f"Failed to record feedback: {str(e)}")
            await self.db.rollback()
            return None

    async def evaluate_model_performance(
        self,
        model_type: str,
        model_version: str,
        product_id: Optional[str] = None,
        evaluation_days: int = 30,
    ) -> ModelPerformance:
        """Evaluate model performance over time period."""
        try:
            # Get feedback from period
            cutoff_date = datetime.utcnow() - timedelta(days=evaluation_days)
            
            stmt = select(FeedbackEvent).where(
                and_(
                    FeedbackEvent.created_at >= cutoff_date,
                    FeedbackEvent.feedback_type == model_type,
                )
            )
            
            if product_id:
                stmt = stmt.where(FeedbackEvent.product_id == product_id)
            
            result = await self.db.execute(stmt)
            feedbacks = result.scalars().all()

            if not feedbacks:
                logger.warning(f"No feedback found for {model_type}")
                return None

            # Calculate metrics
            values = [f.actual_value for f in feedbacks]
            predictions = [f.predicted_value for f in feedbacks]
            errors = [f.error for f in feedbacks]
            abs_errors = [f.absolute_error_percentage for f in feedbacks]

            mae = np.mean(np.abs(errors))
            mape = np.mean(abs_errors)
            rmse = np.sqrt(np.mean(np.array(errors) ** 2))
            accuracy = sum(1 for f in feedbacks if f.prediction_correct) / len(feedbacks) * 100

            # Direction accuracy (for trend)
            correct_direction = 0
            for f in feedbacks:
                pred_direction = 1 if f.predicted_value > 0 else (-1 if f.predicted_value < 0 else 0)
                actual_direction = 1 if f.actual_value > 0 else (-1 if f.actual_value < 0 else 0)
                if pred_direction == actual_direction:
                    correct_direction += 1
            direction_accuracy = (correct_direction / len(feedbacks) * 100) if feedbacks else 0

            # Detect drift
            if len(feedbacks) > 2:
                first_half_acc = sum(1 for f in feedbacks[:len(feedbacks)//2] if f.prediction_correct) / len(feedbacks[:len(feedbacks)//2]) * 100
                second_half_acc = sum(1 for f in feedbacks[len(feedbacks)//2:] if f.prediction_correct) / len(feedbacks[len(feedbacks)//2:]) * 100
                drift_magnitude = abs(first_half_acc - second_half_acc)
                drift_detected = drift_magnitude > 15  # More than 15% difference
            else:
                drift_magnitude = 0
                drift_detected = False

            # Create performance record
            perf = ModelPerformance(
                product_id=product_id,
                model_version=model_version,
                model_type=model_type,
                scope="per_product" if product_id else "global",
                evaluation_period_start=cutoff_date,
                evaluation_period_end=datetime.utcnow(),
                predictions_evaluated=len(feedbacks),
                mae=mae,
                mape=mape,
                rmse=rmse,
                accuracy_percent=accuracy,
                direction_accuracy=direction_accuracy,
                avg_predicted_confidence=np.mean([f.error_percentage for f in feedbacks]),
                predictions_correct=sum(1 for f in feedbacks if f.prediction_correct),
                predictions_incorrect=sum(1 for f in feedbacks if not f.prediction_correct),
                drift_detected=drift_detected,
                drift_magnitude=drift_magnitude,
                data_used={"samples": len(feedbacks), "date_range": f"{cutoff_date} to {datetime.utcnow()}"},
            )

            self.db.add(perf)
            await self.db.commit()
            await self.db.refresh(perf)

            logger.info(
                f"Model performance evaluated: {model_type} (v{model_version}), "
                f"MAE={mae:.2f}, MAPE={mape:.2f}%, Accuracy={accuracy:.2f}%"
            )

            return perf
        except Exception as e:
            logger.error(f"Failed to evaluate model performance: {str(e)}")
            await self.db.rollback()
            return None

    async def auto_tune_global_weights(
        self,
        feedback_lookback_days: int = 30,
    ) -> Optional[GlobalModelWeights]:
        """Auto-tune global neural weights based on feedback."""
        try:
            # Get current weights
            stmt = select(GlobalModelWeights).order_by(desc(GlobalModelWeights.created_at))
            result = await self.db.execute(stmt)
            current_weights = result.scalars().first()

            if not current_weights:
                logger.warning("No global weights found")
                return None

            # Get recent feedback
            cutoff_date = datetime.utcnow() - timedelta(days=feedback_lookback_days)
            stmt = select(FeedbackEvent).where(FeedbackEvent.created_at >= cutoff_date)
            result = await self.db.execute(stmt)
            feedbacks = result.scalars().all()

            if len(feedbacks) < self.min_samples_for_update:
                logger.info(f"Not enough samples ({len(feedbacks)}) for weight update")
                return None

            # Calculate performance metrics
            errors = np.array([f.absolute_error_percentage for f in feedbacks])
            learning_signals = np.array([f.learning_signal_strength for f in feedbacks])

            # Analyze which predictions were most accurate
            correct_predictions = [f for f in feedbacks if f.prediction_correct]
            
            # Adjust neural weight based on accuracy
            if correct_predictions:
                improvement_factor = len(correct_predictions) / len(feedbacks)
                if improvement_factor > 0.8:
                    # Neural layer is doing well, increase its weight
                    new_neural_weight = min(
                        1.0,
                        current_weights.neural_weight + self.learning_rate
                    )
                elif improvement_factor < 0.6:
                    # Neural layer underperforming, decrease weight and boost symbolic
                    new_neural_weight = max(
                        0.3,
                        current_weights.neural_weight - self.learning_rate
                    )
                else:
                    new_neural_weight = current_weights.neural_weight
            else:
                new_neural_weight = current_weights.neural_weight

            # Adjust anomaly detection threshold based on outliers
            outlier_count = sum(1 for e in errors if e > 50)
            if outlier_count / len(errors) > 0.1:  # More than 10% outliers
                # Make anomaly detection stricter
                new_anomaly_threshold = min(
                    4.0,
                    current_weights.anomaly_z_threshold + 0.2
                )
            else:
                new_anomaly_threshold = current_weights.anomaly_z_threshold

            # Adjust seasonality threshold
            seasonal_detected = sum(1 for f in feedbacks if "seasonal" in (f.contributing_factors or ""))
            if seasonal_detected / len(feedbacks) > 0.3:
                # More seasonality, lower threshold to detect it earlier
                new_seasonality_threshold = max(0.4, current_weights.seasonality_threshold - 0.05)
            else:
                new_seasonality_threshold = current_weights.seasonality_threshold

            # Create new weights
            new_weights = GlobalModelWeights(
                forecast_alpha=current_weights.forecast_alpha,
                forecast_beta=current_weights.forecast_beta,
                seasonality_threshold=new_seasonality_threshold,
                anomaly_z_threshold=new_anomaly_threshold,
                neural_weight=new_neural_weight,
                symbolic_weight=1.0 - new_neural_weight,
                confidence_floor=current_weights.confidence_floor,
                confidence_boost=current_weights.confidence_boost,
                learning_rate=self.learning_rate,
                momentum=self.momentum,
                version=current_weights.version + 1,
                previous_version=current_weights.version,
                created_by="adaptive_learner",
                reason=f"Auto-tuned from {len(feedbacks)} feedback samples. "
                       f"Accuracy: {len(correct_predictions)/len(feedbacks)*100:.1f}%. "
                       f"Neural weight adjusted to {new_neural_weight:.2f}",
                performance_before={
                    "accuracy": len(correct_predictions) / len(feedbacks),
                    "mae": float(np.mean(np.abs(errors))),
                },
            )

            self.db.add(new_weights)
            await self.db.commit()
            await self.db.refresh(new_weights)

            logger.info(
                f"Global weights updated to v{new_weights.version}. "
                f"Neural weight: {current_weights.neural_weight:.2f} → {new_neural_weight:.2f}. "
                f"Anomaly threshold: {current_weights.anomaly_z_threshold:.2f} → {new_anomaly_threshold:.2f}"
            )

            return new_weights
        except Exception as e:
            logger.error(f"Failed to auto-tune global weights: {str(e)}")
            await self.db.rollback()
            return None

    async def auto_tune_rule_thresholds(
        self,
        workflow_rule_id: str,
        feedback_lookback_days: int = 30,
    ) -> Tuple[bool, Optional[str], Optional[float]]:
        """Auto-tune symbolic rule thresholds based on outcomes."""
        try:
            # Get rule
            stmt = select(WorkflowRule).where(WorkflowRule.id == workflow_rule_id)
            result = await self.db.execute(stmt)
            rule = result.scalars().first()

            if not rule:
                return False, "Rule not found", None

            # Get recent rule performance
            cutoff_date = datetime.utcnow() - timedelta(days=feedback_lookback_days)
            stmt = select(RulePerformance).where(
                and_(
                    RulePerformance.workflow_rule_id == workflow_rule_id,
                    RulePerformance.evaluation_period_start >= cutoff_date,
                )
            ).order_by(desc(RulePerformance.created_at))
            result = await self.db.execute(stmt)
            performances = result.scalars().all()

            if not performances:
                return False, "No performance data for rule", None

            latest_perf = performances[0]

            # Analyze effectiveness
            if latest_perf.times_action_negative > latest_perf.times_action_successful:
                # Rule is doing more harm than good, recommend loosening threshold
                adjustment = -0.1  # Decrease threshold
                reason = "Rule triggering negatively, recommend loosening threshold"
            elif latest_perf.effectiveness_score > 0.85:
                # Rule is very effective, can be more aggressive
                adjustment = 0.05  # Increase threshold slightly
                reason = "Rule is highly effective, can be more selective"
            elif latest_perf.effectiveness_score < 0.5:
                # Rule is underperforming
                adjustment = -0.15
                reason = "Rule underperforming, recommend significant adjustment"
            else:
                # Rule is OK, no major adjustment needed
                adjustment = 0
                reason = "Rule performing adequately, no adjustment needed"

            # Calculate recommended threshold
            current_threshold = latest_perf.current_threshold
            if current_threshold and adjustment != 0:
                recommended_threshold = current_threshold * (1 + adjustment)
                
                # Update rule config
                import json
                rule_config = rule.rule_config if isinstance(rule.rule_config, dict) else json.loads(rule.rule_config)
                
                # Find and update threshold in conditions
                for condition in rule_config.get("conditions", []):
                    if "value" in condition:
                        condition["value"] = recommended_threshold
                        break
                
                rule.rule_config = rule_config
                await self.db.commit()
                
                logger.info(
                    f"Rule {workflow_rule_id} threshold auto-tuned: "
                    f"{current_threshold:.2f} → {recommended_threshold:.2f}. {reason}"
                )
                
                return True, reason, recommended_threshold
            else:
                return True, reason, current_threshold

        except Exception as e:
            logger.error(f"Failed to auto-tune rule thresholds: {str(e)}")
            await self.db.rollback()
            return False, str(e), None

    async def get_learning_insights(
        self,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Generate insights from learning data."""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            # Get feedback summary
            stmt = select(FeedbackEvent).where(FeedbackEvent.created_at >= cutoff_date)
            result = await self.db.execute(stmt)
            feedbacks = result.scalars().all()

            if not feedbacks:
                return {"message": "No feedback data available", "days": days}

            # Calculate aggregate metrics
            total_predictions = len(feedbacks)
            correct_predictions = sum(1 for f in feedbacks if f.prediction_correct)
            accuracy = correct_predictions / total_predictions * 100 if total_predictions else 0
            avg_error = np.mean([abs(f.error_percentage) for f in feedbacks])
            
            # Find worst performing products
            product_errors = {}
            for f in feedbacks:
                if f.product_id not in product_errors:
                    product_errors[f.product_id] = []
                product_errors[f.product_id].append(abs(f.error_percentage))
            
            worst_products = sorted(
                [(pid, np.mean(errs)) for pid, errs in product_errors.items()],
                key=lambda x: x[1],
                reverse=True
            )[:5]

            # Get model versions and their performance
            stmt = select(ModelPerformance).where(
                ModelPerformance.evaluation_period_start >= cutoff_date
            ).order_by(desc(ModelPerformance.created_at))
            result = await self.db.execute(stmt)
            model_perfs = result.scalars().all()

            return {
                "period_days": days,
                "total_feedback_samples": total_predictions,
                "overall_accuracy_percent": accuracy,
                "average_error_percent": avg_error,
                "worst_performing_products": [
                    {"product_id": str(pid), "avg_error_percent": err} 
                    for pid, err in worst_products
                ],
                "model_performance_summary": [
                    {
                        "model_type": mp.model_type,
                        "version": mp.model_version,
                        "accuracy_percent": mp.accuracy_percent,
                        "mape": mp.mape,
                        "drift_detected": mp.drift_detected,
                    }
                    for mp in model_perfs
                ],
                "learning_signals": {
                    "high_signal_events": sum(1 for f in feedbacks if f.learning_signal_strength > 0.8),
                    "external_factors_noted": sum(1 for f in feedbacks if f.external_factors),
                },
            }
        except Exception as e:
            logger.error(f"Failed to generate learning insights: {str(e)}")
            return {"error": str(e)}
