"""Blockworks Research data provider."""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional, Tuple

import requests

from metrics.defi import Defi, DefiMetricType
from metrics.overview import Overview, OverviewMetricType
from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.base import BaseProvider


class Blockworks(BaseProvider):
    """Fetch stablecoin metrics from the Blockworks Research API."""

    METRIC_MAP: Dict[str, Dict[str, Any]] = {
        "stablecoin_total_supply": {
            "endpoint": "/metrics/stablecoin-supply-total-usd",
            "params": {"project": "solana"},
            "data_path": ["solana"],
            "date_field": "date",
            "value_field": "value",
        },
        "stablecoin_transfer_volume": {
            "chart_id": 2431,
            "date_field": "block_date",
            "value_field": "amount_usd",
        },
        "stablecoin_transfer_count": {
            "chart_id": 2430,
            "date_field": "block_date",
            "value_field": "total_transfers",
        },
        "stablecoin_active_addresses": {
            "chart_id": 5046,
            "date_field": "dt",
            "value_field": "unique_signer",
            "methodology": "Unique signer addresses that execute a transaction involving a stablecoin.",
        },
        "overview_fee_payers": {
            "endpoint": "/metrics/active-address-total",
            "params": {"project": "solana"},
            "use_date_params": True,
            "data_path": ["solana"],
            "date_field": "date",
            "value_field": "value",
        },
        "overview_sol_price": {
            "endpoint": "/metrics/token-price-usd",
            "params": {"project": "solana"},
            "use_date_params": True,
            "data_path": ["solana"],
            "date_field": "date",
            "value_field": "value",
        },
        "overview_fees": {
            "endpoint": "/metrics/transaction-fee-total-native",
            "params": {"project": "solana"},
            "use_date_params": True,
            "data_path": ["solana"],
            "date_field": "date",
            "value_field": "value",
        },
        "overview_non_vote_tx_count_success": {
            "endpoint": "/metrics/transaction-succeed-total",
            "params": {"project": "solana"},
            "use_date_params": True,
            "data_path": ["solana"],
            "date_field": "date",
            "value_field": "value",
        },
        "overview_non_vote_tx_count_failed": {
            "endpoint": "/metrics/transaction-fail-total",
            "params": {"project": "solana"},
            "use_date_params": True,
            "data_path": ["solana"],
            "date_field": "date",
            "value_field": "value",
        },
        "defi_dex_volume": {
            "endpoint": "/metrics/dex-spot-volume-total-usd",
            "params": {"project": "solana"},
            "use_date_params": True,
            "data_path": ["solana"],
            "date_field": "date",
            "value_field": "value",
        },
        "defi_dex_count": {
            "chart_id": 8213,
            "date_field": "block_date",
            "aggregate_distinct": "exchange_id",
            "methodology": "Top spot DEXs that aggregators route to.",
        },
        "overview_compute_units": {
            "chart_id": 2000,
            "date_field": "block_date",
            "value_field": "avg_total_cu_per_block",
        },
        "overview_app_revenue": {
            "chart_id": 1472,
            "date_field": "dt",
            "value_field": "revenue",
        },
        # Charts 7653 and 7655 return the same daily lending table (Kamino + Jupiter Lend)
        "defi_lending_total_deposits": {
            "chart_id": 7653,
            "date_field": "dt",
            "value_field": "total_deposit",
        },
        "defi_lending_total_borrowed": {
            "chart_id": 7655,
            "date_field": "dt",
            "value_field": "total_borrow",
        },
        "defi_lending_utilization_rate": {
            "chart_id": 7653,
            "date_field": "dt",
            "value_field": "total_dep_utilization",
            # Blockworks reports a 0-1 ratio; stored as a 0-100 percentage
            "value_scale": 100,
        },
        "defi_lending_protocol_count": {
            "chart_id": 7653,
            "date_field": "dt",
            # One protocol_deposit_<protocol> column per protocol; "_other" is a catch-all bucket
            "count_positive_prefix": "protocol_deposit_",
            "count_exclude_fields": ["protocol_deposit_other"],
        },
    }

    BASE_URL = "https://api.blockworks.com/v1"

    def __init__(self, *, api_key: Optional[str] = None) -> None:
        resolved_api_key = api_key or self._resolve_api_key()
        if not resolved_api_key:
            raise ValueError("API key is required")
        super().__init__(
            name="Blockworks",
            base_url=self.BASE_URL,
            api_key=resolved_api_key,
        )
        self._session = requests.Session()
        self._chart_cache: Dict[Tuple[int, str], List[Dict[str, Any]]] = {}

    # -- private helpers ----------------------------------------------------

    @staticmethod
    def _resolve_api_key() -> Optional[str]:
        return os.environ.get("BLOCKWORKS_API_KEY")

    def _get(self, endpoint: str, *, params: Optional[Dict[str, Any]] = None) -> dict:
        url = f"{self.base_url}{endpoint}"
        resp = self._session.get(
            url, headers={"x-api-key": self.api_key}, params=params or {}
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _to_iso_date(value: Any) -> str:
        return str(value or "")[:10]

    def _row_date(self, row: Dict[str, Any], date_field: str) -> str:
        val = row.get(date_field)
        if val:
            return self._to_iso_date(val)
        for fallback in ("dt", "block_date", "date"):
            val = row.get(fallback)
            if val:
                return self._to_iso_date(val)
        return ""

    def _extract_payload(self, body: Any, path: List[str]) -> List[Dict[str, Any]]:
        node: Any = body
        for key in path:
            if not isinstance(node, dict):
                return []
            node = node.get(key)
        if isinstance(node, list):
            return node
        return []

    def _get_chart_data(
        self,
        chart_id: int,
        *,
        start_date: str,
        end_date: str,
        date_field: str = "dt",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Return the chart's rows within the date range.

        Every page is fetched regardless of the range, so the full chart is
        cached on the instance and metrics sharing a chart (e.g. lending
        deposits and utilization on 7653) reuse one set of calls.
        """
        cache_key = (chart_id, date_field)
        if cache_key not in self._chart_cache:
            self._chart_cache[cache_key] = self._fetch_all_chart_rows(
                chart_id, date_field=date_field, limit=limit
            )
        return [
            row
            for row in self._chart_cache[cache_key]
            if start_date <= self._row_date(row, date_field) <= end_date
        ]

    def _fetch_all_chart_rows(
        self, chart_id: int, *, date_field: str, limit: int
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        page = 1
        while True:
            body = self._get(
                f"/charts/{chart_id}/data",
                params={
                    "order_by": date_field,
                    "order_dir": "asc",
                    "limit": limit,
                    "page": page,
                },
            )
            page_data = body.get("data", [])
            if not page_data:
                break
            rows.extend(page_data)
            total = body.get("total", 0)
            if len(page_data) < limit or (total and page * limit >= total):
                break
            page += 1
        return rows

    def fetch_rows(
        self, metric: str, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """Return normalized {"date": str, "value": Any} records for the given range (both dates inclusive)."""
        config = self.METRIC_MAP[metric]
        chart_id = config.get("chart_id")
        if chart_id is not None:
            raw = self._get_chart_data(
                chart_id,
                start_date=start_date,
                end_date=end_date,
                date_field=config.get("date_field", "dt"),
            )
        else:
            params = dict(config.get("params") or {})
            if config.get("use_date_params"):
                params["start_date"] = start_date
                params["end_date"] = end_date
            body = self._get(config["endpoint"], params=params)
            data = self._extract_payload(body, config.get("data_path", []))
            raw = [
                row
                for row in data
                if start_date
                <= self._to_iso_date(row.get(config["date_field"]))
                <= end_date
            ]

        distinct_field = config.get("aggregate_distinct")
        if distinct_field is not None:
            buckets: Dict[str, set] = {}
            for row in raw:
                row_date = self._row_date(row, config["date_field"])
                if not row_date:
                    continue
                val = row.get(distinct_field)
                if val is not None:
                    buckets.setdefault(row_date, set()).add(val)
            return [
                {"date": d, "value": float(len(s))} for d, s in sorted(buckets.items())
            ]

        result = []
        for row in raw:
            row_date = self._row_date(row, config["date_field"])
            if not row_date:
                continue
            value = self._extract_value(row, config)
            if value is None:
                continue
            result.append({"date": row_date, "value": float(value) * config.get("value_scale", 1)})
        return result

    def _extract_value(self, row: Dict[str, Any], config: Dict[str, Any]) -> Any:
        prefix = config.get("count_positive_prefix")
        if prefix is not None:
            excluded = set(config.get("count_exclude_fields", []))
            return sum(
                1
                for field, value in row.items()
                if field.startswith(prefix) and field not in excluded and (value or 0) > 0
            )
        return row.get(config["value_field"])

    # -- BaseProvider interface ---------------------------------------------

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
            "overview_fee_payers": OverviewMetricType.FEE_PAYERS,
            "overview_sol_price": OverviewMetricType.SOL_PRICE,
            "overview_fees": OverviewMetricType.FEES,
            "overview_non_vote_tx_count_success": OverviewMetricType.TX_COUNT_NON_VOTE_SUCCESS,
            "overview_non_vote_tx_count_failed": OverviewMetricType.TX_COUNT_NON_VOTE_FAILED,
            "overview_compute_units": OverviewMetricType.COMPUTE_UNITS,
            "overview_tx_count_total": OverviewMetricType.TX_COUNT_TOTAL,
            "overview_app_revenue": OverviewMetricType.APP_REVENUE,
        }
        if metric in overview_metric_map:
            return Overview.from_metric_type(
                metric_type=overview_metric_map[metric],
                date=parsed_date,
                value=value,
            )

        defi_metric_map = {
            "defi_dex_volume": DefiMetricType.DEX_VOLUME,
            "defi_dex_count": DefiMetricType.DEX_COUNT,
            "defi_lending_total_deposits": DefiMetricType.LENDING_TOTAL_DEPOSITS,
            "defi_lending_total_borrowed": DefiMetricType.LENDING_TOTAL_BORROWED,
            "defi_lending_utilization_rate": DefiMetricType.LENDING_UTILIZATION_RATE,
            "defi_lending_protocol_count": DefiMetricType.LENDING_PROTOCOL_COUNT,
        }
        if metric in defi_metric_map:
            return Defi.from_metric_type(
                metric_type=defi_metric_map[metric],
                date=parsed_date,
                value=value,
            )

        stablecoin_metric_map = {
            "stablecoin_total_supply": StablecoinMetricType.TOTAL_SUPPLY,
            "stablecoin_transfer_volume": StablecoinMetricType.TRANSFER_VOLUME,
            "stablecoin_transfer_count": StablecoinMetricType.TRANSFER_COUNT,
            "stablecoin_active_addresses": StablecoinMetricType.ACTIVE_ADDRESSES,
        }
        return Stablecoin.from_metric_type(
            metric_type=stablecoin_metric_map[metric],
            date=parsed_date,
            value=value,
        )
