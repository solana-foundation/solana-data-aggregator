"""Stablecoin metric models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from numbers import Real

from metrics.base import BaseMetric


class StablecoinMetricType(str, Enum):
    """Supported stablecoin metric categories."""

    SUPPLY = "supply"
    TRANSFER_VOLUME = "transfer_volume"
    TRANSFER_COUNT = "transfer_count"
    ACTIVE_ADDRESSES = "active_addresses"
    COUNT = "count"


_METRIC_METADATA: dict[StablecoinMetricType, dict[str, str]] = {
    StablecoinMetricType.SUPPLY: {
        "name": "Supply",
        "unit": "USD",
        "description": "Total circulating supply of stablecoins on Solana, denominated in USD",
    },
    StablecoinMetricType.TRANSFER_VOLUME: {
        "name": "Transfer Volume",
        "unit": "USD",
        "description": "Total transfer volume of stablecoins on Solana, denominated in USD",
    },
    StablecoinMetricType.TRANSFER_COUNT: {
        "name": "Transfer Count",
        "unit": "Count",
        "description": "Total number of stablecoin transfer transactions on Solana",
    },
    StablecoinMetricType.ACTIVE_ADDRESSES: {
        "name": "Active Addresses",
        "unit": "Count",
        "description": "Number of unique addresses interacting with stablecoins on Solana",
    },
    StablecoinMetricType.COUNT: {
        "name": "Stablecoin Count",
        "unit": "Count",
        "description": "Number of distinct USD-pegged stablecoins supported on Solana",
    },
}


@dataclass
class Stablecoin(BaseMetric):
    """Concrete metric model for stablecoin datasets."""

    metric_type: StablecoinMetricType

    @classmethod
    def from_metric_type(
        cls,
        metric_type: StablecoinMetricType,
        date: date,
        value: Real,
    ) -> "Stablecoin":
        """Build a stablecoin metric using canonical metadata."""
        metadata = _METRIC_METADATA[metric_type]
        return cls(
            metric_type=metric_type,
            name=metadata["name"],
            unit=metadata["unit"],
            description=metadata["description"],
            date=date,
            value=value,
        )
