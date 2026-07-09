"""Execution tracing and debugging for neuro-symbolic predictions."""
import logging
import time
import psutil
import os
from typing import Dict, List, Any, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.execution_trace import ExecutionTrace

logger = logging.getLogger(__name__)


class DebugTracer:
    """Captures detailed execution traces for debugging and learning."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.trace_data = {}
        self.start_time = None
        self.process = psutil.Process(os.getpid())

    def start_trace(self, execution_id: str, execution_type: str):
        """Start tracing execution."""
        self.trace_data[execution_id] = {
            "execution_type": execution_type,
            "start_time": time.time(),
            "start_memory_mb": self.process.memory_info().rss / 1024 / 1024,
            "steps": [],
            "warnings": [],
            "error": None,
        }
        logger.debug(f"Trace started: {execution_id} ({execution_type})")

    def log_step(self, execution_id: str, step_name: str, data: Dict[str, Any], duration_ms: float = 0):
        """Log a step in execution."""
        if execution_id not in self.trace_data:
            return

        self.trace_data[execution_id]["steps"].append({
            "name": step_name,
            "data": data,
            "duration_ms": duration_ms,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def log_neural_inputs(self, execution_id: str, inputs: Dict[str, Any]):
        """Log neural layer inputs."""
        if execution_id not in self.trace_data:
            return
        self.trace_data[execution_id]["neural_inputs"] = inputs
        self.log_step(execution_id, "neural_input", {"samples": len(inputs.get("history_data", []))})

    def log_neural_outputs(self, execution_id: str, outputs: Dict[str, Any], duration_ms: float):
        """Log neural layer outputs."""
        if execution_id not in self.trace_data:
            return
        self.trace_data[execution_id]["neural_outputs"] = outputs
        self.trace_data[execution_id]["neural_execution_time_ms"] = duration_ms
        self.log_step(
            execution_id,
            "neural_output",
            {"forecast": outputs.get("value"), "confidence": outputs.get("confidence")},
            duration_ms,
        )

    def log_rules_evaluation(self, execution_id: str, rules_evaluated: List[Dict[str, Any]]):
        """Log symbolic rule evaluation."""
        if execution_id not in self.trace_data:
            return
        self.trace_data[execution_id]["rules_evaluated"] = rules_evaluated
        self.log_step(execution_id, "rules_evaluated", {"rule_count": len(rules_evaluated)})

    def log_rules_applied(self, execution_id: str, rules_applied: List[Dict[str, Any]], duration_ms: float):
        """Log symbolic rule actions."""
        if execution_id not in self.trace_data:
            return
        self.trace_data[execution_id]["rules_applied"] = rules_applied
        self.trace_data[execution_id]["symbolic_execution_time_ms"] = duration_ms
        self.log_step(
            execution_id,
            "rules_applied",
            {"action_count": len(rules_applied)},
            duration_ms,
        )

    def log_hybrid_reasoning(self, execution_id: str, reasoning: Dict[str, Any]):
        """Log hybrid combination logic."""
        if execution_id not in self.trace_data:
            return
        self.trace_data[execution_id]["hybrid_reasoning"] = reasoning
        self.log_step(
            execution_id,
            "hybrid_combination",
            {
                "neural_weight": reasoning.get("neural_weight"),
                "combined_value": reasoning.get("combined_value"),
            },
        )

    def log_warning(self, execution_id: str, warning: str):
        """Log warning during execution."""
        if execution_id not in self.trace_data:
            return
        self.trace_data[execution_id]["warnings"].append(warning)
        logger.warning(f"Trace warning ({execution_id}): {warning}")

    def log_error(self, execution_id: str, error: str):
        """Log error during execution."""
        if execution_id not in self.trace_data:
            return
        self.trace_data[execution_id]["error"] = error
        logger.error(f"Trace error ({execution_id}): {error}")

    def generate_decision_tree(self, execution_id: str) -> str:
        """Generate human-readable decision tree."""
        if execution_id not in self.trace_data:
            return ""

        trace = self.trace_data[execution_id]
        tree = "Decision Tree:\n"
        tree += f"  Type: {trace['execution_type']}\n"
        tree += "  Steps:\n"

        for i, step in enumerate(trace["steps"], 1):
            tree += f"    {i}. {step['name']} ({step['duration_ms']:.2f}ms)\n"
            if step["data"]:
                for key, value in step["data"].items():
                    tree += f"       - {key}: {value}\n"

        if trace["warnings"]:
            tree += "  Warnings:\n"
            for warning in trace["warnings"]:
                tree += f"    - {warning}\n"

        return tree

    async def save_trace(
        self,
        execution_id: str,
        product_id: str,
        prediction_id: Optional[str] = None,
        neural_model_version: str = "v1.0.0",
        feature_values: Optional[Dict[str, Any]] = None,
    ) -> ExecutionTrace:
        """Save complete trace to database."""
        if execution_id not in self.trace_data:
            logger.warning(f"No trace data for {execution_id}")
            return None

        trace = self.trace_data[execution_id]
        end_time = time.time()
        total_time_ms = (end_time - trace["start_time"]) * 1000
        end_memory_mb = self.process.memory_info().rss / 1024 / 1024
        memory_used_mb = end_memory_mb - trace["start_memory_mb"]

        try:
            db_trace = ExecutionTrace(
                prediction_id=prediction_id,
                product_id=product_id,
                execution_type=trace["execution_type"],
                neural_inputs=trace.get("neural_inputs"),
                neural_outputs=trace.get("neural_outputs"),
                neural_model_version=neural_model_version,
                neural_execution_time_ms=trace.get("neural_execution_time_ms"),
                rules_evaluated=trace.get("rules_evaluated"),
                rules_applied=trace.get("rules_applied"),
                symbolic_execution_time_ms=trace.get("symbolic_execution_time_ms"),
                hybrid_reasoning=trace.get("hybrid_reasoning"),
                decision_path=self.generate_decision_tree(execution_id),
                feature_values=feature_values,
                intermediate_results={"steps": trace["steps"]},
                warnings=" | ".join(trace["warnings"]) if trace["warnings"] else None,
                error=trace["error"],
                total_execution_time_ms=total_time_ms,
                memory_used_mb=memory_used_mb,
            )

            self.db.add(db_trace)
            await self.db.commit()
            await self.db.refresh(db_trace)

            logger.info(f"Trace saved: {execution_id} (took {total_time_ms:.2f}ms)")
            return db_trace
        except Exception as e:
            logger.error(f"Failed to save trace: {str(e)}")
            await self.db.rollback()
            return None

    def clear_trace(self, execution_id: str):
        """Clear trace data from memory."""
        if execution_id in self.trace_data:
            del self.trace_data[execution_id]
