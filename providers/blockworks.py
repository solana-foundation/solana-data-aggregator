"""Blockworks Data API provider."""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional

import requests

from metrics.defi import Defi, DefiMetricType
from metrics.overview import Overview, OverviewMetricType
from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.base import BaseProvider

SOLANA_NETWORK_ID = "b204e48e-9812-43e6-a00b-5fcfd40e04a2"
SOL_ASSET_ID = "b3d5d66c-26a2-404c-9325-91dc714a722b"


class Blockworks(BaseProvider):
    """Fetch Solana metrics from the Blockworks Data API timeseries endpoints."""

    METRIC_MAP: Dict[str, Dict[str, Any]] = {
        "stablecoin_total_supply": {
            "model": "blockchains",
            "series": SOLANA_NETWORK_ID,
            "field": "stablecoin-outstanding-supply-usd",
        },
        "stablecoin_transfer_volume": {
            "model": "blockchains",
            "series": SOLANA_NETWORK_ID,
            "field": "stablecoin-transfer-volume-usd",
        },
        "stablecoin_transfer_count": {
            "model": "blockchains",
            "series": SOLANA_NETWORK_ID,
            "field": "stablecoin-transfer-count",
        },
        "stablecoin_active_addresses": {
            "model": "blockchains",
            "series": SOLANA_NETWORK_ID,
            "field": "stablecoin-active-addresses",
            "methodology": "Number of unique addresses that sent a stablecoin transfer.",
        },
        "overview_fee_payers": {
            "model": "blockchains",
            "series": SOLANA_NETWORK_ID,
            "field": "active-addresses",
        },
        "overview_sol_price": {
            "model": "asset-price",
            "series": SOL_ASSET_ID,
            "field": "close",
        },
        "overview_app_revenue": {
            "model": "blockchains",
            "series": SOLANA_NETWORK_ID,
            "field": "app-revenue-usd",
        },
        "overview_non_vote_tx_count_success": {
            "model": "blockchains",
            "series": SOLANA_NETWORK_ID,
            "field": "successful-transactions",
        },
        "overview_non_vote_tx_count_failed": {
            "model": "blockchains",
            "series": SOLANA_NETWORK_ID,
            "field": "unsuccessful-transactions",
        },
        "defi_dex_volume": {
            "model": "blockchains",
            "series": SOLANA_NETWORK_ID,
            "field": "dex-volume-usd",
        },
    }

    BASE_URL = "https://api.blockworks.com"
    GRANULARITY = "1d"

    def __init__(self, *, api_key: Optional[str] = None) -> None:
        resolved_api_key = api_key or self._resolve_api_key()
        if not resolved_api_key:
            raise ValueError("API key is required")
        super().__init__(
            name="Blockworks",
            base_url=self.BASE_URL,
            api_key=resolved_api_key,
        )
        self._session = requests.Session()

    # -- private helpers ----------------------------------------------------

    @staticmethod
    def _resolve_api_key() -> Optional[str]:
        return os.environ.get("BLOCKWORKS_API_KEY")

    def _get(self, endpoint: str, *, params: Optional[Dict[str, Any]] = None) -> dict:
        url = f"{self.base_url}{endpoint}"
        resp = self._session.get(
            url, headers={"X-Blockworks-API-Key": self.api_key}, params=params or {}
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("error"):
            raise RuntimeError(f"Blockworks API error: {body['error']}")
        return body["data"]

    def fetch_rows(
        self, metric: str, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """Return normalized {"date": str, "value": Any} records for the given range (both dates inclusive)."""
        config = self.METRIC_MAP[metric]
        # The Data API's `end` is exclusive; our end_date is inclusive.
        end_exclusive = datetime.date.fromisoformat(end_date) + datetime.timedelta(
            days=1
        )
        data = self._get(
            f"/query/timeseries/{config['model']}/{self.GRANULARITY}/{config['series']}",
            params={
                "start": start_date,
                "end": end_exclusive.isoformat(),
                "selections": config["field"],
            },
        )

        # Each point is [unix_ts, value, ...] in point_schema order.
        fields = [col["field"] for col in data["point_schema"]]
        value_idx = fields.index(config["field"])
        result = []
        for point in data.get("points", []):
            value = point[value_idx]
            if value is None:
                continue
            row_date = datetime.datetime.fromtimestamp(
                point[0], datetime.timezone.utc
            ).date()
            result.append({"date": row_date.isoformat(), "value": float(value)})
        return result

    # -- BaseProvider interface ---------------------------------------------

    def get_metric(
        self, metric: str, date: str, chain: str
    ) -> Stablecoin | Overview | Defi | None:
        """Fetch one metric value and return it as a typed metric model."""
        rows = self.fetch_rows(metric, date, date)
        if not rows:
            return None

        value = rows[0]["value"]
        parsed_date = datetime.date.fromisoformat(date)

        overview_metric_map = {
            "overview_fee_payers": OverviewMetricType.FEE_PAYERS,
            "overview_sol_price": OverviewMetricType.SOL_PRICE,
            "overview_app_revenue": OverviewMetricType.APP_REVENUE,
            "overview_non_vote_tx_count_success": OverviewMetricType.TX_COUNT_NON_VOTE_SUCCESS,
            "overview_non_vote_tx_count_failed": OverviewMetricType.TX_COUNT_NON_VOTE_FAILED,
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
            "stablecoin_total_supply": StablecoinMetricType.TOTAL_SUPPLY,
            "stablecoin_transfer_volume": StablecoinMetricType.TRANSFER_VOLUME,
            "stablecoin_transfer_count": StablecoinMetricType.TRANSFER_COUNT,
            "stablecoin_active_addresses": StablecoinMetricType.ACTIVE_ADDRESSES,
        }
        return Stablecoin.from_metric_type(
            metric_type=stablecoin_metric_map[metric],
            date=parsed_date,
            value=value,
        )
