"""Top Ledger data provider."""

from __future__ import annotations

import datetime
import os
import time
from typing import Any, Dict, List, Optional

import requests

from metrics.overview import Overview, OverviewMetricType
from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.base import BaseProvider


class TopLedger(BaseProvider):
    """Fetch Solana metrics from the Top Ledger Redash API (analytics.topledger.xyz).

    Authentication
    --------------
    Uses a single user-level API key (TOPLEDGER_API_KEY) passed as the
    ``api_key`` query parameter on every request — no per-query keys needed.

    Query execution flow (Redash async pattern)
    -------------------------------------------
    1. POST /api/queries/{id}/results with ``parameters`` body.
    2. If Redash returns a cached ``query_result`` immediately, use it.
    3. Otherwise poll GET /api/jobs/{job_id} until status == 3 (success).
    4. Fetch rows from GET /api/query_results/{query_result_id} if not
       already embedded in the job response.

    Caching
    -------
    Multiple metrics share query 15088. Raw rows are cached in-process
    by (query_id, start_date, end_date) so the query runs at most once
    per date range regardless of how many metrics are requested.
    """

    BASE_URL = "https://analytics.topledger.xyz/tl"

    # All six overview metrics come from a single parameterised Redash query.
    # The query returns one row per block_date with all columns present.
    METRIC_MAP: Dict[str, Dict[str, Any]] = {
        "overview_tx_count_total": {
            "query_id": 15088,
            "date_field": "block_date",
            "value_field": "transactions",
            "methodology": (
                "Total daily transaction count on Solana, deduplicated per "
                "block slot to avoid double-counting re-processed slots."
            ),
            "methodology_url": "https://analytics.topledger.xyz/tl/queries/15088",
        },
        "overview_tx_count_vote": {
            "query_id": 15088,
            "date_field": "block_date",
            "value_field": "vote_transactions",
            "methodology": (
                "Daily vote transaction count on Solana, deduplicated per block slot."
            ),
            "methodology_url": "https://analytics.topledger.xyz/tl/queries/15088",
        },
        "overview_non_vote_tx_count_success": {
            "query_id": 15088,
            "date_field": "block_date",
            "value_field": "successful_non_vote_transactions",
            "methodology": (
                "Daily count of successful non-vote transactions on Solana."
            ),
            "methodology_url": "https://analytics.topledger.xyz/tl/queries/15088",
        },
        "overview_non_vote_tx_count_failed": {
            "query_id": 15088,
            "date_field": "block_date",
            "value_field": "failed_non_vote_transactions",
            "methodology": ("Daily count of failed non-vote transactions on Solana."),
            "methodology_url": "https://analytics.topledger.xyz/tl/queries/15088",
        },
        "overview_fees": {
            "query_id": 15088,
            "date_field": "block_date",
            "value_field": "txns_fees",
            "methodology": (
                "Daily transaction fees on Solana in SOL "
                "(base fees + priority fees), summed across all slots."
            ),
            "methodology_url": "https://analytics.topledger.xyz/tl/queries/15088",
        },
        "overview_slots": {
            "query_id": 15088,
            "date_field": "block_date",
            "value_field": "slots",
            "methodology": "Number of confirmed block slots per day on Solana.",
            "methodology_url": "https://analytics.topledger.xyz/tl/queries/15088",
        },
        "overview_sol_price": {
            "query_id": 15089,
            "date_field": "block_date",
            "value_field": "sol_price_usd",
            "methodology": (
                "Daily average SOL price in USD, computed as the mean of "
                "1-minute OHLC prices for the wrapped SOL mint "
                "(So11111111111111111111111111111111111111112)."
            ),
            "methodology_url": "https://analytics.topledger.xyz/tl/queries/15089",
        },
        "stablecoin_supply": {
            "query_id": 15090,
            "date_field": "block_date",
            "value_field": "marketcap",
            "methodology": (
                "Total circulating supply of stablecoins on Solana in USD, "
                "computed as token supply multiplied by the daily average price "
                "for each mint, summed across all tracked stablecoin contracts."
            ),
            "methodology_url": "https://analytics.topledger.xyz/tl/queries/15090",
        },
        "stablecoin_count": {
            "query_id": 15090,
            "date_field": "block_date",
            "value_field": "stablecoin_count",
            "methodology": (
                "Number of distinct stablecoin contracts tracked on Solana per day."
            ),
            "methodology_url": "https://analytics.topledger.xyz/tl/queries/15090",
        },
        "stablecoin_transfer_volume": {
            "query_id": 15091,
            "date_field": "block_date",
            "value_field": "transfer_volume",
            "methodology": (
                "Daily USD transfer volume of stablecoins on Solana across SPL Token "
                "and SPL Token-2022 programs, priced using 1-minute average prices. "
                "Covers all Transfer and TransferChecked instructions for mapped stablecoin mints."
            ),
            "methodology_url": "https://analytics.topledger.xyz/tl/queries/15091",
        },
        "stablecoin_transfer_count": {
            "query_id": 15091,
            "date_field": "block_date",
            "value_field": "transfer_count",
            "methodology": (
                "Daily count of stablecoin transfer instructions on Solana across "
                "SPL Token and SPL Token-2022 programs for mapped stablecoin mints."
            ),
            "methodology_url": "https://analytics.topledger.xyz/tl/queries/15091",
        },
    }

    _OVERVIEW_METRIC_TYPE_MAP: Dict[str, OverviewMetricType] = {
        "overview_tx_count_total": OverviewMetricType.TX_COUNT_TOTAL,
        "overview_tx_count_vote": OverviewMetricType.TX_COUNT_VOTE,
        "overview_non_vote_tx_count_success": OverviewMetricType.TX_COUNT_NON_VOTE_SUCCESS,
        "overview_non_vote_tx_count_failed": OverviewMetricType.TX_COUNT_NON_VOTE_FAILED,
        "overview_fees": OverviewMetricType.FEES,
        "overview_slots": OverviewMetricType.SLOTS,
        "overview_sol_price": OverviewMetricType.SOL_PRICE,
    }

    _STABLECOIN_METRIC_TYPE_MAP: Dict[str, StablecoinMetricType] = {
        "stablecoin_supply": StablecoinMetricType.SUPPLY,
        "stablecoin_count": StablecoinMetricType.COUNT,
        "stablecoin_transfer_volume": StablecoinMetricType.TRANSFER_VOLUME,
        "stablecoin_transfer_count": StablecoinMetricType.TRANSFER_COUNT,
    }

    _POLL_INTERVAL = 2  # seconds between job status polls
    _POLL_TIMEOUT = 300  # max seconds to wait for a single job

    def __init__(self, *, api_key: Optional[str] = None) -> None:
        resolved = api_key or os.environ.get("TOPLEDGER_API_KEY")
        if not resolved:
            raise ValueError("TOPLEDGER_API_KEY is required")
        super().__init__(
            name="TopLedger",
            base_url=self.BASE_URL,
            api_key=resolved,
        )
        self._session = requests.Session()
        # Cache: (query_id, start_date, end_date) -> raw row list
        self._cache: Dict[tuple[int, str, str], List[Dict[str, Any]]] = {}

    # -- private helpers -------------------------------------------------------

    def _auth(self) -> Dict[str, str]:
        return {"api_key": self.api_key}

    def _run_query(
        self, query_id: int, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """Execute a Redash query with date parameters and return raw rows.

        Results are cached so the same query is never run twice for the same
        date range within a single provider instance.
        """
        cache_key = (query_id, start_date, end_date)
        if cache_key in self._cache:
            return self._cache[cache_key]

        resp = self._session.post(
            f"{self.base_url}/api/queries/{query_id}/results",
            params=self._auth(),
            json={"parameters": {"start_date": start_date, "end_date": end_date}},
            timeout=60,
        )
        resp.raise_for_status()
        payload = resp.json()

        if "query_result" in payload:
            rows = payload["query_result"]["data"]["rows"]
        else:
            job_id = payload["job"]["id"]
            rows = self._poll_job(job_id)

        self._cache[cache_key] = rows
        return rows

    def _poll_job(self, job_id: str) -> List[Dict[str, Any]]:
        """Poll a Redash async job until it completes, then return its rows."""
        deadline = time.monotonic() + self._POLL_TIMEOUT
        while time.monotonic() < deadline:
            time.sleep(self._POLL_INTERVAL)
            resp = self._session.get(
                f"{self.base_url}/api/jobs/{job_id}",
                params=self._auth(),
                timeout=30,
            )
            resp.raise_for_status()
            job = resp.json().get("job", {})
            status = job.get("status")

            if status == 3:  # success
                # Some Redash versions embed the full result; others return only the id.
                if "query_result" in job:
                    return job["query_result"]["data"]["rows"]
                qr_id = job.get("query_result_id")
                if qr_id:
                    return self._fetch_result(qr_id)
                raise RuntimeError(
                    f"Job {job_id} succeeded but contained no result data."
                )

            if status in (4, 5):  # failure or cancelled
                raise RuntimeError(
                    f"Redash job {job_id} ended with status {status}: {job.get('error', 'unknown error')}"
                )

        raise TimeoutError(
            f"Redash job {job_id} did not complete within {self._POLL_TIMEOUT}s."
        )

    def _fetch_result(self, query_result_id: int) -> List[Dict[str, Any]]:
        """Fetch raw rows from a completed query result by its ID."""
        resp = self._session.get(
            f"{self.base_url}/api/query_results/{query_result_id}",
            params=self._auth(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["query_result"]["data"]["rows"]

    # -- BaseProvider interface -------------------------------------------------

    def fetch_rows(
        self, metric: str, start_date: str, end_date: str, **kwargs: Any
    ) -> List[Dict[str, Any]]:
        """Return normalized {"date": str, "value": float} records for the given range (both dates inclusive)."""
        config = self.METRIC_MAP.get(metric)
        if config is None:
            available = ", ".join(self.METRIC_MAP)
            raise ValueError(f"Unknown metric '{metric}'. Available: {available}")

        raw_rows = self._run_query(config["query_id"], start_date, end_date)
        result = []
        for row in raw_rows:
            row_date = str(row.get(config["date_field"], ""))[:10]
            if not row_date or not (start_date <= row_date <= end_date):
                continue
            value = row.get(config["value_field"])
            if value is None:
                continue
            result.append({"date": row_date, "value": float(value)})
        return result

    def get_metric(
        self, metric: str, date: str, chain: str
    ) -> Overview | Stablecoin | None:
        """Fetch one metric for one date and return it as a typed metric model."""
        rows = self.fetch_rows(metric, date, date)
        if not rows:
            return None
        value = rows[0]["value"]
        parsed_date = datetime.date.fromisoformat(date)

        overview_type = self._OVERVIEW_METRIC_TYPE_MAP.get(metric)
        if overview_type is not None:
            return Overview.from_metric_type(
                metric_type=overview_type, date=parsed_date, value=value
            )

        stablecoin_type = self._STABLECOIN_METRIC_TYPE_MAP.get(metric)
        if stablecoin_type is not None:
            return Stablecoin.from_metric_type(
                metric_type=stablecoin_type, date=parsed_date, value=value
            )

        return None
