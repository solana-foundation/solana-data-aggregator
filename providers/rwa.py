"""RWA data provider."""

from __future__ import annotations

import datetime
import json
import os
from typing import Any, Dict, List, Optional

import requests

from metrics.defi import Defi
from metrics.overview import Overview
from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.base import BaseProvider


class Rwa(BaseProvider):
    """Fetch metrics from the RWA data provider."""

    METRIC_MAP: Dict[str, Dict[str, Any]] = {
        "stablecoin_supply": {
            "query": {
                "filter": {
                    "operator": "and",
                    "filters": [
                        {
                            "operator": "equals",
                            "field": "network_name",
                            "value": "Solana",
                        },
                        {
                            "operator": "equals",
                            "field": "asset_class_name",
                            "value": "Stablecoins",
                        },
                        {
                            "operator": "equals",
                            "field": "measure_slug",
                            "value": "circulating_market_value_dollar",
                        },
                    ],
                },
                "aggregate": {
                    "groupBy": "network",
                    "aggregateFunction": "sum",
                    "interval": "day",
                    "mode": "stock",
                },
            },
        },
        "stablecoin_transfer_volume": {
            "query": {
                "filter": {
                    "operator": "and",
                    "filters": [
                        {
                            "operator": "equals",
                            "field": "network_name",
                            "value": "Solana",
                        },
                        {
                            "operator": "equals",
                            "field": "asset_class_name",
                            "value": "Stablecoins",
                        },
                        {
                            "operator": "equals",
                            "field": "measure_slug",
                            "value": "daily_transfer_volume_dollar",
                        },
                    ],
                },
                "aggregate": {
                    "groupBy": "network",
                    "aggregateFunction": "sum",
                    "interval": "day",
                    "mode": "stock",
                },
            },
        },
        "stablecoin_transfer_count": {
            "query": {
                "filter": {
                    "operator": "and",
                    "filters": [
                        {
                            "operator": "equals",
                            "field": "network_name",
                            "value": "Solana",
                        },
                        {
                            "operator": "equals",
                            "field": "asset_class_name",
                            "value": "Stablecoins",
                        },
                        {
                            "operator": "equals",
                            "field": "measure_slug",
                            "value": "number_of_daily_transactions_count",
                        },
                    ],
                },
                "aggregate": {
                    "groupBy": "network",
                    "aggregateFunction": "sum",
                    "interval": "day",
                    "mode": "stock",
                },
            },
        },
        "stablecoin_active_addresses": {
            "query": {
                "filter": {
                    "operator": "and",
                    "filters": [
                        {
                            "operator": "equals",
                            "field": "network_name",
                            "value": "Solana",
                        },
                        {
                            "operator": "equals",
                            "field": "asset_class_name",
                            "value": "Stablecoins",
                        },
                        {
                            "operator": "equals",
                            "field": "measure_slug",
                            "value": "daily_active_addresses_count",
                        },
                    ],
                },
                "aggregate": {
                    "groupBy": "network",
                    "aggregateFunction": "sum",
                    "interval": "day",
                    "mode": "stock",
                },
            },
        },
    }

    BASE_URL = "https://api.rwa.xyz/v4"

    def __init__(self, *, api_key: Optional[str] = None) -> None:
        resolved_api_key = api_key or self._resolve_api_key()
        if not resolved_api_key:
            raise ValueError("API key is required")
        super().__init__(
            name="Rwa",
            base_url=self.BASE_URL,
            api_key=resolved_api_key,
        )
        self._session = requests.Session()

    @property
    def headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    # -- private helpers ----------------------------------------------------

    @staticmethod
    def _resolve_api_key() -> Optional[str]:
        return os.environ.get("RWA_API_KEY")

    def _fetch_timeseries(
        self, query: Dict[str, Any], start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """Fetch timeseries points and return normalized {"date": str, "value": float} records."""
        date_filters = [
            {"operator": "onOrAfter", "field": "date", "value": start_date},
            {"operator": "onOrBefore", "field": "date", "value": end_date},
        ]
        existing_filter = query.get("filter")
        if existing_filter:
            merged_filter = {
                "operator": "and",
                "filters": [existing_filter] + date_filters,
            }
        else:
            merged_filter = {"operator": "and", "filters": date_filters}
        query_with_dates = {**query, "filter": merged_filter}

        url = f"{self.base_url}/tokens/aggregates/timeseries"
        resp = self._session.get(
            url,
            headers=self.headers,
            params={"query": json.dumps(query_with_dates)},
            timeout=60,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return []
        rows = []
        for date_str, value in results[0].get("points", []):
            row_date = str(date_str)[:10]
            if value is not None:
                rows.append({"date": row_date, "value": float(value)})
        return rows

    # -- BaseProvider interface ---------------------------------------------

    @property
    def provider_name(self) -> str:
        return self.name

    def fetch_rows(
        self, metric: str, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """Return normalized {"date": str, "value": Any} records for the given range (both dates inclusive)."""
        config = self.METRIC_MAP[metric]
        return self._fetch_timeseries(config["query"], start_date, end_date)

    def get_metric(
        self, metric: str, date: str, chain: str
    ) -> Stablecoin | Overview | Defi | None:
        """Fetch one metric value and return it as a typed metric model."""
        rows = self.fetch_rows(metric, date, date)
        if not rows:
            return None

        value = rows[0]["value"]
        parsed_date = datetime.date.fromisoformat(date)

        stablecoin_metric_map = {
            "stablecoin_supply": StablecoinMetricType.SUPPLY,
            "stablecoin_transfer_volume": StablecoinMetricType.TRANSFER_VOLUME,
            "stablecoin_transfer_count": StablecoinMetricType.TRANSFER_COUNT,
            "stablecoin_active_addresses": StablecoinMetricType.ACTIVE_ADDRESSES,
        }
        if metric in stablecoin_metric_map:
            return Stablecoin.from_metric_type(
                metric_type=stablecoin_metric_map[metric],
                date=parsed_date,
                value=value,
            )

        return None
