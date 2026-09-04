"""Bitquery data provider.

Bitquery (https://bitquery.io) exposes curated multi-chain DEX trading data
through its Trading APIs — a single GraphQL endpoint backed by the swap-level
``Trading.Trades`` cube and the pre-aggregated Price Index cubes
(``Trading.Tokens`` / ``Trading.Pairs``). Rows are MEV/outlier-filtered and
carry USD values derived by the Bitquery Price Index.

All metrics are fetched with one grouped GraphQL query per date range
(daily buckets via ``Block { Date }``), so a backfill of N days costs one
HTTP request per metric, not N.

The Trading cubes retain a rolling ~30-day window; requested days outside
that window are simply absent from the response.

Configuration:

- ``BITQUERY_API_KEY`` (required) — an access token generated at
  https://account.bitquery.io/user/api_v2/access_tokens, sent as a Bearer token.
"""

from __future__ import annotations

import datetime
import math
import os
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from metrics.defi import Defi, DefiMetricType
from metrics.overview import Overview, OverviewMetricType
from providers.base import BaseProvider

TRADES_DOCS_URL = "https://docs.bitquery.io/docs/trading/crypto-trades-api/trades-api/"
PAIRS_DOCS_URL = "https://docs.bitquery.io/docs/trading/crypto-price-api/pairs/"
TOKENS_DOCS_URL = "https://docs.bitquery.io/docs/trading/crypto-price-api/tokens/"

# Wrapped SOL mint; the Price Index prices native SOL via the wSOL token.
_WSOL_MINT = "So11111111111111111111111111111111111111112"

_TRADES_QUERY = """
{{ Trading {{ Trades(
    where: {{
      Block: {{Time: {{since: "{since}", till: "{till}"}}}},
      Pair: {{Market: {{NetworkBid: {{is: "bid:solana"}}}}}}
    }}
    orderBy: {{ascending: Block_Date}}
  ) {{ Block {{ Date }} value: {aggregate} }} }} }}
"""

_PAIRS_VOLUME_QUERY = """
{{ Trading {{ Pairs(
    where: {{
      Market: {{NetworkBid: {{is: "bid:solana"}}}},
      Interval: {{Time: {{Duration: {{eq: 3600}}}}}},
      Block: {{Time: {{since: "{since}", till: "{till}"}}}}
    }}
    orderBy: {{ascending: Block_Date}}
  ) {{ Block {{ Date }} value: sum(of: Volume_Usd) }} }} }}
"""

_TOKENS_PRICE_QUERY = """
{{ Trading {{ Tokens(
    where: {{
      Token: {{NetworkBid: {{is: "bid:solana"}}, Address: {{is: "{mint}"}}}},
      Interval: {{Time: {{Duration: {{eq: 3600}}}}}},
      Block: {{Time: {{since: "{since}", till: "{till}"}}}}
    }}
    orderBy: {{ascending: Block_Date}}
  ) {{ Block {{ Date }} value: average(of: Price_Average_Mean) }} }} }}
"""


