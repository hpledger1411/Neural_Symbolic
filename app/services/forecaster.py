"""Forecaster: demand / behavior forecasting with Statsmodels ExponentialSmoothing.

This is the neural half of the neuro-symbolic engine. It fits a Holt-Winters
additive ``ExponentialSmoothing`` model on the supplied history (e.g. Shopify
sales per period) and produces a 1-step-ahead forecast plus a confidence score
derived from in-sample forecast error.

The public interface (``Forecaster.predict`` -> ``ForecastResult``) is unchanged
so ``RulesEngine`` and the ``/api/decisions`` contract are unaffected. For very
short histories where ExponentialSmoothing cannot be fit, it falls back to the
history mean so the pipeline stays operational.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing


@dataclass
class ForecastInput:
    product_id: str
    history: list[float]
    price: float | None = None
    inventory_qty: int | None = None


@dataclass
class ForecastResult:
    product_id: str
    predicted_demand: float
    confidence: float


# Minimum observations ExponentialSmoothing needs (trend+seasonal params).
_MIN_FIT = 2 * 2 + 1
# Periodicity used when seasonal smoothing is enabled (e.g. weekly demand).
_SEASONAL = 7


class Forecaster:
    """ExponentialSmoothing-based demand forecaster."""

    def predict(self, item: ForecastInput) -> ForecastResult:
        y = [float(x) for x in (item.history or [])]
        if len(y) == 0:
            return ForecastResult(
                product_id=item.product_id, predicted_demand=0.0, confidence=0.0
            )

        # Not enough data for a seasonal trend model -> mean forecast, length-based confidence.
        if len(y) < _MIN_FIT:
            predicted = float(np.mean(y))
            confidence = min(1.0, len(y) / float(_MIN_FIT))
            return ForecastResult(
                product_id=item.product_id,
                predicted_demand=round(max(0.0, predicted), 4),
                confidence=round(confidence, 4),
            )

        series = pd.Series(y, dtype=float)
        try:
            use_seasonal = len(y) >= 2 * _SEASONAL
            model = ExponentialSmoothing(
                series,
                trend="add",
                seasonal="add" if use_seasonal else None,
                seasonal_periods=_SEASONAL if use_seasonal else None,
                initialization_method="estimated",
            )
            fitted = model.fit()
            forecast = float(fitted.forecast(1).iloc[0])

            # Confidence from in-sample symmetric MAPE (bounded to [0, 1]).
            fitted_vals = fitted.fittedvalues.to_numpy()
            denom = np.where(series.to_numpy() == 0, 1.0, series.to_numpy())
            mape = float(np.mean(np.abs((series.to_numpy() - fitted_vals) / denom)))
            confidence = max(0.0, min(1.0, 1.0 - mape))
        except Exception:
            # Numerical/edge failure -> robust fallback.
            forecast = float(np.mean(y))
            confidence = min(1.0, len(y) / float(_MIN_FIT))

        return ForecastResult(
            product_id=item.product_id,
            predicted_demand=round(max(0.0, forecast), 4),
            confidence=round(confidence, 4),
        )
