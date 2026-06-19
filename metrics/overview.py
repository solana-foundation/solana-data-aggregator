"""Overview metric models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from numbers import Real

from metrics.base import BaseMetric


class OverviewMetricType(str, Enum):
    """Supported overview metric categories."""

    SLOTS = "slots"
    FEE_PAYERS = "fee_payers"
    SOL_PRICE = "sol_price"
    FEES = "fees"
    TX_COUNT_TOTAL = "tx_count_total"
    TX_COUNT_VOTE = "tx_count_vote"
    TX_COUNT_NON_VOTE_SUCCESS = "non_vote_tx_count_success"
    TX_COUNT_NON_VOTE_FAILED = "non_vote_tx_count_failed"
    COMPUTE_UNITS = "compute_units"


_METRIC_METADATA: dict[OverviewMetricType, dict[str, str]] = {
    OverviewMetricType.SLOTS: {
        "name": "Slots",
        "unit": "Count",
        "description": "Number of slots per day on Solana",
    },
    OverviewMetricType.FEE_PAYERS: {
        "name": "Fee Payers",
        "unit": "Count",
        "description": "Number of unique addresses that pay a fee daily on Solana",
    },
    OverviewMetricType.SOL_PRICE: {
        "name": "SOL Price",
        "unit": "USD",
        "description": "Daily average SOL price in USD",
    },
    OverviewMetricType.FEES: {
        "name": "Fees",
        "unit": "SOL",
        "description": "Daily fees (base plus priority) on Solana in SOL",
    },
    OverviewMetricType.TX_COUNT_TOTAL: {
        "name": "Transaction Count (Total)",
        "unit": "Count",
        "description": "Total count of all transactions on Solana per day",
    },
    OverviewMetricType.TX_COUNT_VOTE: {
        "name": "Transaction Count (Vote)",
        "unit": "Count",
        "description": "Count of vote transactions on Solana per day",
    },
    OverviewMetricType.TX_COUNT_NON_VOTE_SUCCESS: {
        "name": "Non Vote Transaction Count (Success)",
        "unit": "Count",
        "description": "Count of successful non-vote transactions on Solana per day",
    },
    OverviewMetricType.TX_COUNT_NON_VOTE_FAILED: {
        "name": "Non Vote Transaction Count (Failed)",
        "unit": "Count",
        "description": "Count of failed non-vote transactions on Solana per day",
    },
    OverviewMetricType.COMPUTE_UNITS: {
        "name": "Compute Units",
        "unit": "Count",
        "description": "Average compute units per block daily on Solana",
    },
}


@dataclass
class Overview(BaseMetric):
    """Concrete metric model for overview datasets."""

    metric_type: OverviewMetricType

    @classmethod
    def from_metric_type(
        cls,
        metric_type: OverviewMetricType,
        date: date,
        value: Real,
    ) -> "Overview":
        """Build an overview metric using canonical metadata."""
        metadata = _METRIC_METADATA[metric_type]
        return cls(
            metric_type=metric_type,
            name=metadata["name"],
            unit=metadata["unit"],
            description=metadata["description"],
            date=date,
            value=value,
        )
