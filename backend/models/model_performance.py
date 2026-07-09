from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSON
from datetime import datetime
import uuid
from backend.database import Base


class ModelPerformance(Base):
    """Tracks neural model and rule performance over time."""
    __tablename__ = "model_performance"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), index=True)
    
    # Model identification
    model_version = Column(String(50), nullable=False, index=True)  # e.g., "v1.2.3"
    model_type = Column(String(100), nullable=False, index=True)  # demand_forecast | seasonal | anomaly
    scope = Column(String(50), nullable=False, default="global")  # global | per_product | per_category
    
    # Time window
    evaluation_period_start = Column(DateTime, nullable=False, index=True)
    evaluation_period_end = Column(DateTime, nullable=False, index=True)
    predictions_evaluated = Column(Integer, default=0)  # Number of predictions in period
    
    # Accuracy metrics
    mae = Column(Float)  # Mean Absolute Error
    mape = Column(Float)  # Mean Absolute Percentage Error
    rmse = Column(Float)  # Root Mean Squared Error
    accuracy_percent = Column(Float)  # % correct predictions within threshold
    
    # Directional metrics (for trend predictions)
    direction_accuracy = Column(Float)  # % predictions got trend direction right
    
    # Confidence calibration
    avg_predicted_confidence = Column(Float)  # Average confidence of predictions
    calibration_error = Column(Float)  # How well confidence matches actual accuracy
    
    # Learning metrics
    predictions_correct = Column(Integer, default=0)
    predictions_incorrect = Column(Integer, default=0)
    outlier_predictions = Column(Integer, default=0)  # Predictions with huge errors
    
    # Drift detection
    drift_detected = Column(Integer, default=0)  # Boolean: 0 | 1
    drift_magnitude = Column(Float)  # How much performance changed from previous period
    
    # Rule performance (if applicable)
    rule_accuracy = Column(Float)  # % of symbolic rules that improved predictions
    rule_coverage = Column(Float)  # % of predictions covered by rules
    
    # Metadata
    data_used = Column(JSON)  # {"train_samples": 1000, "date_range": "2024-01-01 to 2024-01-31"}
    notes = Column(String(500))
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class GlobalModelWeights(Base):
    """Adaptive weights for global neural layer tuning."""
    __tablename__ = "global_model_weights"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Neural layer weights
    forecast_alpha = Column(Float, default=0.3)  # Exponential smoothing factor
    forecast_beta = Column(Float, default=0.5)  # Trend smoothing factor
    seasonality_threshold = Column(Float, default=0.6)  # Min ACF for seasonality
    anomaly_z_threshold = Column(Float, default=3.0)  # Z-score threshold
    
    # Hybrid combination weights
    neural_weight = Column(Float, default=0.6)  # Weight for neural vs symbolic (0-1)
    symbolic_weight = Column(Float, default=0.4)  # Weight for symbolic (1 - neural_weight)
    
    # Confidence calibration
    confidence_floor = Column(Float, default=0.5)  # Min confidence to make recommendation
    confidence_boost = Column(Float, default=1.0)  # Multiplier for stable patterns
    
    # Learning parameters
    learning_rate = Column(Float, default=0.01)  # How fast to adapt weights
    momentum = Column(Float, default=0.9)  # Momentum for gradient-like updates
    regularization = Column(Float, default=0.1)  # L2 regularization
    
    # Version control
    version = Column(Integer, default=1)
    previous_version = Column(Integer)  # Link to previous weights for rollback
    created_by = Column(String(100))  # System or user who set weights
    reason = Column(String(500))  # Why weights were changed
    
    # Performance snapshot
    performance_before = Column(JSON)  # Metrics before these weights
    performance_after = Column(JSON)  # Metrics after these weights
    was_effective = Column(Integer)  # Boolean: 0 | 1
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    class Config:
        # Current weights are marked
        pass


class RulePerformance(Base):
    """Tracks individual workflow rule effectiveness."""
    __tablename__ = "rule_performance"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_rule_id = Column(UUID(as_uuid=True), ForeignKey("workflow_rules.id"), index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), index=True)
    
    # Execution history
    total_executions = Column(Integer, default=0)
    successful_executions = Column(Integer, default=0)
    failed_executions = Column(Integer, default=0)
    success_rate = Column(Float)  # percentage
    
    # Outcome tracking
    times_rule_fired = Column(Integer, default=0)  # Conditions matched
    times_action_successful = Column(Integer, default=0)  # Action had desired effect
    times_action_neutral = Column(Integer, default=0)  # No negative or positive effect
    times_action_negative = Column(Integer, default=0)  # Action had undesired effect
    
    # Effectiveness
    effectiveness_score = Column(Float)  # 0-1, success_action / total_executions
    roi = Column(Float)  # Return on investment (business metric)
    
    # Thresholds from rule (auto-tuned)
    current_threshold = Column(Float)  # Current threshold value in rule
    recommended_threshold = Column(Float)  # Auto-tuned recommendation
    threshold_adjusted = Column(Integer, default=0)  # Boolean: 0 | 1
    
    # Time period
    evaluation_period_start = Column(DateTime, nullable=False, index=True)
    evaluation_period_end = Column(DateTime, nullable=False, index=True)
    
    # Insights
    insights = Column(JSON)  # {"pattern": "rule fires too often", "suggestion": "increase threshold"}
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
