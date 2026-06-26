"""Allium data provider."""

from __future__ import annotations

import datetime
import os
import time
from typing import Any, Dict, List, Optional

import requests

from metrics.defi import Defi, DefiMetricType
from metrics.overview import Overview, OverviewMetricType
from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.base import BaseProvider


class Allium(BaseProvider):
    """Fetch stablecoin metrics from the Allium Explorer API."""

    METRIC_MAP: Dict[str, Dict[str, str]] = {
        "stablecoin_supply": {
            "date_field": "date",
            "value_field": "usd",
            "methodology": "Net mints minus burns, excluding treasury and locked balances.",
            "sql": """
                SELECT
                    date,
                    SUM(circulating_supply * price) AS usd
                FROM solana.stablecoins.supply_distribution_daily t1
                LEFT JOIN solana.prices.token_prices_hourly t2
                    ON t1.date = t2.timestamp
                    AND t1.token_address = t2.token_mint
                WHERE date >= DATE '{start_date}'
                  AND date < DATEADD('day', 1, DATE '{end_date}')
                GROUP BY ALL
                ORDER BY date
            """,
        },
        "stablecoin_transfer_volume": {
            "date_field": "day",
            "value_field": "volume_usd",
            "methodology": "USD transfer volume, deduplicated and filtered per Visa methodology.",
            "sql": """
            SELECT
                DATE(block_timestamp) AS day,
                SUM(usd_amount) AS volume_usd
            FROM solana.assets.stablecoin_transfers
            WHERE block_timestamp >= DATE '{start_date}'
              AND block_timestamp < DATEADD('day', 1, DATE '{end_date}')
            GROUP BY 1
            ORDER BY 1
        """,
        },
        "stablecoin_transfer_count": {
            "date_field": "day",
            "value_field": "transfer_count",
            "sql": """
            SELECT
                DATE(block_timestamp) AS day,
                COUNT(*) AS transfer_count
            FROM solana.assets.stablecoin_transfers
            WHERE block_timestamp >= DATE '{start_date}'
              AND block_timestamp < DATEADD('day', 1, DATE '{end_date}')
            GROUP BY 1
            ORDER BY 1
        """,
        },
        "stablecoin_active_addresses": {
            "date_field": "day",
            "value_field": "active_addresses",
            "chunked": True,
            "methodology": "Unique stablecoin transfer senders and receivers, excluding inorganic activity.",
            "sql": """
            SELECT
                day,
                COUNT(DISTINCT address) AS active_addresses
            FROM (
                SELECT DATE(block_timestamp) AS day, from_address AS address
                FROM solana.assets.stablecoin_transfers
                WHERE block_timestamp >= DATE '{start_date}'
                  AND block_timestamp < DATEADD('day', 1, DATE '{end_date}')
                UNION
                SELECT DATE(block_timestamp) AS day, to_address AS address
                FROM solana.assets.stablecoin_transfers
                WHERE block_timestamp >= DATE '{start_date}'
                  AND block_timestamp < DATEADD('day', 1, DATE '{end_date}')
            ) t
            GROUP BY day
            ORDER BY day
        """,
        },
        "overview_slots": {
            "date_field": "block_date",
            "value_field": "slots_per_day",
            "sql": """
                SELECT
                    timestamp::date AS block_date,
                    COUNT(*) AS slots_per_day
                FROM solana.raw.blocks
                WHERE timestamp >= '{start_date}'
                  AND timestamp <  DATEADD('day', 1, '{end_date}')
                GROUP BY 1
                ORDER BY 1 ASC
            """,
        },
        "overview_fee_payers": {
            "date_field": "block_date",
            "value_field": "fee_payers_count",
            "sql": """
                SELECT
                    activity_date::DATE AS block_date,
                    tx_initiating_addresses AS fee_payers_count
                FROM solana.metrics.overview
                WHERE activity_date >= '{start_date}'
                  AND activity_date < DATEADD('day', 1, '{end_date}')
                ORDER BY block_date ASC
            """,
        },
        "overview_sol_price": {
            "date_field": "timestamp",
            "value_field": "price",
            "price_api": True,
        },
        "overview_tx_count_total": {
            "date_field": "activity_date",
            "value_field": "total_transactions",
            "sql": """
                SELECT
                    activity_date,
                    total_transactions
                FROM solana.metrics.overview
                WHERE activity_date >= '{start_date}'
                  AND activity_date < DATEADD('day', 1, '{end_date}')
                ORDER BY activity_date ASC
            """,
        },
        "overview_non_vote_tx_count_success": {
            "date_field": "activity_date",
            "value_field": "success_non_voting_tx_count",
            "sql": """
                SELECT
                    activity_date,
                    success_non_voting_tx_count
                FROM solana.metrics.overview
                WHERE activity_date >= '{start_date}'
                  AND activity_date < DATEADD('day', 1, '{end_date}')
                ORDER BY activity_date ASC
            """,
        },
        "overview_non_vote_tx_count_failed": {
            "date_field": "activity_date",
            "value_field": "failed_non_voting_tx_count",
            "sql": """
                SELECT
                    activity_date,
                    failed_non_voting_tx_count
                FROM solana.metrics.overview
                WHERE activity_date >= '{start_date}'
                  AND activity_date < DATEADD('day', 1, '{end_date}')
                ORDER BY activity_date ASC
            """,
        },
        "overview_tx_count_vote": {
            "date_field": "activity_date",
            "value_field": "total_voting_tx_count",
            "sql": """
                SELECT
                    activity_date,
                    success_voting_tx_count + failed_voting_tx_count AS total_voting_tx_count
                FROM solana.metrics.overview
                WHERE activity_date >= '{start_date}'
                  AND activity_date < DATEADD('day', 1, '{end_date}')
                ORDER BY activity_date ASC
            """,
        },
        "overview_fees": {
            "date_field": "day",
            "value_field": "total_fees_sol",
            "chunked": True,
            "sql": """
                SELECT
                    activity_date::DATE AS day,
                    transaction_fees AS total_fees_sol
                FROM solana.metrics.overview
                WHERE activity_date >= '{start_date}'
                  AND activity_date < DATEADD('day', 1, '{end_date}')
                ORDER BY day ASC
            """,
        },
        "stablecoin_count": {
            "date_field": "date",
            "value_field": "distinct_usd_stablecoins",
            "sql": """
                SELECT
                    block_timestamp::date AS date,
                    COUNT(DISTINCT mint) AS distinct_usd_stablecoins
                FROM solana.stablecoins.transfers
                WHERE currency = 'usd'
                  AND block_timestamp >= '{start_date}'
                  AND block_timestamp <  DATEADD('day', 1, '{end_date}')
                GROUP BY 1
                ORDER BY 1 ASC
            """,
        },
        "defi_dex_volume": {
            "date_field": "date",
            "value_field": "daily_volume_usd",
            "methodology": "Filters for washtrading activity.",
            "sql": """
                SELECT
                    activity_date AS date,
                    dex_volume_usd_adjusted AS daily_volume_usd
                FROM solana.metrics.overview
                WHERE activity_date >= '{start_date}'
                  AND activity_date < DATEADD('day', 1, '{end_date}')
                ORDER BY 1 ASC
            """,
        },
        "defi_dex_traders": {
            "date_field": "activity_date",
            "value_field": "dex_trader_count",
            "methodology": "Unique Solana DEX swap initiators; no bot filter applied.",
            "sql": """
                SELECT
                    activity_date,
                    dex_trader_count
                FROM solana.metrics.overview
                WHERE activity_date >= '{start_date}'
                  AND activity_date < DATEADD('day', 1, '{end_date}')
                ORDER BY activity_date ASC
            """,
        },
        "defi_dex_count": {
            "date_field": "activity_date",
            "value_field": "active_dex_projects",
            "methodology": "Unique Solana DEX protocols by project and protocol version.",
            "sql": """
                SELECT
                    block_timestamp::date AS activity_date,
                    COUNT(DISTINCT project) AS active_dex_projects
                FROM solana.dex.trades
                WHERE block_timestamp >= '{start_date}'
                  AND block_timestamp <  DATEADD('day', 1, '{end_date}')
                GROUP BY 1
                ORDER BY 1 ASC
            """,
        },
        "defi_dex_transactions": {
            "date_field": "activity_date",
            "value_field": "dex_trade_tx_count",
            "methodology": "Unique Solana DEX swap transactions; multi-hop swaps count once.",
            "sql": """
                SELECT
                    activity_date,
                    dex_trade_tx_count
                FROM solana.metrics.overview
                WHERE activity_date >= '{start_date}'
                  AND activity_date < DATEADD('day', 1, '{end_date}')
                ORDER BY activity_date ASC
            """,
        },
        "overview_compute_units": {
            "date_field": "date",
            "value_field": "avg_compute_units_per_block",
            "sql": """
                SELECT
                    block_timestamp::date AS date,
                    SUM(compute_units_consumed) / COUNT(DISTINCT block_slot) AS avg_compute_units_per_block
                FROM solana.raw.transactions
                WHERE block_timestamp >= '{start_date}'
                  AND block_timestamp <  DATEADD('day', 1, '{end_date}')
                GROUP BY 1
                ORDER BY 1
            """,
        },
    }

    BASE_URL = "https://api.allium.so/api/v1"
    SOL_TOKEN_ADDRESS = "So11111111111111111111111111111111111111112"

    def __init__(self, *, api_key: Optional[str] = None) -> None:
        resolved_api_key = api_key or self._resolve_api_key()
        if not resolved_api_key:
            raise ValueError("API key is required")
        super().__init__(
            name="Allium",
            base_url=self.BASE_URL,
            api_key=resolved_api_key,
        )
        self._session = requests.Session()

    # -- private helpers ----------------------------------------------------

    @staticmethod
    def _resolve_api_key() -> Optional[str]:
        """Try env-var, then Databricks secrets."""
        return os.environ.get("ALLIUM_API_KEY")

    def _post(self, endpoint: str, payload: Optional[Dict[str, Any]] = None) -> dict:
        """Perform an authenticated POST against the Allium Explorer API."""
        url = f"{self.base_url}{endpoint}"
        headers = {"X-API-Key": self.api_key, "Content-Type": "application/json"}
        resp = self._session.post(url, headers=headers, json=payload or {}, timeout=300)
        resp.raise_for_status()
        return resp.json()

    def _run_sql(self, sql: str, retries: int = 3) -> List[Dict[str, Any]]:
        """Execute a SQL query via the Allium Explorer API (two-step: create + run)."""
        # Step 1: Create the query
        query_id = self._post(
            "/explorer/queries",
            payload={
                "title": "temp_query",
                "config": {"type": "sql", "sql": sql, "parameters": {}, "limit": 10000},
            },
        )["query_id"]

        time.sleep(1)

        # Step 2: Run by query ID (with retries for transient server errors)
        url = f"{self.base_url}/explorer/queries/{query_id}/run"
        headers = {"X-API-Key": self.api_key, "Content-Type": "application/json"}
        for attempt in range(retries):
            try:
                resp = self._session.post(url, headers=headers, json={}, timeout=300)
                resp.raise_for_status()
                return resp.json().get("data", [])
            except requests.exceptions.HTTPError as e:
                if e.response.status_code in (503, 524) and attempt < retries - 1:
                    wait = 30 * (attempt + 1)
                    print(
                        f"  Timeout ({e.response.status_code}), retrying in {wait}s... "
                        f"(attempt {attempt + 2}/{retries})"
                    )
                    time.sleep(wait)
                else:
                    print(f"HTTP error: {e}")
                    raise

        return []

    def _fetch_price_rows(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """Fetch daily SOL price from the Allium Developer Prices API."""
        # end_timestamp is exclusive, so add one day to make the range inclusive
        end_dt = datetime.date.fromisoformat(end_date) + datetime.timedelta(days=1)
        payload = {
            "start_timestamp": f"{start_date}T00:00:00Z",
            "end_timestamp": f"{end_dt.isoformat()}T00:00:00Z",
            "addresses": [{"chain": "solana", "token_address": self.SOL_TOKEN_ADDRESS}],
            "time_granularity": "1d",
        }
        data = self._post("/developer/prices/history", payload=payload)
        items = data.get("items", [])
        if not items:
            return []
        return items[0].get("prices", [])

    def _run_sql_chunked(
        self, sql_template: str, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """Break a query into monthly chunks for large tables."""
        all_rows: List[Dict[str, Any]] = []
        start = datetime.date.fromisoformat(start_date)
        end = datetime.date.fromisoformat(end_date)

        current = start.replace(day=1)
        while current <= end:
            month_start = max(current, start)
            if current.month == 12:
                next_month = current.replace(year=current.year + 1, month=1)
            else:
                next_month = current.replace(month=current.month + 1)
            month_end = min(next_month - datetime.timedelta(days=1), end)

            sql = sql_template.format(
                start_date=month_start.isoformat(),
                end_date=month_end.isoformat(),
            )
            print(f"  Chunk: {month_start} → {month_end}")
            all_rows.extend(self._run_sql(sql))

            current = next_month

        return all_rows

    # -- BaseProvider interface ---------------------------------------------

    @property
    def provider_name(self) -> str:
        return self.name

    def fetch_rows(
        self, metric: str, start_date: str, end_date: str, **kwargs: Any
    ) -> List[Dict[str, Any]]:
        """Return normalized {"date": str, "value": Any} records for the given range (both dates inclusive)."""
        config = self.METRIC_MAP[metric]
        result = []
        if config.get("price_api"):
            raw_rows = self._fetch_price_rows(start_date, end_date)
        elif config.get("chunked", False):
            raw_rows = self._run_sql_chunked(config["sql"], start_date, end_date)
        else:
            raw_rows = self._run_sql(
                config["sql"].format(start_date=start_date, end_date=end_date)
            )
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
    ) -> Stablecoin | Overview | Defi | None:
        """Fetch one metric value and return it as a typed metric model."""
        rows = self.fetch_rows(metric, date, date)
        if not rows:
            return None

        value = rows[0]["value"]
        parsed_date = datetime.date.fromisoformat(date)

        overview_metric_map = {
            "overview_slots": OverviewMetricType.SLOTS,
            "overview_fee_payers": OverviewMetricType.FEE_PAYERS,
            "overview_sol_price": OverviewMetricType.SOL_PRICE,
            "overview_fees": OverviewMetricType.FEES,
            "overview_tx_count_total": OverviewMetricType.TX_COUNT_TOTAL,
            "overview_tx_count_vote": OverviewMetricType.TX_COUNT_VOTE,
            "overview_non_vote_tx_count_success": OverviewMetricType.TX_COUNT_NON_VOTE_SUCCESS,
            "overview_non_vote_tx_count_failed": OverviewMetricType.TX_COUNT_NON_VOTE_FAILED,
            "overview_compute_units": OverviewMetricType.COMPUTE_UNITS,
        }
        if metric in overview_metric_map:
            return Overview.from_metric_type(
                metric_type=overview_metric_map[metric],
                date=parsed_date,
                value=value,
            )

        defi_metric_map = {
            "defi_dex_volume": DefiMetricType.DEX_VOLUME,
            "defi_dex_transactions": DefiMetricType.DEX_TRANSACTIONS,
            "defi_dex_traders": DefiMetricType.DEX_TRADERS,
            "defi_dex_count": DefiMetricType.DEX_COUNT,
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
            "stablecoin_count": StablecoinMetricType.COUNT,
        }
        return Stablecoin.from_metric_type(
            metric_type=stablecoin_metric_map[metric],
            date=parsed_date,
            value=value,
        )
