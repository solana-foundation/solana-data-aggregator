"""Uniblock data provider."""

from __future__ import annotations

import datetime
import math
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from metrics.network import Network, NetworkMetricType
from metrics.overview import Overview, OverviewMetricType
from providers.base import BaseProvider


class Uniblock(BaseProvider):
    """Fetch Solana metrics from the Uniblock unified API (api.uniblock.dev)."""

    BASE_URL = "https://api.uniblock.dev/uni/v1"
    _CHAIN = "solana"
    _SYMBOL = "SOL"
    _CURRENCY = "USD"
    _LAMPORTS_PER_SOL = 1_000_000_000

    _TIMEOUT = (5, 90)

    METRIC_MAP: Dict[str, Dict[str, Any]] = {
        "overview_sol_price": {
            "kind": "chart",
            "endpoint": "/market-data/chart-range",
            "value_field": "price",
            "methodology": (
                "Daily average SOL/USD price computed by averaging Uniblock "
                "unified market-data (CoinGecko-backed) intraday price points "
                "per UTC day."
            ),
            "methodology_url": "https://docs.uniblock.dev/api-reference/market-data/get-token-market-chart",
        },
        "network_sol_price": {
            "kind": "chart",
            "endpoint": "/market-data/chart-range",
            "value_field": "price",
            "methodology": (
                "Daily average SOL/USD price computed by averaging Uniblock "
                "unified market-data (CoinGecko-backed) intraday price points "
                "per UTC day."
            ),
            "methodology_url": "https://docs.uniblock.dev/api-reference/market-data/get-token-market-chart",
        },
        "network_total_stake": {
            "kind": "rpc",
            "rpc_kind": "total_stake",
            "methodology": (
                "Total activated stake across current and delinquent vote "
                "accounts from Solana getVoteAccounts, converted from lamports "
                "to SOL. Current-state snapshot."
            ),
            "methodology_url": "https://docs.uniblock.dev/api-reference/json-rpc/send-json-rpc-requests",
        },
        "network_validator_count": {
            "kind": "rpc",
            "rpc_kind": "validator_count",
            "methodology": (
                "Count of current (actively voting) vote accounts from Solana "
                "getVoteAccounts, excluding delinquent. Current-state snapshot."
            ),
            "methodology_url": "https://docs.uniblock.dev/api-reference/json-rpc/send-json-rpc-requests",
        },
    }

    _OVERVIEW_METRIC_TYPE_MAP: Dict[str, OverviewMetricType] = {
        "overview_sol_price": OverviewMetricType.SOL_PRICE,
    }

    _NETWORK_METRIC_TYPE_MAP: Dict[str, NetworkMetricType] = {
        "network_sol_price": NetworkMetricType.SOL_PRICE,
        "network_total_stake": NetworkMetricType.TOTAL_STAKE,
        "network_validator_count": NetworkMetricType.VALIDATOR_COUNT,
    }

    def __init__(self, *, api_key: Optional[str] = None) -> None:
        resolved = api_key or os.environ.get("UNIBLOCK_API_KEY")

        if not resolved:
            raise ValueError("UNIBLOCK_API_KEY is required")

        super().__init__(
            name="Uniblock",
            base_url=self.BASE_URL,
            api_key=resolved,
        )
        self._session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            backoff_jitter=0.5,
            status_forcelist=(408, 429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "POST"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        self._session.mount("https://", HTTPAdapter(max_retries=retry))

    # -- shared helpers -----------------------------------------------------

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        """Coerce an API value to a finite float, or None if it can't be."""
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None

        return result if math.isfinite(result) else None

    # -- market-data (chart) ------------------------------------------------

    def _get(self, endpoint: str, *, params: Dict[str, Any]) -> Any:
        headers = {"X-API-Key": self.api_key, "accept": "application/json"}
        resp = self._session.get(
            f"{self.base_url}{endpoint}",
            params=params,
            headers=headers,
            timeout=self._TIMEOUT,
        )
        resp.raise_for_status()

        return resp.json()

    @staticmethod
    def _daily_average(
        data: Dict[str, Any], value_field: str, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """Average intraday points per UTC day within the inclusive range."""
        buckets: Dict[str, List[float]] = defaultdict(list)

        for ts_ms, entry in data.items():
            try:
                seconds = int(ts_ms) / 1000
            except (TypeError, ValueError):
                continue

            row_date = datetime.datetime.fromtimestamp(
                seconds, tz=datetime.timezone.utc
            ).strftime("%Y-%m-%d")

            if not (start_date <= row_date <= end_date):
                continue

            if not isinstance(entry, dict):
                continue

            value = Uniblock._to_float(entry.get(value_field))

            if value is None:
                continue

            buckets[row_date].append(value)

        return [
            {"date": row_date, "value": sum(values) / len(values)}
            for row_date, values in sorted(buckets.items())
        ]

    def _fetch_chart_rows(
        self, config: Dict[str, Any], start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        start_dt = datetime.datetime.fromisoformat(start_date).replace(
            tzinfo=datetime.timezone.utc
        )
        end_dt = datetime.datetime.fromisoformat(end_date).replace(
            hour=23, minute=59, second=59, tzinfo=datetime.timezone.utc
        )
        body = self._get(
            config["endpoint"],
            params={
                "symbol": self._SYMBOL,
                "currency": self._CURRENCY,
                "from": int(start_dt.timestamp()),
                "to": int(end_dt.timestamp()),
            },
        )
        data = body.get("data") if isinstance(body, dict) else None

        if not isinstance(data, dict):
            return []

        return self._daily_average(data, config["value_field"], start_date, end_date)

    # -- solana json-rpc (snapshot) -----------------------------------------

    def _post_rpc(self, method: str, params: List[Any]) -> Any:
        """Send one JSON-RPC method and return its ``result``."""
        resp = self._session.post(
            f"{self.base_url}/json-rpc",
            params={"chainId": self._CHAIN},
            headers={"X-API-Key": self.api_key, "accept": "application/json"},
            json={"id": 1, "jsonrpc": "2.0", "method": method, "params": params},
            timeout=self._TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()

        if not isinstance(payload, dict):
            raise RuntimeError(f"Unexpected RPC response for {method}: {payload!r}")

        if payload.get("error"):
            raise RuntimeError(f"Solana RPC {method} failed: {payload['error']}")

        return payload.get("result")

    def _get_vote_accounts(self) -> Dict[str, Any]:
        result = self._post_rpc("getVoteAccounts", [])
        return result if isinstance(result, dict) else {}

    def _rpc_value(self, rpc_kind: str) -> Optional[float]:
        """Compute a snapshot metric value from Solana JSON-RPC."""
        accounts = self._get_vote_accounts()
        if rpc_kind == "validator_count":
            return float(len(accounts.get("current", [])))

        if rpc_kind == "total_stake":
            lamports = 0.0
            for group in ("current", "delinquent"):
                for account in accounts.get(group, []):
                    stake = self._to_float(account.get("activatedStake"))
                    if stake is not None:
                        lamports += stake
            return lamports / self._LAMPORTS_PER_SOL

        return None

    # -- BaseProvider interface ---------------------------------------------

    def fetch_rows(
        self, metric: str, start_date: str, end_date: str, **kwargs: Any
    ) -> List[Dict[str, Any]]:
        """Return normalized {"date": str, "value": float} records for the given range (both dates inclusive).

        Note: JSON-RPC metrics (stake, validators) are current snapshots — they
        return a single row dated today when today falls within the range. Only
        SOL price supports historical backfill.
        """
        config = self.METRIC_MAP.get(metric)

        if config is None:
            available = ", ".join(self.METRIC_MAP)
            raise ValueError(f"Unknown metric '{metric}'. Available: {available}")

        if config["kind"] == "chart":
            return self._fetch_chart_rows(config, start_date, end_date)

        today = datetime.date.today().isoformat()
        if not (start_date <= today <= end_date):
            return []

        value = self._rpc_value(config["rpc_kind"])
        if value is None:
            return []

        return [{"date": today, "value": float(value)}]

    def get_metric(
        self, metric: str, date: str, chain: str = _CHAIN
    ) -> Overview | Network | None:
        """Fetch one metric for one date and return it as a typed metric model."""
        if chain != self._CHAIN:
            raise ValueError(
                f"Unsupported chain '{chain}'; Uniblock provider only serves "
                f"'{self._CHAIN}'."
            )
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

        network_type = self._NETWORK_METRIC_TYPE_MAP.get(metric)
        if network_type is not None:
            return Network.from_metric_type(
                metric_type=network_type, date=parsed_date, value=value
            )

        return None
