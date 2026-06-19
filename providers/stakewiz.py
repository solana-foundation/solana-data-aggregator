"""Stakewiz data provider."""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

import requests

from metrics.network import Network, NetworkMetricType
from providers.base import BaseProvider


class Stakewiz(BaseProvider):
    """Fetch network metrics from the Stakewiz public API.

    Endpoints
    ---------
    - Validators: /validators  (current snapshot, aggregated for stake/count/ASN share)

    No API key required.
    """

    METRIC_MAP: Dict[str, Dict[str, Any]] = {
        "network_total_stake": {
            "endpoint": "/validators",
            "validators_aggregate": "sum_stake",
        },
        "network_validator_count": {
            "endpoint": "/validators",
            "validators_aggregate": "count",
        },
        "network_top_3_asn_share": {
            "endpoint": "/validators",
            "validators_aggregate": "top_3_asn_share",
        },
    }

    _NETWORK_METRIC_TYPE_MAP: Dict[str, NetworkMetricType] = {
        "network_total_stake": NetworkMetricType.TOTAL_STAKE,
        "network_validator_count": NetworkMetricType.VALIDATOR_COUNT,
        "network_top_3_asn_share": NetworkMetricType.TOP_3_ASN_SHARE,
    }

    BASE_URL = "https://api.stakewiz.com"

    def __init__(self) -> None:
        super().__init__(
            name="Stakewiz",
            base_url=self.BASE_URL,
            api_key="",
        )
        self._session = requests.Session()

    # -- private helpers ----------------------------------------------------

    def _get(self, endpoint: str, *, params: Optional[Dict[str, Any]] = None) -> Any:
        resp = self._session.get(
            f"{self.base_url}{endpoint}", params=params or {}, timeout=30
        )
        resp.raise_for_status()
        return resp.json()

    # -- BaseProvider interface ---------------------------------------------

    def fetch_rows(
        self, metric: str, start_date: str, end_date: str, **kwargs: Any
    ) -> List[Dict[str, Any]]:
        """Return normalized {"date": str, "value": float} records for the given range (both dates inclusive).

        Note: /validators is a current snapshot — returns one row for today's date.
        """
        config = self.METRIC_MAP.get(metric)
        if config is None:
            available = ", ".join(self.METRIC_MAP)
            raise ValueError(f"Unknown metric '{metric}'. Available: {available}")

        today = datetime.date.today().isoformat()
        if not (start_date <= today <= end_date):
            return []

        validators = self._get(config["endpoint"])
        current_epoch = max((v.get("epoch") for v in validators), default=None)
        active = [
            v
            for v in validators
            if not v.get("delinquent", True) and v.get("epoch") == current_epoch
        ]
        agg = config["validators_aggregate"]

        if agg == "sum_stake":
            # activated_stake is already in SOL
            value = sum(v.get("activated_stake", 0) for v in active)
        elif agg == "count":
            value = float(len(active))
        else:  # top_3_asn_share
            asn_stake: Dict[Any, float] = {}
            for v in active:
                asn = v.get("asn")
                if asn:
                    asn_stake[asn] = asn_stake.get(asn, 0) + v.get("activated_stake", 0)
            sorted_stakes = sorted(asn_stake.values(), reverse=True)
            total = sum(sorted_stakes)
            top_3 = sum(sorted_stakes[:3])
            value = (top_3 / total * 100) if total else 0.0

        return [{"date": today, "value": float(value)}]

    def get_metric(self, metric: str, date: str, chain: str) -> Network | None:
        """Fetch one metric value and return it as a typed Network metric model."""
        rows = self.fetch_rows(metric, date, date)
        if not rows:
            return None

        metric_type = self._NETWORK_METRIC_TYPE_MAP.get(metric)
        if metric_type is None:
            return None

        return Network.from_metric_type(
            metric_type=metric_type,
            date=datetime.date.fromisoformat(date),
            value=rows[0]["value"],
        )
