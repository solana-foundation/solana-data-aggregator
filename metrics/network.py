"""Network metric models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from numbers import Real

from metrics.base import BaseMetric


class NetworkMetricType(str, Enum):
    """Supported network metric categories."""

    TOTAL_STAKE = "total_stake"
    SOL_PRICE = "sol_price"
    VALIDATOR_COUNT = "validator_count"
    TOP_3_ASN_SHARE = "top_3_asn_share"
    AVG_TPS = "avg_tps"
    BAM_STAKE_SHARE = "bam_stake_share"


_METRIC_METADATA: dict[NetworkMetricType, dict[str, str]] = {
    NetworkMetricType.TOTAL_STAKE: {
        "name": "Total Stake",
        "unit": "SOL",
        "description": "Total staked SOL across all validators on Solana daily",
    },
    NetworkMetricType.SOL_PRICE: {
        "name": "SOL Price (Network)",
        "unit": "USD",
        "description": "Daily average SOL price in USD",
    },
    NetworkMetricType.VALIDATOR_COUNT: {
        "name": "Validator Count",
        "unit": "Count",
        "description": "Number of active validators on Solana daily",
    },
    NetworkMetricType.TOP_3_ASN_SHARE: {
        "name": "Top 3 ASN Share",
        "unit": "Percent",
        "description": "Percentage of stake concentrated in the top 3 ASNs on Solana daily",
    },
    NetworkMetricType.AVG_TPS: {
        "name": "Average TPS",
        "unit": "TPS",
        "description": "Daily average transactions per second on Solana (non-vote transactions, successful and failed, / 86,400)",
    },
    NetworkMetricType.BAM_STAKE_SHARE: {
        "name": "BAM Stake Share",
        "unit": "Percent",
        "description": "Percentage of total Solana stake held by validators connected to Jito's Block Assembly Marketplace (BAM) daily",
    },
}


@dataclass
class Network(BaseMetric):
    """Concrete metric model for network datasets."""

    metric_type: NetworkMetricType

    @classmethod
    def from_metric_type(
        cls,
        metric_type: NetworkMetricType,
        date: date,
        value: Real,
    ) -> "Network":
        """Build a network metric using canonical metadata."""
        metadata = _METRIC_METADATA[metric_type]
        return cls(
            metric_type=metric_type,
            name=metadata["name"],
            unit=metadata["unit"],
            description=metadata["description"],
            date=date,
            value=value,
        )
