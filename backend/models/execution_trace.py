from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSON
from datetime import datetime
import uuid
from backend.database import Base


class ExecutionTrace(Base):
    """Debug traces for prediction and rule execution."""
    __tablename__ = "execution_traces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prediction_id = Column(UUID(as_uuid=True), ForeignKey("predictions.id"), index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), index=True)
    execution_type = Column(String(100), nullable=False, index=True)  # demand_forecast | rule_evaluation | anomaly_detection
    
    # Neural layer trace
    neural_inputs = Column(JSON)  # {"historical_data": [...], "periods": 30}
    neural_outputs = Column(JSON)  # {"forecast": 150, "confidence": 0.85, "trend": "up"}
    neural_model_version = Column(String(50))  # Model version used
    neural_execution_time_ms = Column(Float)  # Performance metric
    
    # Symbolic layer trace
    rules_evaluated = Column(JSON)  # [{"rule_name": "...", "fired": true/false, "conditions": [...]}]
    rules_applied = Column(JSON)  # [{"action": "...", "params": {...}}]
    symbolic_execution_time_ms = Column(Float)
    
    # Hybrid combination
    hybrid_reasoning = Column(JSON)  # {"neural_weight": 0.6, "combined_value": 155, "final_confidence": 0.82}
    decision_path = Column(Text)  # Human-readable decision tree
    
    # Debugging info
    feature_values = Column(JSON)  # Input features used
    intermediate_results = Column(JSON)  # Any intermediate calculations
    warnings = Column(String(500))  # Any warnings during execution
    error = Column(String(500))  # If execution failed
    
    # Performance tracking
    total_execution_time_ms = Column(Float)
    memory_used_mb = Column(Float)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
