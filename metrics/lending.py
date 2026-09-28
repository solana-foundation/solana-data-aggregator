"""Lending metric models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from numbers import Real

from metrics.base import BaseMetric


class LendingMetricType(str, Enum):
    """Supported lending metric categories."""

    TOTAL_DEPOSITS = "total_deposits"
    UTILIZATION_RATE = "utilization_rate"
    TOTAL_BORROWED = "total_borrowed"
    PROTOCOL_COUNT = "protocol_count"


_METRIC_METADATA: dict[LendingMetricType, dict[str, str]] = {
    LendingMetricType.TOTAL_DEPOSITS: {
        "name": "Lending Total Deposits",
        "unit": "USD",
        "description": "Total USD value supplied to Solana lending protocols",
    },
    LendingMetricType.UTILIZATION_RATE: {
        "name": "Lending Utilization Rate",
        "unit": "Percent",
        "description": "Total borrowed divided by total deposits across Solana lending protocols, as a percentage (0-100)",
    },
    LendingMetricType.TOTAL_BORROWED: {
        "name": "Lending Total Borrowed",
        "unit": "USD",
        "description": "Total USD value borrowed from Solana lending protocols",
    },
    LendingMetricType.PROTOCOL_COUNT: {
        "name": "Lending Protocol Count",
        "unit": "Count",
        "description": "Number of unique lending protocols on Solana",
    },
}


@dataclass
class Lending(BaseMetric):
    """Concrete metric model for lending datasets."""

    metric_type: LendingMetricType

    @classmethod
    def from_metric_type(
        cls,
        metric_type: LendingMetricType,
        date: date,
        value: Real,
    ) -> "Lending":
        """Build a lending metric using canonical metadata."""
        metadata = _METRIC_METADATA[metric_type]
        return cls(
            metric_type=metric_type,
            name=metadata["name"],
            unit=metadata["unit"],
            description=metadata["description"],
            date=date,
            value=value,
        )
