"""Token Terminal data provider."""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional

import requests

from metrics.defi import Defi, DefiMetricType
from metrics.overview import Overview, OverviewMetricType
from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.base import BaseProvider


class TokenTerminal(BaseProvider):
    """Fetch metrics from the Token Terminal v2 API."""

    METRIC_MAP: Dict[str, Dict[str, Any]] = {
        "overview_tx_count_total": {
            "metric_id": "transaction_count",
            "date_field": "timestamp",
            "value_field": "transaction_count",
        },
        "overview_tx_count_vote": {
            "metric_id": "vote_transaction_count",
            "date_field": "timestamp",
            "value_field": "vote_transaction_count",
        },
        "overview_sol_price": {
            "metric_id": "price",
            "date_field": "timestamp",
            "value_field": "price",
        },
        "overview_fee_payers": {
            "metric_id": "active_addresses_daily",
            "date_field": "timestamp",
            "value_field": "active_addresses_daily",
        },
        "stablecoin_supply": {
            # Total stablecoin supply = native issuance + bridged-in supply.
            # Token Terminal exposes these as two separate metric_ids; requesting
            # both in one call and summing them yields the bridged-inclusive total.
            "metric_id": "ecosystem_stablecoin_supply,ecosystem_bridged_stablecoin_supply",
            "date_field": "timestamp",
            "value_field": [
                "ecosystem_stablecoin_supply",
                "ecosystem_bridged_stablecoin_supply",
            ],
            "methodology": (
                "Total stablecoin supply on Solana = native issuance "
                "(ecosystem_stablecoin_supply) + bridged-in supply "
                "(ecosystem_bridged_stablecoin_supply). Circulating supply excludes "
                "issuer treasury and pre-minted, not-yet-issued balances."
            ),
        },
        "defi_dex_volume": {
            "metric_id": "ecosystem_dex_trading_volume",
            "date_field": "timestamp",
            "value_field": "ecosystem_dex_trading_volume",
            "methodology": "DEX trade volume varies by indexed venues, pricing, and filtering methodology.",
        },
    }

    BASE_URL = "https://api.tokenterminal.com/v2"
    PROJECT = "solana"

    def __init__(self, *, api_key: Optional[str] = None) -> None:
        resolved_api_key = api_key or self._resolve_api_key()
        if not resolved_api_key:
            raise ValueError("API key is required")
        super().__init__(
            name="TokenTerminal",
            base_url=self.BASE_URL,
            api_key=resolved_api_key,
        )
        self._session = requests.Session()

    # -- private helpers ----------------------------------------------------

    @staticmethod
    def _resolve_api_key() -> Optional[str]:
        return os.environ.get("TOKEN_TERMINAL_API_KEY")

    def _get(self, endpoint: str, *, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }
        resp = self._session.get(url, headers=headers, params=params or {}, timeout=60)
        resp.raise_for_status()
        return resp.json()

    # -- BaseProvider interface ---------------------------------------------

    @property
    def provider_name(self) -> str:
        return self.name

    def fetch_rows(
        self, metric: str, start_date: str, end_date: str, **kwargs: Any
    ) -> List[Dict[str, Any]]:
        """Return normalized {"date": str, "value": float} records for the given range (both dates inclusive)."""
        config = self.METRIC_MAP[metric]
        # A metric may map to one or more Token Terminal metric_ids. When several
        # are provided (e.g. native + bridged stablecoin supply), their per-day
        # values are summed into a single figure.
        value_fields = config["value_field"]
        if isinstance(value_fields, str):
            value_fields = [value_fields]
        body = self._get(
            f"/projects/{self.PROJECT}/metrics",
            params={
                "metric_ids": config["metric_id"],
                "start": start_date,
                "end": end_date,
                "granularity": "day",
            },
        )
        raw = body if isinstance(body, list) else body.get("data", [])
        result = []
        for row in raw:
            row_date = str(row.get(config["date_field"], ""))[:10]
            if not row_date or not (start_date <= row_date <= end_date):
                continue
            present = [row.get(field) for field in value_fields]
            present = [v for v in present if v is not None]
            if not present:
                continue
            value = sum(float(v) for v in present)
            result.append({"date": row_date, "value": value})
        return result

    def get_metric(
        self, metric: str, date: str, chain: str
    ) -> Stablecoin | Overview | Defi | None:
        """Fetch one metric value and return it as a typed metric model."""
        rows = self.fetch_rows(metric, date, date)
        if not rows:
            return None

        value = rows[0]["value"]
        parsed_date = datetime.date.fromisoformat(date)

        overview_metric_map: Dict[str, OverviewMetricType] = {
            "overview_tx_count_total": OverviewMetricType.TX_COUNT_TOTAL,
            "overview_tx_count_vote": OverviewMetricType.TX_COUNT_VOTE,
            "overview_sol_price": OverviewMetricType.SOL_PRICE,
            "overview_fee_payers": OverviewMetricType.FEE_PAYERS,
        }
        if metric in overview_metric_map:
            return Overview.from_metric_type(
                metric_type=overview_metric_map[metric],
                date=parsed_date,
                value=value,
            )

        defi_metric_map: Dict[str, DefiMetricType] = {
            "defi_dex_volume": DefiMetricType.DEX_VOLUME,
        }
        if metric in defi_metric_map:
            return Defi.from_metric_type(
                metric_type=defi_metric_map[metric],
                date=parsed_date,
                value=value,
            )

        stablecoin_metric_map: Dict[str, StablecoinMetricType] = {
            "stablecoin_supply": StablecoinMetricType.SUPPLY,
        }
        return Stablecoin.from_metric_type(
            metric_type=stablecoin_metric_map[metric],
            date=parsed_date,
            value=value,
        )
