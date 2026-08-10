"""Prediction market metric models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from numbers import Real

from metrics.base import BaseMetric


class PredictionMarketMetricType(str, Enum):
    """Supported prediction market metric categories."""

    TVL = "tvl"
    VOLUME = "volume"
    COUNT = "count"
    TRANSACTIONS = "transactions"
    USERS = "users"


_METRIC_METADATA: dict[PredictionMarketMetricType, dict[str, str]] = {
    PredictionMarketMetricType.TVL: {
        "name": "Prediction Market TVL",
        "unit": "USD",
        "description": "Total value locked in prediction market protocols on Solana, denominated in USD",
    },
    PredictionMarketMetricType.VOLUME: {
        "name": "Prediction Market Volume",
        "unit": "USD",
        "description": "Daily USD value traded on prediction market protocols on Solana",
    },
    PredictionMarketMetricType.COUNT: {
        "name": "Prediction Market Count",
        "unit": "Count",
        "description": "Number of prediction market protocols with on-chain activity on Solana per day",
    },
    PredictionMarketMetricType.TRANSACTIONS: {
        "name": "Prediction Market Transactions",
        "unit": "Count",
        "description": "Number of successful transactions involving prediction market programs on Solana per day",
    },
    PredictionMarketMetricType.USERS: {
        "name": "Prediction Market Users",
        "unit": "Count",
        "description": "Number of unique wallets using prediction market protocols on Solana per day",
    },
}


@dataclass
class PredictionMarket(BaseMetric):
    """Concrete metric model for prediction market datasets."""

    metric_type: PredictionMarketMetricType

    @classmethod
    def from_metric_type(
        cls,
        metric_type: PredictionMarketMetricType,
        date: date,
        value: Real,
    ) -> "PredictionMarket":
        """Build a prediction market metric using canonical metadata."""
        metadata = _METRIC_METADATA[metric_type]
        return cls(
            metric_type=metric_type,
            name=metadata["name"],
            unit=metadata["unit"],
            description=metadata["description"],
            date=date,
            value=value,
        )
