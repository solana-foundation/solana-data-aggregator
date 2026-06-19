"""Artemis data provider."""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional

import requests

from metrics.defi import Defi, DefiMetricType
from metrics.overview import Overview, OverviewMetricType
from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.base import BaseProvider

# ---------------------------------------------------------------------------
# Artemis
# ---------------------------------------------------------------------------


class Artemis(BaseProvider):
    """Fetch stablecoin metrics from the Artemis XYZ API."""

    METRIC_MAP: Dict[str, str] = {
        "stablecoin_supply": "STABLECOIN_SUPPLY",
        "stablecoin_transfer_volume": "STABLECOIN_TRANSFER_VOLUME",
        "stablecoin_transfer_count": "STABLECOIN_DAILY_TXNS",
        "stablecoin_active_addresses": "STABLECOIN_DAU",
        "overview_fee_payers": "DAU",
        "overview_sol_price": "PRICE",
        "overview_fees": "FEES_NATIVE",
        "defi_dex_volume": "CHAIN_SPOT_VOLUME",
    }
    BASE_URL = "https://data-svc.artemisxyz.com"

    def __init__(self, *, api_key: Optional[str] = None) -> None:
        resolved_api_key = api_key or self._resolve_api_key()
        if not resolved_api_key:
            raise ValueError("API key is required")
        super().__init__(
            name="Artemis",
            base_url=self.BASE_URL,
            api_key=resolved_api_key,
        )
        self._session = requests.Session()

    # -- private helpers ----------------------------------------------------

    @staticmethod
    def _resolve_api_key() -> Optional[str]:
        """Try env-var, then Databricks secrets."""
        key = os.environ.get("ARTEMIS_API_KEY")
        if key:
            return key

    def _get(self, endpoint: str, *, params: Optional[Dict[str, Any]] = None) -> dict:
        """Perform an authenticated GET against the Artemis timeseries API."""
        url = f"{self.base_url}/data/api/{endpoint}"
        params = dict(params or {})
        params["APIKey"] = self.api_key
        params.setdefault("granularity", "DAY")
        resp = self._session.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    def fetch_rows(
        self, metric: str, start_date: str, end_date: str, chain: str = "solana"
    ) -> List[Dict[str, Any]]:
        """Return normalized {"date": str, "value": Any} records for the given range (both dates inclusive)."""
        endpoint = self.METRIC_MAP[metric]
        body = self._get(
            endpoint,
            params={"symbols": chain, "startDate": start_date, "endDate": end_date},
        )
        entries = (
            body.get("data", {}).get("symbols", {}).get(chain, {}).get(endpoint, [])
        )
        result = []
        for entry in entries:
            row_date = str(entry.get("date", ""))[:10]
            if not row_date:
                continue
            value = entry.get("val")
            if value is None:
                continue
            result.append({"date": row_date, "value": float(value)})
        return result

    # -- BaseProvider interface ---------------------------------------------

    @property
    def provider_name(self) -> str:
        return self.name

    def get_metric(
        self, metric: str, date: str, chain: str
    ) -> Stablecoin | Overview | Defi | None:
        """Fetch one metric value and return it as a typed metric model."""
        rows = self.fetch_rows(metric, date, date, chain)
        if not rows:
            return None

        value = rows[0]["value"]
        parsed_date = datetime.date.fromisoformat(date)

        overview_metric_map = {
            "overview_fee_payers": OverviewMetricType.FEE_PAYERS,
            "overview_sol_price": OverviewMetricType.SOL_PRICE,
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
        }
        if metric in defi_metric_map:
            return Defi.from_metric_type(
                metric_type=defi_metric_map[metric],
                date=parsed_date,
                value=value,
            )

        stablecoin_metric_map = {
            "stablecoin_supply": StablecoinMetricType.SUPPLY,
            "stablecoin_transfer_volume": StablecoinMetricType.TRANSFER_VOLUME,
            "stablecoin_transfer_count": StablecoinMetricType.TRANSFER_COUNT,
            "stablecoin_active_addresses": StablecoinMetricType.ACTIVE_ADDRESSES,
        }
        return Stablecoin.from_metric_type(
            metric_type=stablecoin_metric_map[metric],
            date=parsed_date,
            value=value,
        )
