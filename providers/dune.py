"""Dune Analytics data provider."""

from __future__ import annotations

import datetime
import os
import time
from typing import Any, Dict, List, Optional

import requests

from metrics.defi import Defi, DefiMetricType
from metrics.overview import Overview, OverviewMetricType
from metrics.prediction_market import PredictionMarket, PredictionMarketMetricType
from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.base import BaseProvider

# Solana prediction market programs counted by the prediction market metrics.
# IDs come from each protocol's DefiLlama TVL adapter
# (github.com/DefiLlama/DefiLlama-Adapters) or volume adapter
# (github.com/DefiLlama/dimension-adapters), except Trepa, which DefiLlama
# does not list: its mainnet program is verified from the pool accounts its
# public API reports. Pascal matches trades off-chain, and PRDT and DropCopy
# publish no program IDs, so none of them are counted here.
PREDICTION_MARKET_PROGRAMS: Dict[str, List[str]] = {
    "world.xyz": ["prediCtPZCttYMvm2W3PtxmMxLmT1dtN7riU6Cxh6tM"],
    "Hedgehog Markets": [
        "D8vMVKonxkbBtAXAxBwPPWyTfon8337ARJmHvwtsF98G",
        "P2PototC41acvjMc9cvAoRjFjtaRD5Keo9PvNJfRwf3",
        "P2PzLraW8YF87BxqZTZ5kgrfvzcrKGPnqUBNhqmcV9B",
        "PLYaNRbQs9GWyVQdcLrzPvvZu7NH4W2sneyHcEimLr7",
        "PARrVs6F5egaNuz8g6pKJyU4ze3eX5xGZCFb3GLiVvu",
    ],
    "Divvy.Bet": ["dvyFwAPniptQNb1ey4eM12L8iLHrzdiDsPPDndd6xAR"],
    "Bubblegum": ["71ywu6cFWETLyiz1KcuMwq2wfguYfra7b1bCPinVqKm3"],
    "Rush Sports": ["CAzPCZuaji4ycz4KWtmBirvNeXp3ULCqunJgSMFZX5ar"],
    "Prophet.fun": ["ProPh6ruVL41JR3XXPuy6hN6TPH1ERqpWkZ9dp9YSEe"],
    # Trepa shut down on 2026-08-12 and runs no rounds after that date. It is
    # kept here so backfills of earlier days stay complete; from 2026-08-13 its
    # program has no activity, so it contributes nothing to any of the metrics.
    "Trepa": ["TrP8DegtRkKAyoUuD9ZzrSWdYvx829ZgXkxK21rvm6v"],
    "Worm": [
        "WrgN8d3Xe7qTzZw59kiXaf3fAagHHWg78Mbhkn2dTPD",
        "SormXyTMQ69ux8yhn9CBQ8v7UuqepefMHbM5TcNDtkf",
    ],
}

# Protocols that sponsor gas for their users. Every transaction is signed by a
# relayer wallet, so counting signers reports a handful of wallets instead of
# the user base. Users are counted from stake token transfer owners instead.
# Trepa is listed for the days it ran; see the note on its program ID above.
PREDICTION_MARKET_RELAYER_PROTOCOLS = {"Trepa", "Worm"}

# Assets users stake on the protocols above: USDC, USDT, wSOL and world.xyz's
# CASH. Native SOL is excluded because its transfers also cover account
# creation and rent, which would count wallets that never placed a prediction.
PREDICTION_MARKET_STAKE_TOKENS = [
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "So11111111111111111111111111111111111111112",
    "CASHx9KJUStyftLFWGvEVf59SGeG9sh5FfcnZMVPCASH",
]