class Bitquery(BaseProvider):
    """Fetch Solana DEX and price metrics from the Bitquery Trading APIs."""

    BASE_URL = "https://streaming.bitquery.io/graphql"

    # (connect, read) timeouts; requests has no default and would otherwise hang.
    _TIMEOUT = (5, 60)

    METRIC_MAP: Dict[str, Dict[str, Any]] = {
        "defi_dex_volume": {
            "cube": "Pairs",
            "query": _PAIRS_VOLUME_QUERY,
            "cast": float,
            "methodology": (
                "Daily USD volume summed across all DEX trading pairs indexed on "
                "Solana, from the pre-aggregated Trading.Pairs cube. Covers every "
                "indexed swap; MEV and outlier trades are filtered by the Bitquery "
                "Price Index before aggregation."
            ),
            "methodology_url": PAIRS_DOCS_URL,
        },
        "defi_dex_transactions": {
            "cube": "Trades",
            "query": _TRADES_QUERY,
            "aggregate": "count",
            "cast": int,
            "methodology": (
                "Number of DEX swaps per day on Solana from the Trading.Trades "
                "cube (one row per swap, MEV/outlier-filtered)."
            ),
            "methodology_url": TRADES_DOCS_URL,
        },
        "defi_dex_traders": {
            "cube": "Trades",
            "query": _TRADES_QUERY,
            "aggregate": "count(distinct: Trader_Address)",
            "cast": int,
            "methodology": (
                "Number of unique trader wallet addresses executing at least one "
                "DEX swap per day on Solana, from the Trading.Trades cube."
            ),
            "methodology_url": TRADES_DOCS_URL,
        },
        "defi_dex_count": {
            "cube": "Trades",
            "query": _TRADES_QUERY,
            "aggregate": "count(distinct: Pair_Market_Program)",
            "cast": int,
            "methodology": (
                "Number of distinct DEX programs with at least one swap per day "
                "on Solana, from the Trading.Trades cube."
            ),
            "methodology_url": TRADES_DOCS_URL,
        },
        "overview_sol_price": {
            "cube": "Tokens",
            "query": _TOKENS_PRICE_QUERY,
            "cast": float,
            "methodology": (
                "Daily average SOL/USD price: hourly Bitquery Price Index "
                "intervals for wrapped SOL on Solana (volume-weighted across "
                "DEX pools, outlier-filtered) averaged per day."
            ),
            "methodology_url": TOKENS_DOCS_URL,
        },
    }

    _DEFI_METRIC_TYPE_MAP: Dict[str, DefiMetricType] = {
        "defi_dex_volume": DefiMetricType.DEX_VOLUME,
        "defi_dex_transactions": DefiMetricType.DEX_TRANSACTIONS,
        "defi_dex_traders": DefiMetricType.DEX_TRADERS,
        "defi_dex_count": DefiMetricType.DEX_COUNT,
    }

    _OVERVIEW_METRIC_TYPE_MAP: Dict[str, OverviewMetricType] = {
        "overview_sol_price": OverviewMetricType.SOL_PRICE,
    }

    def __init__(self, *, api_key: Optional[str] = None) -> None:
        resolved_api_key = api_key or os.environ.get("BITQUERY_API_KEY") or ""
        if not resolved_api_key:
            raise ValueError("BITQUERY_API_KEY is required")

        super().__init__(
            name="Bitquery",
            base_url=self.BASE_URL,
            api_key=resolved_api_key,
        )
        self._session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            backoff_jitter=0.5,
            status_forcelist=(408, 429, 500, 502, 503, 504),
            allowed_methods=frozenset({"POST"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        self._session.mount("https://", HTTPAdapter(max_retries=retry))

    # -- private helpers ----------------------------------------------------

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        """Coerce an API value to a finite float, or None if it can't be.

        Aggregate values arrive as JSON strings (e.g. "31572024"); guards
        against schema drift and non-finite values poisoning a metric.
        """
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None
        return result if math.isfinite(result) else None

    def _post(self, query: str) -> Any:
        resp = self._session.post(
            self.base_url,
            json={"query": query},
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            timeout=self._TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("errors"):
            raise RuntimeError(f"Bitquery GraphQL error: {payload['errors']}")
        return payload.get("data") or {}

    @staticmethod
    def _day_bounds(start_date: str, end_date: str) -> tuple[str, str]:
        """Return [since, till) ISO instants covering the inclusive date range."""
        start = datetime.date.fromisoformat(start_date)
        end = datetime.date.fromisoformat(end_date)
        since = f"{start.isoformat()}T00:00:00Z"
        till = f"{(end + datetime.timedelta(days=1)).isoformat()}T00:00:00Z"
        return since, till

    # -- BaseProvider interface ---------------------------------------------

    def fetch_rows(
        self, metric: str, start_date: str, end_date: str, **kwargs: Any
    ) -> List[Dict[str, Any]]:
        """Return normalized {"date": str, "value": Any} records for the given range (start_date and end_date are both inclusive)."""
        config = self.METRIC_MAP.get(metric)
        if config is None:
            available = ", ".join(self.METRIC_MAP)
            raise ValueError(f"Unknown metric '{metric}'. Available: {available}")

        since, till = self._day_bounds(start_date, end_date)
        query = config["query"].format(
            since=since,
            till=till,
            aggregate=config.get("aggregate", ""),
            mint=_WSOL_MINT,
        )
        data = self._post(query)
        rows = (data.get("Trading") or {}).get(config["cube"]) or []

        result: List[Dict[str, Any]] = []
        for row in rows:
            date = (row.get("Block") or {}).get("Date")
            # The till bound can echo a sliver of the next day; keep only
            # dates inside the requested inclusive range.
            if not date or not (start_date <= date <= end_date):
                continue
            value = self._to_float(row.get("value"))
            if value is None:
                continue
            result.append({"date": date, "value": config["cast"](value)})
        return result

    def get_metric(self, metric: str, date: str, chain: str) -> Defi | Overview | None:
        """Fetch one metric for one date and chain from provider API."""
        rows = self.fetch_rows(metric, date, date)
        if not rows:
            return None

        value = rows[0]["value"]
        parsed_date = datetime.date.fromisoformat(date)

        if metric in self._DEFI_METRIC_TYPE_MAP:
            return Defi.from_metric_type(
                metric_type=self._DEFI_METRIC_TYPE_MAP[metric],
                date=parsed_date,
                value=value,
            )
        if metric in self._OVERVIEW_METRIC_TYPE_MAP:
            return Overview.from_metric_type(
                metric_type=self._OVERVIEW_METRIC_TYPE_MAP[metric],
                date=parsed_date,
                value=value,
            )
        return None
