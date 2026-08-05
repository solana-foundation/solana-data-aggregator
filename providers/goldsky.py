"""Goldsky data provider.

Goldsky Turbo Pipelines (https://docs.goldsky.com/turbo-pipelines/sources/solana)
stream curated Solana datasets into a database sink rather than exposing a hosted
query API. This provider queries a ClickHouse sink populated by a Turbo pipeline
from the following datasets:

- ``solana.blocks``     -> ``solana_blocks`` table
- ``solana.transactions`` -> ``solana_transactions`` table
- ``solana.dex_swaps``  -> ``solana_dex_swaps`` table

Queries run over the ClickHouse HTTP interface, configured via:

- ``GOLDSKY_CLICKHOUSE_URL``      (required, e.g. ``https://host:8443``)
- ``GOLDSKY_CLICKHOUSE_USER``     (default ``default``)
- ``GOLDSKY_CLICKHOUSE_PASSWORD`` (default empty)
- ``GOLDSKY_CLICKHOUSE_DATABASE`` (default ``default``)
"""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional

import requests

from metrics.defi import Defi, DefiMetricType
from metrics.overview import Overview, OverviewMetricType
from providers.base import BaseProvider

SOLANA_DOCS_URL = "https://docs.goldsky.com/turbo-pipelines/sources/solana"
DEX_TRADES_DOCS_URL = (
    "https://docs.goldsky.com/turbo-pipelines/sources/solana-dex-trades"
)


