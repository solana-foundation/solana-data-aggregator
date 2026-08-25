"""Solscan Pro API data provider."""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional

import requests

from metrics.defi import Defi, DefiMetricType
from metrics.network import Network, NetworkMetricType
from metrics.overview import Overview, OverviewMetricType
from providers.base import BaseProvider


class Solscan(BaseProvider):
    """Fetch network/DeFi metrics from the Solscan Pro API analytics endpoints."""

    METRIC_MAP: Dict[str, Dict[str, Any]] = {
        "overview_tx_count_total": {
            "endpoint": "/analytics/transactions",
            "params": {"filter": "total"},
            "date_field": "block_date",
            "value_field": "value",
        },
        "overview_tx_count_vote": {
            "endpoint": "/analytics/transactions",
            "params": {"filter": "vote"},
            "date_field": "block_date",
            "value_field": "value",
        },
        "overview_non_vote_tx_count_success": {
            "endpoint": "/analytics/transactions",
            "params": {"filter": "nonvote_success"},
            "date_field": "block_date",
            "value_field": "value",
        },
        "overview_non_vote_tx_count_failed": {
            "endpoint": "/analytics/transactions",
            "params": {"filter": "nonvote_fail"},
            "date_field": "block_date",
            "value_field": "value",
        },
        "overview_compute_units": {
            "endpoint": "/analytics/compute-units",
            "date_field": "block_date",
            "value_field": "value",
        },
        "overview_slots": {
            "endpoint": "/analytics/slots",
            "date_field": "block_date",
            "value_field": "value",
        },
        "overview_fees": {
            "endpoint": "/analytics/fees",
            "date_field": "block_date",
            "value_field": "total_fee",
        },
        "network_total_stake": {
            "endpoint": "/analytics/stake",
            "date_field": "block_date",
            "value_field": "total_stake_sol",
        },
        "defi_dex_volume": {
            "endpoint": "/analytics/dex/activity",
            "date_field": "block_date",
            "value_field": "volume_usd",
        },
        "defi_dex_count": {
            "endpoint": "/analytics/dex/activity",
            "date_field": "block_date",
            "value_field": "active_dex_count",
        },
        "defi_dex_transactions": {
            "endpoint": "/analytics/dex/activity",
            "date_field": "block_date",
            "value_field": "trade_count",
        },
        "defi_dex_traders": {
            "endpoint": "/analytics/dex/activity",
            "date_field": "block_date",
            "value_field": "trader_count",
        },
    }

    BASE_URL = "https://public-api.solscan.io"

    def __init__(self, *, api_key: Optional[str] = None) -> None:
        resolved_api_key = api_key or self._resolve_api_key()
        if not resolved_api_key:
            raise ValueError("API key is required")
        super().__init__(
            name="Solscan",
            base_url=os.environ.get("SOLSCAN_API_BASE_URL", self.BASE_URL),
            api_key=resolved_api_key,
        )
        self._session = requests.Session()
        # Cache: (endpoint, sorted params tuple) -> raw response body
        self._cache: Dict[tuple, dict] = {}

    # -- private helpers ----------------------------------------------------

    @staticmethod
    def _resolve_api_key() -> Optional[str]:
        return os.environ.get("SOLSCAN_API_KEY")

    def _get(self, endpoint: str, *, params: Optional[Dict[str, Any]] = None) -> dict:
        """GET an endpoint, caching by (endpoint, params) so metrics that share
        an endpoint and params (e.g. the defi_dex_* metrics) only hit the API once."""
        params = params or {}
        cache_key = (endpoint, tuple(sorted(params.items())))
        if cache_key in self._cache:
            return self._cache[cache_key]

        url = f"{self.base_url}{endpoint}"
        resp = self._session.get(
            url, headers={"token": self.api_key}, params=params, timeout=30
        )
        resp.raise_for_status()
        body = resp.json()
        if not body.get("success", True):
            raise RuntimeError(body.get("error") or f"Solscan API error for {endpoint}")

        self._cache[cache_key] = body
        return body

    @staticmethod
    def _to_iso_date(value: Any) -> str:
        return str(value or "")[:10]

    @staticmethod
    def _to_unix_seconds(date_str: str) -> int:
        parsed = datetime.date.fromisoformat(date_str)
        combined = datetime.datetime.combine(
            parsed, datetime.time.min, tzinfo=datetime.timezone.utc
        )
        return int(combined.timestamp())

    def fetch_rows(
        self, metric: str, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """Return normalized {"date": str, "value": Any} records for the given range (both dates inclusive)."""
        config = self.METRIC_MAP[metric]
        params = dict(config.get("params") or {})
        params["from_time"] = self._to_unix_seconds(start_date)
        params["to_time"] = self._to_unix_seconds(end_date)

        body = self._get(config["endpoint"], params=params)
        series = body.get("data", {}).get("series", [])

        result = []
        for row in series:
            row_date = self._to_iso_date(row.get(config["date_field"]))
            if not row_date or not (start_date <= row_date <= end_date):
                continue
            value = row.get(config["value_field"])
            if value is None:
                continue
            result.append({"date": row_date, "value": float(value)})
        return result

    # -- BaseProvider interface ---------------------------------------------

    def get_metric(
        self, metric: str, date: str, chain: str
    ) -> Overview | Defi | Network | None:
        """Fetch one metric value and return it as a typed metric model."""
        rows = self.fetch_rows(metric, date, date)
        if not rows:
            return None

        value = rows[0]["value"]
        parsed_date = datetime.date.fromisoformat(date)

        overview_metric_map = {
            "overview_tx_count_total": OverviewMetricType.TX_COUNT_TOTAL,
            "overview_tx_count_vote": OverviewMetricType.TX_COUNT_VOTE,
            "overview_non_vote_tx_count_success": OverviewMetricType.TX_COUNT_NON_VOTE_SUCCESS,
            "overview_non_vote_tx_count_failed": OverviewMetricType.TX_COUNT_NON_VOTE_FAILED,
            "overview_compute_units": OverviewMetricType.COMPUTE_UNITS,
            "overview_slots": OverviewMetricType.SLOTS,
            "overview_fees": OverviewMetricType.FEES,
        }
        if metric in overview_metric_map:
            return Overview.from_metric_type(
                metric_type=overview_metric_map[metric],
                date=parsed_date,
                value=value,
            )

        defi_metric_map = {
            "defi_dex_volume": DefiMetricType.DEX_VOLUME,
            "defi_dex_count": DefiMetricType.DEX_COUNT,
            "defi_dex_traders": DefiMetricType.DEX_TRADERS,
            "defi_dex_transactions": DefiMetricType.DEX_TRANSACTIONS,
        }
        if metric in defi_metric_map:
            return Defi.from_metric_type(
                metric_type=defi_metric_map[metric],
                date=parsed_date,
                value=value,
            )

        network_metric_map = {
            "network_total_stake": NetworkMetricType.TOTAL_STAKE,
        }
        if metric in network_metric_map:
            return Network.from_metric_type(
                metric_type=network_metric_map[metric],
                date=parsed_date,
                value=value,
            )

        return None
