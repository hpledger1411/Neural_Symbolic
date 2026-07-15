"""RulesEngine: the symbolic half of the neuro-symbolic engine.

Applies deterministic business logic and guardrails over Forecaster scores and
emits human-readable explanations. Pure functions over typed inputs so they are
testable and explainable (key property of neuro-symbolic systems).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.forecaster import ForecastResult

# Symbolic thresholds — the "knowledge" the engine reasons with.
LOW_STOCK_GUARD = 5
HIGH_CONFIDENCE = 0.7
REORDER_TRIGGER_DEMAND = 10.0


@dataclass
class Decision:
    product_id: str
    action: str  # "reorder" | "hold" | "review"
    explanation: str
    triggered_rules: list[str] = field(default_factory=list)


class RulesEngine:
    """Symbolic rule layer over neural forecasts.

    Rules are evaluated in priority order; the first matching guardrail wins,
    and every decision carries the list of rules that fired plus a natural
    language explanation.
    """

    def decide(self, forecast: ForecastResult, inventory_qty: int | None) -> Decision:
        rules: list[str] = []

        # Guardrail: never recommend a reorder when stock is already adequate.
        if inventory_qty is not None and inventory_qty >= LOW_STOCK_GUARD:
            rules.append("guardrail:stock_adequate")
            return Decision(
                product_id=forecast.product_id,
                action="hold",
                explanation=(
                    f"Stock {inventory_qty} >= guard {LOW_STOCK_GUARD}; "
                    f"no reorder despite demand {forecast.predicted_demand:.2f}."
                ),
                triggered_rules=rules,
            )

        # Low-confidence forecasts require human review rather than auto-action.
        if forecast.confidence < HIGH_CONFIDENCE:
            rules.append("rule:low_confidence_review")
            return Decision(
                product_id=forecast.product_id,
                action="review",
                explanation=(
                    f"Forecast confidence {forecast.confidence:.2f} < "
                    f"{HIGH_CONFIDENCE}; route to human review."
                ),
                triggered_rules=rules,
            )

        # High demand + low stock -> automated reorder.
        if forecast.predicted_demand >= REORDER_TRIGGER_DEMAND:
            rules.append("rule:high_demand_reorder")
            return Decision(
                product_id=forecast.product_id,
                action="reorder",
                explanation=(
                    f"Predicted demand {forecast.predicted_demand:.2f} >= "
                    f"{REORDER_TRIGGER_DEMAND} with stock {inventory_qty}; "
                    f"auto-reorder (conf {forecast.confidence:.2f})."
                ),
                triggered_rules=rules,
            )

        rules.append("rule:default_hold")
        return Decision(
            product_id=forecast.product_id,
            action="hold",
            explanation="No trigger met; hold.",
            triggered_rules=rules,
        )
