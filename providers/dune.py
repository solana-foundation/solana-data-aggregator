"""Dune Analytics data provider."""

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


class Dune(BaseProvider):
    """Fetch stablecoin metrics from the Dune SQL API."""

    METRIC_MAP: Dict[str, Dict[str, str]] = {
        "stablecoin_supply": {
            "date_field": "day",
            "value_field": "total_supply_usd",
            "sql": """
                SELECT
                    b.day,
                    SUM(b.balance_usd) AS total_supply_usd
                FROM stablecoins_solana.balances AS b
                WHERE b.balance > 0
                  AND b.day BETWEEN DATE '{start_date}' AND DATE '{end_date}'
                GROUP BY b.day
                ORDER BY b.day ASC
            """,
        },
        "stablecoin_transfer_volume": {
            "date_field": "block_date",
            "value_field": "volume_usd",
            "sql": """
                SELECT
                    t.block_date,
                    SUM(t.amount_usd) AS volume_usd
                FROM stablecoins_solana.transfers AS t
                WHERE t.block_date BETWEEN DATE '{start_date}' AND DATE '{end_date}'
                GROUP BY t.block_date
                ORDER BY t.block_date ASC
            """,
        },
        "stablecoin_transfer_count": {
            "date_field": "block_date",
            "value_field": "transfers",
            "sql": """
                SELECT
                    t.block_date,
                    COUNT(*) AS transfers
                FROM stablecoins_solana.transfers AS t
                WHERE t.block_date BETWEEN DATE '{start_date}' AND DATE '{end_date}'
                GROUP BY t.block_date
                ORDER BY t.block_date ASC
            """,
        },
        "stablecoin_active_addresses": {
            "date_field": "block_date",
            "value_field": "active_wallets",
            "sql": """
                SELECT
                    block_date,
                    COUNT(DISTINCT wallet) AS active_wallets
                FROM (
                    SELECT block_date, from_owner AS wallet
                    FROM stablecoins_solana.transfers
                    WHERE block_date BETWEEN DATE '{start_date}' AND DATE '{end_date}'
                    UNION ALL
                    SELECT block_date, to_owner AS wallet
                    FROM stablecoins_solana.transfers
                    WHERE block_date BETWEEN DATE '{start_date}' AND DATE '{end_date}'
                ) t
                GROUP BY block_date
                ORDER BY block_date ASC
            """,
        },
        "stablecoin_count": {
            "date_field": "day",
            "value_field": "distinct_stablecoins",
            "sql": """
                SELECT
                    DATE_TRUNC('day', block_time) AS day,
                    COUNT(DISTINCT token_mint_address) AS distinct_stablecoins
                FROM stablecoins_solana.transfers
                WHERE blockchain = 'solana'
                  AND currency = 'USD'
                  AND block_time >= TIMESTAMP '{start_date}'
                  AND block_time <  TIMESTAMP '{end_date}' + INTERVAL '1' DAY
                GROUP BY DATE_TRUNC('day', block_time)
                ORDER BY day ASC
            """,
        },
        "overview_slots": {
            "date_field": "block_date",
            "value_field": "slots_per_day",
            "sql": """
                SELECT
                    date AS block_date,
                    COUNT(*) AS slots_per_day
                FROM solana.blocks
                WHERE date BETWEEN DATE '{start_date}' AND DATE '{end_date}'
                GROUP BY date
                ORDER BY date ASC
            """,
        },
        "overview_fee_payers": {
            "date_field": "block_date",
            "value_field": "fee_payers",
            "performance": "large",
            "timeout": 3600,
            "sql": """
                SELECT
                    block_date,
                    COUNT(DISTINCT signer) AS fee_payers
                FROM solana.transactions
                WHERE block_date BETWEEN DATE '{start_date}' AND DATE '{end_date}'
                GROUP BY block_date
                ORDER BY block_date ASC
            """,
        },
        "overview_sol_price": {
            "date_field": "block_date",
            "value_field": "price_usd",
            "sql": """
                SELECT
                    DATE(timestamp) AS block_date,
                    AVG(price) AS price_usd
                FROM prices.day
                WHERE blockchain = 'solana'
                  AND symbol = 'SOL'
                  AND DATE(timestamp) BETWEEN DATE '{start_date}' AND DATE '{end_date}'
                GROUP BY DATE(timestamp)
                ORDER BY block_date ASC
            """,
        },
        "overview_fees": {
            "date_field": "day",
            "value_field": "fee_sol",
            "performance": "large",
            "sql": """
                SELECT
                    day,
                    SUM(fee) AS fee_sol
                FROM (
                    SELECT
                        date_trunc('day', block_time) AS day,
                        SUM(fee / 1e9) AS fee
                    FROM solana.transactions
                    WHERE block_date BETWEEN DATE '{start_date}' AND DATE '{end_date}'
                    GROUP BY 1

                    UNION ALL

                    SELECT
                        date_trunc('day', block_time) AS day,
                        SUM(fee / 1e9) AS fee
                    FROM solana.vote_transactions
                    WHERE block_date BETWEEN DATE '{start_date}' AND DATE '{end_date}'
                    GROUP BY 1
                ) t
                GROUP BY 1
                ORDER BY 1
            """,
        },
        "overview_tx_count_total": {
            "date_field": "block_date",
            "value_field": "total_txns",
            "sql": """
                SELECT
                    date AS block_date,
                    SUM(total_transactions) AS total_txns
                FROM solana.blocks
                WHERE date BETWEEN DATE '{start_date}' AND DATE '{end_date}'
                GROUP BY date
                ORDER BY block_date ASC
            """,
        },
        "overview_tx_count_vote": {
            "date_field": "block_date",
            "value_field": "vote_txns",
            "sql": """
                SELECT
                    date AS block_date,
                    SUM(total_vote_transactions) AS vote_txns
                FROM solana.blocks
                WHERE date BETWEEN DATE '{start_date}' AND DATE '{end_date}'
                GROUP BY date
                ORDER BY block_date ASC
            """,
        },
        "defi_dex_volume": {
            "date_field": "date",
            "value_field": "volume_usd",
            "sql": """
                SELECT
                    DATE_TRUNC('day', block_time) AS date,
                    SUM(amount_usd) AS volume_usd
                FROM dex_solana.trades
                WHERE block_time >= TIMESTAMP '{start_date}'
                  AND block_time < TIMESTAMP '{end_date}' + INTERVAL '1' DAY
                GROUP BY 1
                ORDER BY 1 ASC
            """,
        },
        "overview_non_vote_tx_count_success": {
            "date_field": "block_date",
            "value_field": "success_txns",
            "sql": """
                SELECT
                    date AS block_date,
                    SUM(successful_non_vote_transactions) AS success_txns
                FROM solana.blocks
                WHERE date BETWEEN DATE '{start_date}' AND DATE '{end_date}'
                GROUP BY 1
                ORDER BY block_date ASC
            """,
        },
        "overview_non_vote_tx_count_failed": {
            "date_field": "block_date",
            "value_field": "failed_txns",
            "sql": """
                SELECT
                    date AS block_date,
                    SUM(failed_non_vote_transactions) AS failed_txns
                FROM solana.blocks
                WHERE date BETWEEN DATE '{start_date}' AND DATE '{end_date}'
                GROUP BY 1
                ORDER BY block_date ASC
            """,
        },
        "defi_dex_traders": {
            "date_field": "day",
            "value_field": "unique_traders",
            "performance": "large",
            "sql": """
                SELECT
                    block_date AS day,
                    COUNT(DISTINCT trader_id) AS unique_traders
                FROM dex_solana.trades
                WHERE block_date BETWEEN DATE '{start_date}' AND DATE '{end_date}'
                GROUP BY block_date
                ORDER BY block_date ASC
            """,
        },
        "defi_dex_count": {
            "date_field": "day",
            "value_field": "unique_dex_count",
            "performance": "large",
            "sql": """
                SELECT
                    DATE_TRUNC('day', block_time) AS day,
                    COUNT(DISTINCT project) AS unique_dex_count
                FROM dex_solana.trades
                WHERE block_time >= TIMESTAMP '{start_date}'
                  AND block_time < TIMESTAMP '{end_date}' + INTERVAL '1' DAY
                GROUP BY DATE_TRUNC('day', block_time)
                ORDER BY day ASC
            """,
        },
        "defi_dex_transactions": {
            "date_field": "day",
            "value_field": "transaction_count",
            "performance": "large",
            "sql": """
                SELECT
                    DATE_TRUNC('day', block_time) AS day,
                    COUNT(DISTINCT tx_id) AS transaction_count
                FROM dex_solana.trades
                WHERE block_time >= TIMESTAMP '{start_date}'
                  AND block_time < TIMESTAMP '{end_date}' + INTERVAL '1' DAY
                GROUP BY DATE_TRUNC('day', block_time)
                ORDER BY day ASC
            """,
        },
        "overview_compute_units": {
            "date_field": "block_date",
            "value_field": "avg_compute_units_per_block",
            "performance": "large",
            "sql": """
                SELECT
                    block_date,
                    SUM(compute_units_consumed) / COUNT(DISTINCT block_slot) AS avg_compute_units_per_block
                FROM solana.transactions
                WHERE block_date BETWEEN DATE '{start_date}' AND DATE '{end_date}'
                GROUP BY block_date
                ORDER BY block_date
            """,
        },
    }

    BASE_URL = "https://api.dune.com/api/v1"

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        poll_interval: int = 5,
        timeout: int = 300,
    ) -> None:
        resolved_api_key = api_key or self._resolve_api_key()
        if not resolved_api_key:
            raise ValueError("API key is required")
        super().__init__(
            name="Dune",
            base_url=self.BASE_URL,
            api_key=resolved_api_key,
        )
        self._poll_interval = poll_interval
        self._timeout = timeout
        self._session = requests.Session()

    # -- private helpers ----------------------------------------------------

    @staticmethod
    def _resolve_api_key() -> Optional[str]:
        return os.environ.get("DUNE_API_KEY")

    def _post(self, endpoint: str, payload: Optional[Dict[str, Any]] = None) -> dict:
        url = f"{self.base_url}{endpoint}"
        headers = {"X-DUNE-API-KEY": self.api_key, "Content-Type": "application/json"}
        resp = self._session.post(url, headers=headers, json=payload or {})
        resp.raise_for_status()
        return resp.json()

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> dict:
        url = f"{self.base_url}{endpoint}"
        headers = {"X-DUNE-API-KEY": self.api_key}
        resp = self._session.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()

    def _execute_sql(self, sql: str, performance: str = "medium") -> str:
        body = self._post(
            "/sql/execute", payload={"sql": sql, "performance": performance}
        )
        return body["execution_id"]

    def _poll_results(
        self, execution_id: str, timeout: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        elapsed = 0
        limit = timeout if timeout is not None else self._timeout
        while elapsed < limit:
            status = self._get(f"/execution/{execution_id}/status")
            state = status.get("state")
            if state == "QUERY_STATE_COMPLETED":
                results = self._get(f"/execution/{execution_id}/results")
                return results.get("result", {}).get("rows", [])
            if state in {"QUERY_STATE_FAILED", "QUERY_STATE_CANCELLED"}:
                raise RuntimeError(f"Dune query failed with state: {state}")
            time.sleep(self._poll_interval)
            elapsed += self._poll_interval
        raise TimeoutError(f"Query did not complete within {limit}s")

    def _run_sql(
        self, sql: str, performance: str = "medium", timeout: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        execution_id = self._execute_sql(sql, performance=performance)
        return self._poll_results(execution_id, timeout=timeout)

    def fetch_rows(
        self, metric: str, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """Return normalized {"date": str, "value": Any} records for the given range (both dates inclusive)."""
        config = self.METRIC_MAP[metric]
        sql = config["sql"].format(start_date=start_date, end_date=end_date)
        result = []
        for row in self._run_sql(
            sql,
            performance=config.get("performance", "medium"),
            timeout=config.get("timeout"),
        ):
            row_date = str(row.get(config["date_field"], ""))[:10]
            if not row_date:
                continue
            value = row.get(config["value_field"])
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
