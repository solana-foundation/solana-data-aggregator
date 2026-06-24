"""Zerion data provider."""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional

import requests

from metrics.overview import Overview, OverviewMetricType
from providers.base import BaseProvider


class Zerion(BaseProvider):
    """Fetch metrics from the Zerion API.

    Zerion is a protocol-decoded portfolio and token-data API spanning 36+ chains
    including Solana — portfolio, positions (SPL Token + Token-2022 + native SOL),
    decoded transactions, token data, and PnL.

    Within this repo it currently contributes SOL price to the Overview category;
    ecosystem-wide stablecoin metrics (supply, transfer volume, active addresses)
    follow once those endpoints ship — see the notes in METRIC_MAP and get_metric.
    """

    METRIC_MAP: Dict[str, Dict[str, Any]] = {
        "overview_sol_price": {
            "implementation": "solana",
            "price_chart": True,
            "methodology": "Daily SOL price in USD from Zerion's cross-source price feed; covers the trailing 365 days at daily granularity.",
            "methodology_url": "https://docs.zerion.io/api-reference/fungibles/get-a-chart-for-a-fungible-asset-by-implementation",
        },
        # TODO: add Zerion ecosystem-wide stablecoin metrics (supply,
        # transfer_volume, active_addresses) mapping onto the Stablecoin category
        # once those endpoints ship — see the PR description.
    }

    BASE_URL = "https://api.zerion.io/v1"

    def __init__(self, *, api_key: Optional[str] = None) -> None:
        resolved_api_key = api_key or self._resolve_api_key()
        if not resolved_api_key:
            raise ValueError("API key is required")
        super().__init__(
            name="Zerion",
            base_url=self.BASE_URL,
            api_key=resolved_api_key,
        )
        self._session = requests.Session()

    # -- private helpers ----------------------------------------------------

    @staticmethod
    def _resolve_api_key() -> Optional[str]:
        return os.environ.get("ZERION_API_KEY")

    def _get(self, path: str, *, params: Optional[Dict[str, Any]] = None) -> Any:
        # Zerion uses HTTP Basic auth: the API key as the username with an empty
        # password (Authorization: Basic base64("<api_key>:")).
        resp = self._session.get(
            f"{self.base_url}{path}",
            params=params or {},
            headers={"accept": "application/json"},
            auth=(self.api_key, ""),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _ts_to_date(ts: int) -> str:
        return (
            datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
            .date()
            .isoformat()
        )

    # -- BaseProvider interface ---------------------------------------------

    def fetch_rows(
        self, metric: str, start_date: str, end_date: str, **kwargs: Any
    ) -> List[Dict[str, Any]]:
        """Return normalized {"date": str, "value": float} records for the given range (both dates inclusive)."""
        config = self.METRIC_MAP.get(metric)
        if config is None:
            available = ", ".join(self.METRIC_MAP)
            raise ValueError(f"Unknown metric '{metric}'. Available: {available}")

        if config.get("price_chart"):
            # Zerion fungible charts are fixed windows ending "now". `year` is the
            # trailing 365 days at 1-day spacing — the only period that yields a
            # true daily series. We deliberately do NOT fall back to `max` for
            # older ranges: its spacing widens past daily and would silently
            # return coarse points dressed up as daily values. So history is
            # capped to the trailing 365 days (documented in the methodology);
            # dates older than that are simply not returned rather than faked.
            raw = self._get(
                "/fungibles/by-implementation/charts/year",
                params={"implementation": config["implementation"], "currency": "usd"},
            )
            points = raw.get("data", {}).get("attributes", {}).get("points", []) or []
            # `year` is daily already; dedupe defensively so any duplicate UTC day
            # collapses to its last value.
            daily: Dict[str, float] = {}
            for point in points:
                if not isinstance(point, (list, tuple)) or len(point) < 2:
                    continue
                ts, value = point[0], point[1]
                row_date = self._ts_to_date(int(ts))
                if start_date <= row_date <= end_date:
                    daily[row_date] = float(value)
            return [
                {"date": row_date, "value": daily[row_date]}
                for row_date in sorted(daily)
            ]

        raise ValueError(f"Metric '{metric}' is not yet wired to a live endpoint.")

    def get_metric(self, metric: str, date: str, chain: str) -> Overview | None:
        """Fetch one metric value and return it as a typed metric model."""
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

        # TODO: map upcoming stablecoin metrics to Stablecoin.from_metric_type
        # here when the endpoints ship (see METRIC_MAP and the PR description).

        # Defensive: fetch_rows() already validates the metric is in METRIC_MAP,
        # so reaching here means a known metric has no typed-model mapping yet.
        raise ValueError(f"Metric '{metric}' has no typed-model mapping in get_metric.")
