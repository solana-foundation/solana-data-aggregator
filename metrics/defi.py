"""DeFi metric models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from numbers import Real

from metrics.base import BaseMetric


class DefiMetricType(str, Enum):
    """Supported DeFi metric categories."""

    DEX_VOLUME = "dex_volume"
    DEX_TRADERS = "dex_traders"
    DEX_TRANSACTIONS = "dex_transactions"
    DEX_COUNT = "dex_count"


_METRIC_METADATA: dict[DefiMetricType, dict[str, str]] = {
    DefiMetricType.DEX_VOLUME: {
        "name": "DEX Volume",
        "unit": "USD",
        "description": "Daily spot trading volume across DEXes on Solana in USD",
    },
    DefiMetricType.DEX_TRADERS: {
        "name": "DEX Traders",
        "unit": "Count",
        "description": "Number of unique daily traders on Solana DEXes",
    },
    DefiMetricType.DEX_TRANSACTIONS: {
        "name": "DEX Transactions",
        "unit": "Count",
        "description": "Number of transactions on Solana DEXes per day",
    },
    DefiMetricType.DEX_COUNT: {
        "name": "DEX Count",
        "unit": "Count",
        "description": "Number of supported unique DEXes on Solana",
    },
}


@dataclass
class Defi(BaseMetric):
    """Concrete metric model for DeFi datasets."""

    metric_type: DefiMetricType

    @classmethod
    def from_metric_type(
        cls,
        metric_type: DefiMetricType,
        date: date,
        value: Real,
    ) -> "Defi":
        """Build a DeFi metric using canonical metadata."""
        metadata = _METRIC_METADATA[metric_type]
        return cls(
            metric_type=metric_type,
            name=metadata["name"],
            unit=metadata["unit"],
            description=metadata["description"],
            date=date,
            value=value,
        )
