from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSON
from datetime import datetime
import uuid
from backend.database import Base


class FeedbackEvent(Base):
    """Actual outcomes for predictions to enable adaptive learning."""
    __tablename__ = "feedback_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prediction_id = Column(UUID(as_uuid=True), ForeignKey("predictions.id"), index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), index=True)
    
    # What was predicted vs what actually happened
    predicted_value = Column(Float, nullable=False)
    actual_value = Column(Float, nullable=False)
    error = Column(Float)  # actual - predicted
    error_percentage = Column(Float)  # (error / actual) * 100
    absolute_error_percentage = Column(Float)  # Absolute percentage error
    
    # Classification: was prediction correct?
    prediction_correct = Column(Boolean)  # Correct within threshold?
    accuracy_threshold_percent = Column(Float, default=10.0)  # +/- 10%
    
    # Context
    feedback_type = Column(String(100), nullable=False, index=True)  # demand | inventory | trend | seasonal
    feedback_source = Column(String(100))  # manual | automated | system
    feedback_date = Column(DateTime, nullable=False, index=True)  # When feedback was recorded
    prediction_date = Column(DateTime)  # When prediction was made
    days_until_feedback = Column(Integer)  # How long prediction horizon was
    
    # Root cause analysis
    external_factors = Column(JSON)  # {"weather": "rainy", "promo": true, "holiday": false}
    contributing_factors = Column(String(500))  # Free text explanation
    
    # Learning signals
    should_retrain = Column(Boolean, default=False)  # Flag for retraining
    learning_signal_strength = Column(Float)  # 0-1, how important for learning
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
