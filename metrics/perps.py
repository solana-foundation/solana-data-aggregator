"""Perpetual futures (perps) metric models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from numbers import Real

from metrics.base import BaseMetric


class PerpsMetricType(str, Enum):
    """Supported perps metric categories."""

    TRADING_VOLUME = "trading_volume"
    TRADERS = "traders"
    TRANSACTIONS = "transactions"
    OPEN_INTEREST_DOUBLE_SIDED = "open_interest_double_sided"
    OPEN_INTEREST_SINGLE_SIDED = "open_interest_single_sided"
    VENUE_COUNT = "venue_count"


_METRIC_METADATA: dict[PerpsMetricType, dict[str, str]] = {
    PerpsMetricType.TRADING_VOLUME: {
        "name": "Trading Volume",
        "unit": "USD",
        "description": "Daily perpetual futures trading volume across Solana perp venues in USD",
    },
    PerpsMetricType.TRADERS: {
        "name": "Traders",
        "unit": "Count",
        "description": "Number of unique daily traders on Solana perp venues",
    },
    PerpsMetricType.TRANSACTIONS: {
        "name": "Transactions",
        "unit": "Count",
        "description": "Number of perpetual futures trades on Solana perp venues per day",
    },
    PerpsMetricType.OPEN_INTEREST_DOUBLE_SIDED: {
        "name": "Total OI (Double-Sided)",
        "unit": "USD",
        "description": "Total open interest across Solana perp venues in USD, double-sided (long and short both counted)",
    },
    PerpsMetricType.OPEN_INTEREST_SINGLE_SIDED: {
        "name": "Total OI (Single-Sided)",
        "unit": "USD",
        "description": "Total open interest across Solana perp venues in USD, single-sided (one side of each position counted)",
    },
    PerpsMetricType.VENUE_COUNT: {
        "name": "Venue Count",
        "unit": "Count",
        "description": "Number of Solana perp venues with trading activity",
    },
}


@dataclass
class Perps(BaseMetric):
    """Concrete metric model for perps datasets."""

    metric_type: PerpsMetricType

    @classmethod
    def from_metric_type(
        cls,
        metric_type: PerpsMetricType,
        date: date,
        value: Real,
    ) -> "Perps":
        """Build a perps metric using canonical metadata."""
        metadata = _METRIC_METADATA[metric_type]
        return cls(
            metric_type=metric_type,
            name=metadata["name"],
            unit=metadata["unit"],
            description=metadata["description"],
            date=date,
            value=value,
        )