class Goldsky(BaseProvider):
    """Fetch Solana metrics from a ClickHouse sink fed by Goldsky Turbo Pipelines."""

    METRIC_MAP: Dict[str, Dict[str, str]] = {
        "overview_slots": {
            "table": "blocks",
            "date_field": "block_date",
            "value_field": "slots",
            "methodology": "Number of block-producing slots per day, counted from Goldsky's solana.blocks dataset (skipped slots excluded).",
            "methodology_url": SOLANA_DOCS_URL,
            "sql": """
                SELECT
                    toDate(timestamp) AS block_date,
                    count() AS slots
                FROM {table}
                WHERE NOT skipped
                  AND toDate(timestamp) BETWEEN toDate('{start_date}') AND toDate('{end_date}')
                GROUP BY block_date
                ORDER BY block_date ASC
            """,
        },
        "overview_tx_count_total": {
            "table": "blocks",
            "date_field": "block_date",
            "value_field": "total_txns",
            "methodology": "Total transactions per day (vote and non-vote), summed from per-block transaction counts in Goldsky's solana.blocks dataset.",
            "methodology_url": SOLANA_DOCS_URL,
            "sql": """
                SELECT
                    toDate(timestamp) AS block_date,
                    sum(transaction_count) AS total_txns
                FROM {table}
                WHERE toDate(timestamp) BETWEEN toDate('{start_date}') AND toDate('{end_date}')
                GROUP BY block_date
                ORDER BY block_date ASC
            """,
        },
        "overview_fees": {
            "table": "transactions",
            "date_field": "block_date",
            "value_field": "fee_sol",
            "methodology": "Daily sum of transaction fees (base plus priority) in SOL across all transactions in Goldsky's solana.transactions dataset.",
            "methodology_url": SOLANA_DOCS_URL,
            "sql": """
                SELECT
                    toDate(block_timestamp) AS block_date,
                    sum(fee) / 1e9 AS fee_sol
                FROM {table}
                WHERE toDate(block_timestamp) BETWEEN toDate('{start_date}') AND toDate('{end_date}')
                GROUP BY block_date
                ORDER BY block_date ASC
            """,
        },
        "overview_compute_units": {
            "table": "transactions",
            "date_field": "block_date",
            "value_field": "avg_compute_units_per_block",
            "methodology": "Average compute units consumed per block daily, from Goldsky's solana.transactions dataset.",
            "methodology_url": SOLANA_DOCS_URL,
            "sql": """
                SELECT
                    toDate(block_timestamp) AS block_date,
                    sum(compute_units_consumed) / count(DISTINCT block_slot) AS avg_compute_units_per_block
                FROM {table}
                WHERE toDate(block_timestamp) BETWEEN toDate('{start_date}') AND toDate('{end_date}')
                GROUP BY block_date
                ORDER BY block_date ASC
            """,
        },
        "defi_dex_transactions": {
            "table": "dex_swaps",
            "date_field": "block_date",
            "value_field": "transaction_count",
            "methodology": "Number of distinct transactions containing a DEX swap per day, from Goldsky's normalized solana.dex_swaps dataset.",
            "methodology_url": DEX_TRADES_DOCS_URL,
            "sql": """
                SELECT
                    toDate(toDateTime(block_timestamp)) AS block_date,
                    count(DISTINCT tx_id) AS transaction_count
                FROM {table}
                WHERE toDate(toDateTime(block_timestamp)) BETWEEN toDate('{start_date}') AND toDate('{end_date}')
                GROUP BY block_date
                ORDER BY block_date ASC
            """,
        },
        "defi_dex_traders": {
            "table": "dex_swaps",
            "date_field": "block_date",
            "value_field": "unique_traders",
            "methodology": "Number of unique trader accounts per day in Goldsky's solana.dex_swaps dataset. For router-mediated swaps the trader is the payer/owner on the swap instruction.",
            "methodology_url": DEX_TRADES_DOCS_URL,
            "sql": """
                SELECT
                    toDate(toDateTime(block_timestamp)) AS block_date,
                    count(DISTINCT trader_id) AS unique_traders
                FROM {table}
                WHERE toDate(toDateTime(block_timestamp)) BETWEEN toDate('{start_date}') AND toDate('{end_date}')
                GROUP BY block_date
                ORDER BY block_date ASC
            """,
        },
        "defi_dex_count": {
            "table": "dex_swaps",
            "date_field": "block_date",
            "value_field": "unique_dex_count",
            "methodology": "Number of unique DEX projects with at least one swap per day, from Goldsky's solana.dex_swaps dataset.",
            "methodology_url": DEX_TRADES_DOCS_URL,
            "sql": """
                SELECT
                    toDate(toDateTime(block_timestamp)) AS block_date,
                    count(DISTINCT project) AS unique_dex_count
                FROM {table}
                WHERE toDate(toDateTime(block_timestamp)) BETWEEN toDate('{start_date}') AND toDate('{end_date}')
                GROUP BY block_date
                ORDER BY block_date ASC
            """,
        },
    }

    DEFAULT_TABLES: Dict[str, str] = {
        "blocks": "solana_blocks",
        "transactions": "solana_transactions",
        "dex_swaps": "solana_dex_swaps",
    }

    def __init__(
        self,
        *,
        url: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
        tables: Optional[Dict[str, str]] = None,
    ) -> None:
        resolved_url = url or os.environ.get("GOLDSKY_CLICKHOUSE_URL") or ""
        if not resolved_url:
            raise ValueError("GOLDSKY_CLICKHOUSE_URL is required")

        self._user = user or os.environ.get("GOLDSKY_CLICKHOUSE_USER") or "default"
        resolved_password = (
            password or os.environ.get("GOLDSKY_CLICKHOUSE_PASSWORD") or ""
        )
        self._database = (
            database or os.environ.get("GOLDSKY_CLICKHOUSE_DATABASE") or "default"
        )
        self._tables = {**self.DEFAULT_TABLES, **(tables or {})}

        super().__init__(
            name="Goldsky",
            base_url=resolved_url.rstrip("/"),
            api_key=resolved_password,
        )
        self._session = requests.Session()

    # -- private helpers ----------------------------------------------------

    @staticmethod
    def _validate_date(date_str: str) -> str:
        """Parse a YYYY-MM-DD string so only well-formed dates reach the SQL."""
        return datetime.date.fromisoformat(date_str).isoformat()

    def _run_sql(self, sql: str) -> List[Dict[str, Any]]:
        """Execute SQL over the ClickHouse HTTP interface and return rows."""
        headers = {
            "X-ClickHouse-User": self._user,
            "X-ClickHouse-Key": self.api_key,
        }
        resp = self._session.post(
            f"{self.base_url}/",
            params={"database": self._database},
            data=f"{sql}\nFORMAT JSON",
            headers=headers,
            timeout=300,
        )
        resp.raise_for_status()
        return resp.json().get("data", [])

    # -- BaseProvider interface ---------------------------------------------

    def fetch_rows(
        self, metric: str, start_date: str, end_date: str, **kwargs: Any
    ) -> List[Dict[str, Any]]:
        """Return normalized {"date": str, "value": Any} records for the given range (both dates inclusive)."""
        config = self.METRIC_MAP.get(metric)
        if config is None:
            available = ", ".join(self.METRIC_MAP)
            raise ValueError(f"Unknown metric '{metric}'. Available: {available}")

        sql = config["sql"].format(
            table=self._tables[config["table"]],
            start_date=self._validate_date(start_date),
            end_date=self._validate_date(end_date),
        )
        result = []
        for row in self._run_sql(sql):
            row_date = str(row.get(config["date_field"], ""))[:10]
            if not row_date:
                continue
            value = row.get(config["value_field"])
            if value is None:
                continue
            # ClickHouse JSON output quotes 64-bit integers as strings.
            result.append({"date": row_date, "value": float(value)})
        return result

    def get_metric(self, metric: str, date: str, chain: str) -> Overview | Defi | None:
        """Fetch one metric value and return it as a typed metric model."""
        rows = self.fetch_rows(metric, date, date)
        if not rows:
            return None

        value = rows[0]["value"]
        parsed_date = datetime.date.fromisoformat(date)

        overview_metric_map = {
            "overview_slots": OverviewMetricType.SLOTS,
            "overview_tx_count_total": OverviewMetricType.TX_COUNT_TOTAL,
            "overview_fees": OverviewMetricType.FEES,
            "overview_compute_units": OverviewMetricType.COMPUTE_UNITS,
        }
        if metric in overview_metric_map:
            return Overview.from_metric_type(
                metric_type=overview_metric_map[metric],
                date=parsed_date,
                value=value,
            )

        defi_metric_map = {
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

        return None
