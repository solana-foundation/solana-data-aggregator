"""Zerion data provider."""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional

import requests

from metrics.overview import Overview, OverviewMetricType
from providers.base import BaseProvider


class Zerion(BaseProvider):
    """Fetch SOL price (and, soon, ecosystem stablecoin) metrics from the Zerion API."""

    METRIC_MAP: Dict[str, Dict[str, Any]] = {
        "overview_sol_price": {
            "implementation": "solana",
            "price_chart": True,
            "methodology": "Daily SOL price in USD from Zerion's cross-source price feed.",
            "methodology_url": "https://docs.zerion.io/api-reference/fungibles/get-a-chart-for-a-fungible-asset-by-implementation",
        },
        # -- Upcoming: Zerion ecosystem-wide stablecoin metrics ----------------
        # Zerion is releasing ecosystem-wide stablecoin data that maps directly
        # onto the Stablecoin metric category already defined in this repo. To
        # enable when the endpoints ship: add the endpoint config here, add a
        # parsing branch in fetch_rows(), and uncomment the matching entries in
        # get_metric()'s stablecoin_metric_map (plus the Stablecoin imports).
        #
        # "stablecoin_supply":           -> StablecoinMetricType.SUPPLY
        # "stablecoin_transfer_volume":  -> StablecoinMetricType.TRANSFER_VOLUME
        # "stablecoin_active_addresses": -> StablecoinMetricType.ACTIVE_ADDRESSES
    }

    BASE_URL = "https://api.zerion.io/v1"

    def __init__(self, *, api_key: Optional[str] = None) -> None:
        resolved_api_key = api_key or os.environ.get("ZERION_API_KEY") or ""
        super().__init__(
            name="Zerion",
            base_url=self.BASE_URL,
            api_key=resolved_api_key,
        )
        self._session = requests.Session()

    # -- private helpers ----------------------------------------------------

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

    @staticmethod
    def _chart_period(start_date: str) -> str:
        """Pick the smallest day-spaced chart period that still covers start_date.

        Zerion chart periods are fixed windows ending at "now": ``year`` spans
        the last 365 days at 1-day spacing (ideal for a daily series). For older
        backfills we fall back to ``max`` (best-effort; spacing widens beyond a
        year), and downsample to one point per day in fetch_rows().
        """
        days_back = (
            datetime.date.today() - datetime.date.fromisoformat(start_date)
        ).days
        return "year" if days_back < 365 else "max"

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
            period = self._chart_period(start_date)
            raw = self._get(
                f"/fungibles/by-implementation/charts/{period}",
                params={"implementation": config["implementation"], "currency": "usd"},
            )
            points = raw.get("data", {}).get("attributes", {}).get("points", []) or []
            # Charts return finer-than-daily points for some periods; collapse to
            # one value per day (last point of each UTC day wins).
            daily: Dict[str, float] = {}
            for ts, value in points:
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

        # Upcoming stablecoin metrics — enable alongside the METRIC_MAP entries
        # above (and add: from metrics.stablecoin import Stablecoin,
        # StablecoinMetricType):
        #
        # stablecoin_metric_map = {
        #     "stablecoin_supply": StablecoinMetricType.SUPPLY,
        #     "stablecoin_transfer_volume": StablecoinMetricType.TRANSFER_VOLUME,
        #     "stablecoin_active_addresses": StablecoinMetricType.ACTIVE_ADDRESSES,
        # }
        # if metric in stablecoin_metric_map:
        #     return Stablecoin.from_metric_type(
        #         metric_type=stablecoin_metric_map[metric],
        #         date=parsed_date,
        #         value=value,
        #     )

        return None