# Volume decoders, one per protocol, because each program records stake sizes
# in its own instruction layout. Protocols without a decoder contribute no
# volume: Divvy.Bet's on-chain IDL no longer matches its deployed program, and
# the rest either publish no IDL or have had no on-chain activity to measure.
PREDICTION_MARKET_VOLUME_DECODERS = {
    # world.xyz routes trades through the DFlow aggregator, which emits an
    # Anchor swap event carrying the CASH leg of the trade. Same decode as
    # DefiLlama's world.xyz adapter, and it reproduces their published volume.
    "world.xyz": """
                    SELECT
                        ic.block_date,
                        CASE
                            WHEN bytearray_substring(ic.data, 49, 32) = from_base58('CASHx9KJUStyftLFWGvEVf59SGeG9sh5FfcnZMVPCASH')
                                THEN CAST(bytearray_to_uint256(bytearray_reverse(bytearray_substring(ic.data, 81, 8))) AS DOUBLE) / 1e6
                            WHEN bytearray_substring(ic.data, 89, 32) = from_base58('CASHx9KJUStyftLFWGvEVf59SGeG9sh5FfcnZMVPCASH')
                                THEN CAST(bytearray_to_uint256(bytearray_reverse(bytearray_substring(ic.data, 121, 8))) AS DOUBLE) / 1e6
                            ELSE 0
                        END AS volume_usd
                    FROM solana.instruction_calls ic
                    JOIN (
                        SELECT DISTINCT tx_id
                        FROM solana.instruction_calls
                        WHERE executing_account = 'prediCtPZCttYMvm2W3PtxmMxLmT1dtN7riU6Cxh6tM'
                          AND tx_success
                          AND block_date BETWEEN DATE '{start_date}' AND DATE '{end_date}'
                    ) w ON w.tx_id = ic.tx_id
                    WHERE ic.executing_account = 'DF1ow4tspfHX9JwWJsAb9epbkA8hmpSEAtxXy1V27QBH'
                      AND ic.tx_success
                      AND ic.block_date BETWEEN DATE '{start_date}' AND DATE '{end_date}'
                      AND bytearray_substring(ic.data, 1, 8) = 0xe445a52e51cb9a1d
                      AND bytearray_substring(ic.data, 9, 8) = 0x40c6cde8260871e2""",
    # Trepa's predict instruction carries the USDC stake as a little-endian
    # u64 immediately after the 8 byte Anchor discriminator. Retained for
    # backfills of days before its 2026-08-12 shutdown.
    "Trepa": """
                    SELECT
                        block_date,
                        CAST(bytearray_to_uint256(bytearray_reverse(bytearray_substring(data, 9, 8))) AS DOUBLE) / 1e6 AS volume_usd
                    FROM solana.instruction_calls
                    WHERE executing_account = 'TrP8DegtRkKAyoUuD9ZzrSWdYvx829ZgXkxK21rvm6v'
                      AND tx_success
                      AND block_date BETWEEN DATE '{start_date}' AND DATE '{end_date}'
                      AND bytearray_substring(data, 1, 8) = 0xFE7270F425312080""",
    # Worm records the collateral staked on a position: at byte 17 for its
    # main program (which also carries leverage at byte 9) and at byte 9 for
    # its creator-markets program. Same decode as DefiLlama's Worm adapter.
    "Worm": """
                    SELECT
                        block_date,
                        CASE
                            WHEN executing_account = 'SormXyTMQ69ux8yhn9CBQ8v7UuqepefMHbM5TcNDtkf'
                                THEN CAST(bytearray_to_uint256(bytearray_reverse(bytearray_substring(data, 9, 8))) AS DOUBLE) / 1e6
                            ELSE CAST(bytearray_to_uint256(bytearray_reverse(bytearray_substring(data, 17, 8))) AS DOUBLE) / 1e6
                        END AS volume_usd
                    FROM solana.instruction_calls
                    WHERE tx_success
                      AND block_date BETWEEN DATE '{start_date}' AND DATE '{end_date}'
                      AND (
                        (
                            executing_account = 'WrgN8d3Xe7qTzZw59kiXaf3fAagHHWg78Mbhkn2dTPD'
                            AND length(data) = 25
                            AND bytearray_substring(data, 1, 8) = 0x87802f4d0f98f031
                            AND bytearray_to_uint256(bytearray_reverse(bytearray_substring(data, 9, 8))) BETWEEN 100 AND 1000
                        )
                        OR (
                            executing_account = 'SormXyTMQ69ux8yhn9CBQ8v7UuqepefMHbM5TcNDtkf'
                            AND length(data) = 16
                            AND bytearray_substring(data, 1, 8) = 0x33c29baf6d82606a
                        )
                      )""",
}


def _sql_list(values, indent: int = 20) -> str:
    """Render values as a quoted, indented SQL IN-list."""
    separator = ",\n" + " " * indent
    return separator.join(f"'{value}'" for value in values)


def _join_names(names) -> str:
    """Join names for prose: 'A', 'A and B', 'A, B and C'."""
    names = list(names)
    if len(names) < 3:
        return " and ".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def _program_ids(protocols) -> List[str]:
    return [
        program_id
        for protocol in protocols
        for program_id in PREDICTION_MARKET_PROGRAMS[protocol]
    ]


_SIGNER_PROTOCOLS = [
    protocol
    for protocol in PREDICTION_MARKET_PROGRAMS
    if protocol not in PREDICTION_MARKET_RELAYER_PROTOCOLS
]
_RELAYER_PROTOCOLS = [
    protocol
    for protocol in PREDICTION_MARKET_PROGRAMS
    if protocol in PREDICTION_MARKET_RELAYER_PROTOCOLS
]

_PREDICTION_MARKET_PROGRAM_IDS = _sql_list(
    _program_ids(PREDICTION_MARKET_PROGRAMS), indent=20
)
_SIGNER_PROGRAM_IDS = _sql_list(_program_ids(_SIGNER_PROTOCOLS), indent=24)
_RELAYER_PROGRAM_IDS = _sql_list(_program_ids(_RELAYER_PROTOCOLS), indent=28)
_STAKE_TOKEN_IDS = _sql_list(PREDICTION_MARKET_STAKE_TOKENS, indent=24)

_PROTOCOL_CASE_SQL = "\n".join(
    f"                            WHEN executing_account IN ({_sql_list(ids, 32)}) THEN '{protocol}'"
    for protocol, ids in PREDICTION_MARKET_PROGRAMS.items()
)

