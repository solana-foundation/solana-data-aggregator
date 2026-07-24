"""Birdeye data provider."""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional

import requests

from metrics.defi import Defi, DefiMetricType
from metrics.overview import Overview, OverviewMetricType
from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.base import BaseProvider


class Birdeye(BaseProvider):

    METRIC_MAP: Dict[str, Dict[str, Any]] = {
        "overview_sol_price": {
            "endpoint": "/defi/history_price",
        },
        "stablecoin_supply": {
            "endpoint": "/defi/v3/market-history",
            "metric_field": "stable_coin_market_cap",
        },
        "defi_dex_volume": {
            "endpoint": "/defi/v3/market-history",
            "metric_field": "volume_usd",
        },
        "defi_dex_transactions": {
            "endpoint": "/defi/v3/market-history",
            "metric_field": "trade_count",
        },
    }

    BASE_URL = "https://public-api.birdeye.so"
    SOL_TOKEN_ADDRESS = "So11111111111111111111111111111111111111112"
    ONE_DAY_SECONDS = 24 * 60 * 60

    def __init__(self, *, api_key: Optional[str] = None) -> None:
        resolved_api_key = api_key or os.environ.get("BIRDEYE_API_KEY") or ""
        if not resolved_api_key:
            raise ValueError("API key is required")

        super().__init__(
            name="Birdeye",
            base_url=self.BASE_URL,
            api_key=resolved_api_key,
        )
        self._session = requests.Session()

    # -- private helpers ----------------------------------------------------

    def _get(self, url: str, chain, *, params: Optional[Dict[str, Any]] = None) -> Any:
        headers = {
            "X-API-KEY": self.api_key,
            "x-chain": chain,
            "accept": "application/json",
        }
        resp = self._session.get(url, params=params or {}, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _date_to_timestamp(self, date_str: str) -> int:
        dt = datetime.datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
        return int(dt.timestamp())

    def _timestamp_to_date(self, timestamp: int) -> str:
        return datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc).strftime("%Y-%m-%d")

    # -- BaseProvider interface ---------------------------------------------

    def get_metric(
        self, metric: str, date: str, chain: str
    ) -> Overview | Stablecoin | Defi | None:
        """Fetch one metric for one date and chain from provider API."""
        rows = self.fetch_rows(metric, date, date)
        if not rows:
            return None
        
        value = rows[0]["value"]
        parsed_date = datetime.date.fromisoformat(date)

        overview_metric_map = {
            "overview_sol_price": OverviewMetricType.SOL_PRICE,
        }
        if metric in overview_metric_map:
            return Overview.from_metric_type(
                metric_type=overview_metric_map[metric],
                date=parsed_date,
                value=value,
            )

        stablecoin_metric_map = {
            "stablecoin_supply": StablecoinMetricType.SUPPLY,
        }
        if metric in stablecoin_metric_map:
            return Stablecoin.from_metric_type(
                metric_type=stablecoin_metric_map[metric],
                date=parsed_date,
                value=value,
            )

        defi_metric_map = {
            "defi_dex_volume": DefiMetricType.DEX_VOLUME,
            "defi_dex_transactions": DefiMetricType.DEX_TRANSACTIONS,
        }
        if metric in defi_metric_map:
            return Defi.from_metric_type(
                metric_type=defi_metric_map[metric],
                date=parsed_date,
                value=value,
            )
        
        return None

    def fetch_rows(
        self, metric: str, start_date: str, end_date: str, **kwargs: Any
    ) -> List[Dict[str, Any]]:
        """Return normalized {"date": str, "value": Any} records for the given range (start_date and end_date are both inclusive)."""
        result = []

        config = self.METRIC_MAP.get(metric)
        if config is None:
            available = ", ".join(self.METRIC_MAP)
            raise ValueError(f"Unknown metric '{metric}'. Available: {available}")
        
        endpoint = config["endpoint"]
        start_timestamp = self._date_to_timestamp(start_date)
        end_timestamp = self._date_to_timestamp(end_date)

        match metric:
            case "overview_sol_price":
                response = self._get(
                    f"{self.base_url}{endpoint}",
                    chain="solana",
                    params={
                        "address": self.SOL_TOKEN_ADDRESS,
                        "address_type": "token",
                        "type": "1D",
                        "time_from": start_timestamp,
                        "time_to": end_timestamp
                    },
                )
                data = response.get("data")
                if data is not None:
                    for record in data.get("items", []):
                        timestamp = record.get("unixTime", -1)
                        if timestamp < start_timestamp or timestamp > end_timestamp:
                            continue
                        if "value" in record:
                            result.append(
                                {
                                    "date": self._timestamp_to_date(timestamp),
                                    "value": record["value"],
                                }
                            )

            case "stablecoin_supply" | "defi_dex_volume" | "defi_dex_transactions":
                while start_timestamp <= end_timestamp:
                    count = min(10, (end_timestamp - start_timestamp) // self.ONE_DAY_SECONDS + 1)
                    response = self._get(
                        f"{self.base_url}{endpoint}",
                        chain="solana",
                        params={
                            "type": "1D",
                            "time": start_timestamp,
                            "direction": "forward",
                            "count": count,
                        },
                    )

                    data = response.get("data")
                    metric_field = config["metric_field"]
                    last_timestamp = start_timestamp
                    if data is not None:
                        for record in data.get("items", []):
                            timestamp = record.get("unix_time", -1)
                            if timestamp < start_timestamp or timestamp > end_timestamp:
                                continue
                            if timestamp > last_timestamp:
                                last_timestamp = timestamp
                            
                            if metric_field in record:
                                result.append(
                                    {
                                        "date": self._timestamp_to_date(timestamp),
                                        "value": record[metric_field],
                                    }
                                ) 
                        if not data.get("has_more", False):
                            break
                    
                    start_timestamp = last_timestamp + self.ONE_DAY_SECONDS # Move to the next batch of days
        
        return result