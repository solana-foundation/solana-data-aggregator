"""BAMservatory data provider."""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from metrics.network import Network, NetworkMetricType
from providers.base import BaseProvider


class Bamservatory(BaseProvider):
    """Fetch BAM stake share from BAMservatory's published metrics.

    BAMservatory is an independent, open-source observatory of Jito's Block
    Assembly Marketplace (BAM). It records BAM's public API every minute,
    archives every capture, and publishes one median per completed UTC day.

    Endpoints
    ---------
    - /metrics.json  (the ``daily`` array: one row per completed UTC day)

    One request covers any date range. History begins 2026-06-20, and the day
    in progress is never published, so dates outside that span return no rows.

    The session retries idempotent GETs with capped exponential backoff + jitter
    on 408/429/5xx, since the endpoint is a static file behind a CDN.

    No API key required.
    """

    METRIC_MAP: Dict[str, Dict[str, Any]] = {
        "network_bam_stake_share": {
            "endpoint": "/metrics.json",
            "daily_field": "bamStakePct",
            "methodology": (
                "Daily median of BAM's published share of total Solana stake "
                "(bam_stake_percentage from the BAM /bam_stake endpoint), "
                "recorded every minute. Captures that are partial or internally "
                "inconsistent API responses are excluded before the median is "
                "taken, and only completed UTC days are published."
            ),
            "methodology_url": "https://github.com/RYthaGOD/bamservatory/blob/main/SCHEMA.md#daily",
        },
    }

    _NETWORK_METRIC_TYPE_MAP: Dict[str, NetworkMetricType] = {
        "network_bam_stake_share": NetworkMetricType.BAM_STAKE_SHARE,
    }

    BASE_URL = "https://rythagod.github.io/bamservatory"

    def __init__(self) -> None:
        super().__init__(
            name="BAMservatory",
            base_url=self.BASE_URL,
            api_key="",
        )
        self._session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            backoff_jitter=0.5,
            status_forcelist=(408, 429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        self._session.mount("https://", HTTPAdapter(max_retries=retry))

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
        """Return normalized {"date": str, "value": float} records for the given range (both dates inclusive)."""
        config = self.METRIC_MAP.get(metric)
        if config is None:
            available = ", ".join(self.METRIC_MAP)
            raise ValueError(f"Unknown metric '{metric}'. Available: {available}")

        payload = self._get(config["endpoint"])
        daily = payload.get("daily") if isinstance(payload, dict) else None
        if not isinstance(daily, list):
            raise ValueError("BAMservatory response has no 'daily' series")

        field = config["daily_field"]
        rows: List[Dict[str, Any]] = []
        for row in daily:
            day = row.get("date") if isinstance(row, dict) else None
            value = row.get(field) if isinstance(row, dict) else None
            if (
                not isinstance(day, str)
                or isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0 <= value <= 100
            ):
                raise ValueError(f"Malformed BAMservatory daily row: {row!r}")
            if start_date <= day <= end_date:
                rows.append({"date": day, "value": float(value)})

        return sorted(rows, key=lambda r: r["date"])

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
