"""Goldsky data provider.

Goldsky Turbo Pipelines (https://docs.goldsky.com/turbo-pipelines/sources/solana)
stream curated Solana datasets into a database sink rather than exposing a hosted
query API. This provider queries a ClickHouse sink populated by a Turbo pipeline
from two datasets:

- ``solana.dex_swaps``               -> ``community.solana_dex_swaps``
- ``solana.stable_coin_transfers``   -> ``community.solana_stable_coin_transfers``

``block_timestamp`` is a Unix timestamp in seconds on both tables, so the daily bucket
is derived as ``toDate(toDateTime(block_timestamp))``. Every metric counts only live,
successful rows (``is_deleted = 0 AND status = 1``): ``is_deleted`` is a CDC
soft-delete marker, and ``status = 0`` rows are failed transactions, which other
providers exclude too. On the stablecoin table ``status`` was verified against the
``err`` column -- they agree on every row.

The stablecoin table carries several pegs (``asset_id`` of ``usd``, ``eur``, ``vchf``,
...) and holds no price data, so the two USD-denominated metrics are scoped to
``asset_id = 'usd'`` and assume a 1:1 peg. Counts that are not currency-denominated
span every curated stablecoin.

Queries run over the ClickHouse HTTP interface, configured via:

- ``GOLDSKY_CLICKHOUSE_URL``      (required, e.g. ``https://host:8443``)
- ``GOLDSKY_CLICKHOUSE_USER``     (default ``default``)
- ``GOLDSKY_CLICKHOUSE_PASSWORD`` (default empty)
- ``GOLDSKY_CLICKHOUSE_DATABASE`` (default ``community``)
"""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional

import requests

from metrics.defi import Defi, DefiMetricType
from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.base import BaseProvider

DEX_TRADES_DOCS_URL = (
    "https://docs.goldsky.com/turbo-pipelines/sources/solana-dex-trades"
)
STABLECOIN_DOCS_URL = (
    "https://docs.goldsky.com/turbo-pipelines/sources/solana-stablecoin-transfers"
)