_PREDICTION_MARKET_PROTOCOLS = ", ".join(PREDICTION_MARKET_PROGRAMS)
_PREDICTION_MARKET_RELAYERS = _join_names(_RELAYER_PROTOCOLS)
_VOLUME_PROTOCOLS = ", ".join(PREDICTION_MARKET_VOLUME_DECODERS)
_VOLUME_DECODER_SQL = "\n\n                    UNION ALL\n".join(
    PREDICTION_MARKET_VOLUME_DECODERS.values()
)


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
        "prediction_market_transactions": {
            "date_field": "block_date",
            "value_field": "pm_transactions",
            "timeout": 3600,
            "methodology": f"Distinct successful transactions calling Solana prediction market programs ({_PREDICTION_MARKET_PROTOCOLS}).",
            "sql": f"""
                SELECT
                    block_date,
                    COUNT(DISTINCT tx_id) AS pm_transactions
                FROM solana.instruction_calls
                WHERE executing_account IN (
                    {_PREDICTION_MARKET_PROGRAM_IDS}
                )
                  AND tx_success
                  AND block_date BETWEEN DATE '{{start_date}}' AND DATE '{{end_date}}'
                GROUP BY block_date
                ORDER BY block_date ASC
            """,
        },
        "prediction_market_count": {
            "date_field": "block_date",
            "value_field": "pm_count",
            "timeout": 3600,
            "methodology": f"Solana prediction market protocols with on-chain activity on the day ({_PREDICTION_MARKET_PROTOCOLS}). Protocols holding collateral but processing no transactions are not counted.",
            "sql": f"""
                SELECT
                    block_date,
                    COUNT(DISTINCT protocol) AS pm_count
                FROM (
                    SELECT
                        block_date,
                        CASE
{_PROTOCOL_CASE_SQL}
                        END AS protocol
                    FROM solana.instruction_calls
                    WHERE executing_account IN (
                            {_PREDICTION_MARKET_PROGRAM_IDS}
                        )
                      AND tx_success
                      AND block_date BETWEEN DATE '{{start_date}}' AND DATE '{{end_date}}'
                ) protocols
                GROUP BY block_date
                ORDER BY block_date ASC
            """,
        },
        "prediction_market_volume": {
            "date_field": "block_date",
            "value_field": "pm_volume_usd",
            "timeout": 3600,
            "methodology": f"Trade size decoded from the on-chain instruction data of each Solana prediction market program with a known layout ({_VOLUME_PROTOCOLS}). Protocols whose layout is not published are not counted.",
            "sql": f"""
                SELECT
                    block_date,
                    SUM(volume_usd) AS pm_volume_usd
                FROM (
{_VOLUME_DECODER_SQL}
                ) trades
                GROUP BY block_date
                ORDER BY block_date ASC
            """,
        },
        "prediction_market_users": {
            "date_field": "block_date",
            "value_field": "pm_users",
            "timeout": 3600,
            "methodology": f"Unique wallets using Solana prediction market programs ({_PREDICTION_MARKET_PROTOCOLS}), counted as transaction signers. On {_PREDICTION_MARKET_RELAYERS}, which sponsor gas and sign through relayer wallets, wallets are counted as the owners of the stake tokens moved instead.",
            "sql": f"""
                SELECT
                    block_date,
                    COUNT(DISTINCT wallet) AS pm_users
                FROM (
                    SELECT block_date, tx_signer AS wallet
                    FROM solana.instruction_calls
                    WHERE executing_account IN (
                            {_SIGNER_PROGRAM_IDS}
                        )
                      AND tx_success
                      AND block_date BETWEEN DATE '{{start_date}}' AND DATE '{{end_date}}'

                    UNION

                    SELECT t.block_date, t.from_owner AS wallet
                    FROM tokens_solana.transfers t
                    JOIN (
                        SELECT DISTINCT tx_id
                        FROM solana.instruction_calls
                        WHERE executing_account IN (
                                {_RELAYER_PROGRAM_IDS}
                            )
                          AND tx_success
                          AND block_date BETWEEN DATE '{{start_date}}' AND DATE '{{end_date}}'
                    ) r ON t.tx_id = r.tx_id
                    WHERE t.block_date BETWEEN DATE '{{start_date}}' AND DATE '{{end_date}}'
                      AND t.from_owner IS NOT NULL
                      AND t.token_mint_address IN (
                            {_STAKE_TOKEN_IDS}
                        )
                ) wallets
                GROUP BY block_date
                ORDER BY block_date ASC
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
    ) -> Stablecoin | Overview | Defi | PredictionMarket | None:
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

        prediction_market_metric_map = {
            "prediction_market_transactions": PredictionMarketMetricType.TRANSACTIONS,
            "prediction_market_count": PredictionMarketMetricType.COUNT,
            "prediction_market_volume": PredictionMarketMetricType.VOLUME,
            "prediction_market_users": PredictionMarketMetricType.USERS,
        }
        if metric in prediction_market_metric_map:
            return PredictionMarket.from_metric_type(
                metric_type=prediction_market_metric_map[metric],
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
