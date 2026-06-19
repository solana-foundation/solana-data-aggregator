"""Validators.app data provider."""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional

import requests

from metrics.network import Network, NetworkMetricType
from providers.base import BaseProvider


class ValidatorsApp(BaseProvider):
    """Fetch network metrics from the Validators.app API.

    Endpoints
    ---------
    - SOL Price:   /api/v1/sol-prices.json         (~30 days of daily prices)
    - Validators:  /api/v1/validators/mainnet.json  (current snapshot, aggregated for stake/count/ASN share)
    """

    METRIC_MAP: Dict[str, Dict[str, Any]] = {
        "network_sol_price": {
            "endpoint": "/sol-prices.json",
        },
        "network_total_stake": {
            "endpoint": "/validators/mainnet.json",
            "validators_aggregate": "sum_stake",
        },
        "network_validator_count": {
            "endpoint": "/validators/mainnet.json",
            "validators_aggregate": "count",
        },
        "network_top_3_asn_share": {
            "endpoint": "/validators/mainnet.json",
            "validators_aggregate": "top_3_asn_share",
        },
    }

    _NETWORK_METRIC_TYPE_MAP: Dict[str, NetworkMetricType] = {
        "network_sol_price": NetworkMetricType.SOL_PRICE,
        "network_total_stake": NetworkMetricType.TOTAL_STAKE,
        "network_validator_count": NetworkMetricType.VALIDATOR_COUNT,
        "network_top_3_asn_share": NetworkMetricType.TOP_3_ASN_SHARE,
    }

    BASE_URL = "https://www.validators.app/api/v1"

    def __init__(self, *, api_token: Optional[str] = None) -> None:
        resolved_token = api_token or os.environ.get("VALIDATORS_APP_API_TOKEN") or ""
        super().__init__(
            name="ValidatorsApp",
            base_url=self.BASE_URL,
            api_key=resolved_token,
        )
        self._session = requests.Session()
        self._session.headers.update({"Token": self.api_key})

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

        Note: all endpoints return current snapshots — one row for today's date.
        """
        config = self.METRIC_MAP.get(metric)
        if config is None:
            available = ", ".join(self.METRIC_MAP)
            raise ValueError(f"Unknown metric '{metric}'. Available: {available}")

        today = datetime.date.today().isoformat()

        if metric == "network_sol_price":
            raw = self._get(config["endpoint"])
            result = []
            for entry in raw:
                row_date = (
                    entry.get("datetime_from_exchange") or entry.get("created_at", "")
                )[:10]
                price = entry.get("average_price")
                if (
                    row_date
                    and price is not None
                    and start_date <= row_date <= end_date
                ):
                    result.append({"date": row_date, "value": float(price)})
            return result

        if not (start_date <= today <= end_date):
            return []

        if config.get("validators_aggregate"):
            validators = self._get(config["endpoint"])
            active = [
                v
                for v in validators
                if v.get("is_active") and not v.get("delinquent", False)
            ]
            agg = config["validators_aggregate"]
            if agg == "sum_stake":
                value = sum(v.get("active_stake", 0) for v in active) / 1e9
            elif agg == "count":
                value = float(len(active))
            else:  # top_3_asn_share
                asn_stake: Dict[Any, int] = {}
                for v in active:
                    asn = v.get("autonomous_system_number")
                    if asn:
                        asn_stake[asn] = asn_stake.get(asn, 0) + v.get(
                            "active_stake", 0
                        )
                sorted_stakes = sorted(asn_stake.values(), reverse=True)
                total = sum(sorted_stakes)
                top_3 = sum(sorted_stakes[:3])
                value = (top_3 / total * 100) if total else 0.0
            return [{"date": today, "value": value}]

        # Snapshot-based cluster stats
        raw = self._get(config["endpoint"])
        value = raw.get(config["field"])
        if value is None:
            return []
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