class Goldsky(BaseProvider):
    """Fetch Solana metrics from a ClickHouse sink fed by Goldsky Turbo Pipelines."""

    METRIC_MAP: Dict[str, Dict[str, str]] = {
        "defi_dex_transactions": {
            "table": "dex_swaps",
            "date_field": "block_date",
            "value_field": "transaction_count",
            "methodology": "Number of distinct transactions containing a successful DEX swap per day, from Goldsky's normalized solana.dex_swaps dataset. Failed swap attempts are excluded.",
            "methodology_url": DEX_TRADES_DOCS_URL,
            "sql": """
                SELECT
                    toDate(toDateTime(block_timestamp)) AS block_date,
                    count(DISTINCT tx_id) AS transaction_count
                FROM {table}
                WHERE toDate(toDateTime(block_timestamp)) BETWEEN toDate('{start_date}') AND toDate('{end_date}')
                  AND is_deleted = 0
                  AND status = 1
                GROUP BY block_date
                ORDER BY block_date ASC
            """,
        },
        "defi_dex_traders": {
            "table": "dex_swaps",
            "date_field": "block_date",
            "value_field": "unique_traders",
            "methodology": "Number of unique trader accounts with a successful swap per day in Goldsky's solana.dex_swaps dataset. For router-mediated swaps the trader is the payer/owner on the swap instruction. Failed swap attempts are excluded.",
            "methodology_url": DEX_TRADES_DOCS_URL,
            "sql": """
                SELECT
                    toDate(toDateTime(block_timestamp)) AS block_date,
                    count(DISTINCT trader_id) AS unique_traders
                FROM {table}
                WHERE toDate(toDateTime(block_timestamp)) BETWEEN toDate('{start_date}') AND toDate('{end_date}')
                  AND is_deleted = 0
                  AND status = 1
                GROUP BY block_date
                ORDER BY block_date ASC
            """,
        },
        "defi_dex_count": {
            "table": "dex_swaps",
            "date_field": "block_date",
            "value_field": "unique_dex_count",
            "methodology": "Number of unique DEX projects with at least one successful swap per day, from Goldsky's solana.dex_swaps dataset. Failed swap attempts, and swaps whose project could not be attributed (null project), are excluded.",
            "methodology_url": DEX_TRADES_DOCS_URL,
            "sql": """
                SELECT
                    toDate(toDateTime(block_timestamp)) AS block_date,
                    count(DISTINCT project) AS unique_dex_count
                FROM {table}
                WHERE toDate(toDateTime(block_timestamp)) BETWEEN toDate('{start_date}') AND toDate('{end_date}')
                  AND is_deleted = 0
                  AND status = 1
                  AND project IS NOT NULL
                GROUP BY block_date
                ORDER BY block_date ASC
            """,
        },
        "stablecoin_transfer_count": {
            "table": "stable_coin_transfers",
            "date_field": "block_date",
            "value_field": "transfer_count",
            "methodology": "Number of stablecoin transfer instructions per day, across all curated stablecoins in Goldsky's solana.stable_coin_transfers dataset. Counts individual transfers, not transactions, so a transaction carrying several transfers contributes each one (~2 per transaction on average). Mints and burns are not transfers and are excluded, as are failed transactions.",
            "methodology_url": STABLECOIN_DOCS_URL,
            "sql": """
                SELECT
                    toDate(toDateTime(block_timestamp)) AS block_date,
                    count() AS transfer_count
                FROM {table}
                WHERE toDate(toDateTime(block_timestamp)) BETWEEN toDate('{start_date}') AND toDate('{end_date}')
                  AND is_deleted = 0
                  AND status = 1
                  AND transfer_type NOT IN ('MintTo', 'MintToChecked', 'Burn', 'BurnChecked')
                GROUP BY block_date
                ORDER BY block_date ASC
            """,
        },
        "stablecoin_transfer_volume": {
            "table": "stable_coin_transfers",
            "date_field": "block_date",
            "value_field": "transfer_volume",
            "methodology": "Daily transfer volume of USD-pegged stablecoins in Goldsky's solana.stable_coin_transfers dataset, summed over mint-decimal-normalized amounts. The dataset carries no prices, so each token is valued at its 1:1 peg and non-USD pegs (eur, vchf, ...) are excluded. Mints, burns, and failed transactions are excluded.",
            "methodology_url": STABLECOIN_DOCS_URL,
            "sql": """
                SELECT
                    toDate(toDateTime(block_timestamp)) AS block_date,
                    sum(amount_normalized) AS transfer_volume
                FROM {table}
                WHERE toDate(toDateTime(block_timestamp)) BETWEEN toDate('{start_date}') AND toDate('{end_date}')
                  AND is_deleted = 0
                  AND status = 1
                  AND asset_id = 'usd'
                  AND transfer_type NOT IN ('MintTo', 'MintToChecked', 'Burn', 'BurnChecked')
                GROUP BY block_date
                ORDER BY block_date ASC
            """,
        },
        "stablecoin_active_addresses": {
            "table": "stable_coin_transfers",
            "date_field": "block_date",
            "value_field": "active_addresses",
            "methodology": "Number of unique wallets on either side of a stablecoin transfer per day, across all curated stablecoins in Goldsky's solana.stable_coin_transfers dataset. Sender and recipient owners are pooled, so a wallet that both sends and receives counts once. Mints and burns are included as interactions; failed transactions are excluded.",
            "methodology_url": STABLECOIN_DOCS_URL,
            "sql": """
                SELECT
                    toDate(toDateTime(block_timestamp)) AS block_date,
                    count(DISTINCT owner) AS active_addresses
                FROM {table}
                ARRAY JOIN [from_owner, to_owner] AS owner
                WHERE toDate(toDateTime(block_timestamp)) BETWEEN toDate('{start_date}') AND toDate('{end_date}')
                  AND is_deleted = 0
                  AND status = 1
                  AND owner IS NOT NULL
                GROUP BY block_date
                ORDER BY block_date ASC
            """,
        },
        "stablecoin_count": {
            "table": "stable_coin_transfers",
            "date_field": "block_date",
            "value_field": "stablecoin_count",
            "methodology": "Number of distinct USD-pegged stablecoin mints with at least one transfer per day in Goldsky's solana.stable_coin_transfers dataset, counted by asset-registry variant id. This is stablecoins seen in activity, not the number in existence. Failed transactions are excluded.",
            "methodology_url": STABLECOIN_DOCS_URL,
            "sql": """
                SELECT
                    toDate(toDateTime(block_timestamp)) AS block_date,
                    count(DISTINCT variant_id) AS stablecoin_count
                FROM {table}
                WHERE toDate(toDateTime(block_timestamp)) BETWEEN toDate('{start_date}') AND toDate('{end_date}')
                  AND is_deleted = 0
                  AND status = 1
                  AND asset_id = 'usd'
                GROUP BY block_date
                ORDER BY block_date ASC
            """,
        },
    }

    DEFAULT_DATABASE = "community"

    DEFAULT_TABLES: Dict[str, str] = {
        "dex_swaps": "solana_dex_swaps",
        "stable_coin_transfers": "solana_stable_coin_transfers",
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
            database
            or os.environ.get("GOLDSKY_CLICKHOUSE_DATABASE")
            or self.DEFAULT_DATABASE
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

    def get_metric(
        self, metric: str, date: str, chain: str
    ) -> Defi | Stablecoin | None:
        """Fetch one metric value and return it as a typed metric model."""
        rows = self.fetch_rows(metric, date, date)
        if not rows:
            return None

        value = rows[0]["value"]
        parsed_date = datetime.date.fromisoformat(date)

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

        stablecoin_metric_map = {
            "stablecoin_transfer_count": StablecoinMetricType.TRANSFER_COUNT,
            "stablecoin_transfer_volume": StablecoinMetricType.TRANSFER_VOLUME,
            "stablecoin_active_addresses": StablecoinMetricType.ACTIVE_ADDRESSES,
            "stablecoin_count": StablecoinMetricType.COUNT,
        }
        if metric in stablecoin_metric_map:
            return Stablecoin.from_metric_type(
                metric_type=stablecoin_metric_map[metric],
                date=parsed_date,
                value=value,
            )

        return None
