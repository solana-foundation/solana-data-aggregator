"""Top Ledger data provider."""

from __future__ import annotations

import datetime
import os
import time
from typing import Any, Dict, List, Optional

import requests

from metrics.defi import Defi, DefiMetricType
from metrics.network import Network, NetworkMetricType
from metrics.overview import Overview, OverviewMetricType
from metrics.perps import Perps, PerpsMetricType
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
    Multiple metrics can share the same Redash query. Raw rows are cached
    in-process by (query_id, start_date, end_date) so each query runs at
    most once per date range regardless of how many metrics are requested.
    """

    BASE_URL = "https://analytics.topledger.xyz/tl"

    METRIC_MAP: Dict[str, Dict[str, Any]] = {
        "overview_non_vote_tx_count_success": {
            "query_id": 15088,
            "date_field": "block_date",
            "value_field": "successful_non_vote_transactions",
            "methodology": "Successful non-vote transactions",
        },
        "overview_non_vote_tx_count_failed": {
            "query_id": 15088,
            "date_field": "block_date",
            "value_field": "failed_non_vote_transactions",
            "methodology": "Failed non-vote transactions",
        },
        "overview_slots": {
            "query_id": 15088,
            "date_field": "block_date",
            "value_field": "slots",
            "methodology": "Confirmed block slots",
        },
        "overview_tx_count_total": {
            "query_id": 15088,
            "date_field": "block_date",
            "value_field": "transactions",
            "methodology": "Total count of all transactions on Solana per day",
        },
        "overview_tx_count_vote": {
            "query_id": 15088,
            "date_field": "block_date",
            "value_field": "vote_transactions",
            "methodology": "Count of vote transactions on Solana per day",
        },
        "overview_fees": {
            "query_id": 15088,
            "date_field": "block_date",
            "value_field": "txns_fees",
            "methodology": "Daily fees (base plus priority) on Solana in SOL",
        },
        "overview_compute_units": {
            "query_id": 15357,
            "date_field": "block_date",
            "value_field": "avg_cu_per_block",
            "methodology": "Average compute units per block daily on Solana",
        },
        "overview_sol_price": {
            "query_id": 15089,
            "date_field": "block_date",
            "value_field": "sol_price_usd",
            "methodology": "Average SOL price in USD",
        },
        "overview_fee_payers": {
            "query_id": 15096,
            "date_field": "block_date",
            "value_field": "fee_payer",
            "methodology": "Unique signers of non-vote transactions",
        },
        "stablecoin_circulating_supply": {
            "query_id": 15090,
            "date_field": "block_date",
            "value_field": "marketcap",
            "methodology": "Circulating supply of stablecoins in USD",
        },
        "stablecoin_total_supply": {
            "query_id": 15090,
            "date_field": "block_date",
            "value_field": "total_supply",
            "methodology": "Total supply of stablecoins in USD, including non-circulating balances",
        },
        "stablecoin_count": {
            "query_id": 15090,
            "date_field": "block_date",
            "value_field": "stablecoin_count",
            "methodology": "Distinct stablecoin contracts tracked",
        },
        "stablecoin_transfer_volume": {
            "query_id": 15091,
            "date_field": "block_date",
            "value_field": "transfer_volume",
            "methodology": "USD value of stablecoin transfers",
        },
        "stablecoin_transfer_count": {
            "query_id": 15091,
            "date_field": "block_date",
            "value_field": "transfer_count",
            "methodology": "Stablecoin transfer instructions",
        },
        "stablecoin_active_addresses": {
            "query_id": 15092,
            "date_field": "block_date",
            "value_field": "active_address",
            "methodology": "Unique signers of transactions containing a stablecoin transfer",
        },
        "defi_dex_volume": {
            "query_id": 15093,
            "date_field": "block_date",
            "value_field": "dex_volume",
            "methodology": "USD value of spot DEX trades excluding Pump wash trading and filtered pools",
        },
        "defi_dex_transactions": {
            "query_id": 15103,
            "date_field": "block_date",
            "value_field": "dex_transactions",
            "methodology": "Distinct DEX swap transactions, with multi-hop swaps counted once per transaction",
        },
        "defi_dex_traders": {
            "query_id": 15103,
            "date_field": "block_date",
            "value_field": "traders",
            "methodology": "Unique wallet signers initiating DEX swap transactions",
        },
        "defi_dex_count": {
            "query_id": 15103,
            "date_field": "block_date",
            "value_field": "dex_counts",
            "methodology": "Distinct DEX programs with trading activity",
        },
        "perps_trading_volume": {
            "query_id": 15344,
            "date_field": "block_date",
            "value_field": "trading_volume_usd",
            "methodology": "Daily perpetual futures trading volume across Solana perp venues in USD",
        },
        "perps_transactions": {
            "query_id": 15344,
            "date_field": "block_date",
            "value_field": "transactions",
            "methodology": "Number of perpetual futures trades on Solana perp venues per day",
        },
        "perps_venue_count": {
            "query_id": 15344,
            "date_field": "block_date",
            "value_field": "perp_venue_count",
            "methodology": "Number of Solana perp venues with trading activity",
        },
        "perps_traders": {
            "query_id": 15346,
            "date_field": "block_date",
            "value_field": "unique_traders",
            "methodology": "Number of unique daily traders on Solana perp venues",
        },
        "perps_open_interest": {
            "query_id": 15343,
            "date_field": "block_date",
            "value_field": "total_open_interest_usd",
            "methodology": "Total open interest across Solana perp venues in USD",
        },
        "network_total_stake": {
            "query_id": 15379,
            "date_field": "block_date",
            "value_field": "sol_staked",
            "methodology": "Total staked SOL across all validators on Solana daily",
        },
        "network_validator_count": {
            "query_id": 15380,
            "date_field": "block_date",
            "value_field": "validators_count",
            "methodology": "Number of active validators on Solana daily",
        },
        "network_top_3_asn_share": {
            "query_id": 15380,
            "date_field": "block_date",
            "value_field": "asn_share_top3",
            "methodology": "Percentage of stake concentrated in the top 3 ASNs on Solana daily",
        },
        "network_avg_tps": {
            "query_id": 15088,
            "date_field": "block_date",
            "value_field": "avg_tps",
            "methodology": "Daily average transactions per second on Solana (non-vote transactions, successful and failed, / 86,400)",
        },
    }

    _OVERVIEW_METRIC_TYPE_MAP: Dict[str, OverviewMetricType] = {
        "overview_non_vote_tx_count_success": OverviewMetricType.TX_COUNT_NON_VOTE_SUCCESS,
        "overview_non_vote_tx_count_failed": OverviewMetricType.TX_COUNT_NON_VOTE_FAILED,
        "overview_slots": OverviewMetricType.SLOTS,
        "overview_tx_count_total": OverviewMetricType.TX_COUNT_TOTAL,
        "overview_tx_count_vote": OverviewMetricType.TX_COUNT_VOTE,
        "overview_fees": OverviewMetricType.FEES,
        "overview_compute_units": OverviewMetricType.COMPUTE_UNITS,
        "overview_sol_price": OverviewMetricType.SOL_PRICE,
        "overview_fee_payers": OverviewMetricType.FEE_PAYERS,
    }

    _STABLECOIN_METRIC_TYPE_MAP: Dict[str, StablecoinMetricType] = {
        "stablecoin_circulating_supply": StablecoinMetricType.CIRCULATING_SUPPLY,
        "stablecoin_total_supply": StablecoinMetricType.TOTAL_SUPPLY,
        "stablecoin_count": StablecoinMetricType.COUNT,
        "stablecoin_transfer_volume": StablecoinMetricType.TRANSFER_VOLUME,
        "stablecoin_transfer_count": StablecoinMetricType.TRANSFER_COUNT,
        "stablecoin_active_addresses": StablecoinMetricType.ACTIVE_ADDRESSES,
    }

    _DEFI_METRIC_TYPE_MAP: Dict[str, DefiMetricType] = {
        "defi_dex_volume": DefiMetricType.DEX_VOLUME,
        "defi_dex_transactions": DefiMetricType.DEX_TRANSACTIONS,
        "defi_dex_traders": DefiMetricType.DEX_TRADERS,
        "defi_dex_count": DefiMetricType.DEX_COUNT,
    }

    _PERPS_METRIC_TYPE_MAP: Dict[str, PerpsMetricType] = {
        "perps_trading_volume": PerpsMetricType.TRADING_VOLUME,
        "perps_transactions": PerpsMetricType.TRANSACTIONS,
        "perps_venue_count": PerpsMetricType.VENUE_COUNT,
        "perps_traders": PerpsMetricType.TRADERS,
        "perps_open_interest": PerpsMetricType.OPEN_INTEREST,
    }

    _NETWORK_METRIC_TYPE_MAP: Dict[str, NetworkMetricType] = {
        "network_total_stake": NetworkMetricType.TOTAL_STAKE,
        "network_validator_count": NetworkMetricType.VALIDATOR_COUNT,
        "network_top_3_asn_share": NetworkMetricType.TOP_3_ASN_SHARE,
        "network_avg_tps": NetworkMetricType.AVG_TPS,
    }

    _POLL_INTERVAL = 2  # seconds between job status polls
    _POLL_TIMEOUT = 300  # max seconds to wait for a single job

    def __init__(self, *, api_key: Optional[str] = None) -> None:
        resolved = api_key or os.environ.get("TOPLEDGER_API_KEY")
        if not resolved:
            raise ValueError("TOPLEDGER_API_KEY is required")
        super().__init__(
            name="Top Ledger",
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
            json={"parameters": {"start_date": start_date, "end_date": end_date}, "max_age": 0},
            timeout=120,
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
    ) -> Overview | Stablecoin | Defi | Perps | Network | None:
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

        defi_type = self._DEFI_METRIC_TYPE_MAP.get(metric)
        if defi_type is not None:
            return Defi.from_metric_type(
                metric_type=defi_type, date=parsed_date, value=value
            )

        perps_type = self._PERPS_METRIC_TYPE_MAP.get(metric)
        if perps_type is not None:
            return Perps.from_metric_type(
                metric_type=perps_type, date=parsed_date, value=value
            )

        network_type = self._NETWORK_METRIC_TYPE_MAP.get(metric)
        if network_type is not None:
            return Network.from_metric_type(
                metric_type=network_type, date=parsed_date, value=value
            )

        return None
