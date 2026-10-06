"""Blockworks Data API and Charts API provider."""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional, Tuple

import requests

from metrics.defi import Defi, DefiMetricType
from metrics.lending import Lending, LendingMetricType
from metrics.overview import Overview, OverviewMetricType
from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.base import BaseProvider

SOLANA_NETWORK_ID = "b204e48e-9812-43e6-a00b-5fcfd40e04a2"
SOL_ASSET_ID = "b3d5d66c-26a2-404c-9325-91dc714a722b"


class Blockworks(BaseProvider):
    """Fetch Solana metrics from Blockworks.

    Metrics with a ``model`` key read a Data API timeseries; metrics with a
    ``chart_id`` key read a published Blockworks chart (Charts API).
    """

    METRIC_MAP: Dict[str, Dict[str, Any]] = {
        "stablecoin_total_supply": {
            "model": "blockchains",
            "series": SOLANA_NETWORK_ID,
            "field": "stablecoin-outstanding-supply-usd",
        },
        "stablecoin_transfer_volume": {
            "model": "blockchains",
            "series": SOLANA_NETWORK_ID,
            "field": "stablecoin-transfer-volume-usd",
        },
        "stablecoin_transfer_count": {
            "model": "blockchains",
            "series": SOLANA_NETWORK_ID,
            "field": "stablecoin-transfer-count",
        },
        "stablecoin_active_addresses": {
            "model": "blockchains",
            "series": SOLANA_NETWORK_ID,
            "field": "stablecoin-active-addresses",
            "methodology": "Number of unique addresses that sent a stablecoin transfer.",
        },
        "overview_fee_payers": {
            "model": "blockchains",
            "series": SOLANA_NETWORK_ID,
            "field": "active-addresses",
        },
        "overview_sol_price": {
            "model": "asset-price",
            "series": SOL_ASSET_ID,
            "field": "close",
        },
        "overview_app_revenue": {
            "model": "blockchains",
            "series": SOLANA_NETWORK_ID,
            "field": "app-revenue-usd",
        },
        "overview_non_vote_tx_count_success": {
            "model": "blockchains",
            "series": SOLANA_NETWORK_ID,
            "field": "successful-transactions",
        },
        "overview_non_vote_tx_count_failed": {
            "model": "blockchains",
            "series": SOLANA_NETWORK_ID,
            "field": "unsuccessful-transactions",
        },
        "defi_dex_volume": {
            "model": "blockchains",
            "series": SOLANA_NETWORK_ID,
            "field": "dex-volume-usd",
        },
        "overview_fees": {
            # Fees in SOL: daily USD fees / SOL close price for the same day.
            # Matches other providers through Jul 2026; ~20-25% above them since
            # Blockworks revised fee-revenue from 2026-08-01 (reported to them).
            "model": "blockchains",
            "series": SOLANA_NETWORK_ID,
            "field": "fee-revenue",
            "divide_by": {
                "model": "asset-price",
                "series": SOL_ASSET_ID,
                "field": "close",
            },
        },
        # Chart 2000 ("Solana: Compute Unit Usage", Solana - Onchain Activity)
        "overview_compute_units": {
            "chart_id": 2000,
            "date_field": "block_date",
            "value_field": "avg_total_cu_per_block",
        },
        # Chart 8213 ("Solana: DEX Aggregator Volume by DEX"): one row per DEX per day
        "defi_dex_count": {
            "chart_id": 8213,
            "date_field": "block_date",
            "count_distinct": "exchange_id",
            "methodology": "Top spot DEXs that aggregators route to.",
        },
        # Chart 15954 ("Solana: Lending Total Deposits", Solana - Lending
        # dashboard): one row per day with totals and <protocol>_deposit /
        # <protocol>_borrow columns (Kamino, Jupiter Lend).
        "lending_total_deposits": {
            "chart_id": 15954,
            "value_field": "total_deposit",
        },
        "lending_total_borrowed": {
            "chart_id": 15954,
            "value_field": "total_borrow",
        },
        "lending_utilization_rate": {
            "chart_id": 15954,
            # borrow / deposit as a 0-100 percentage
            "ratio_fields": ("total_borrow", "total_deposit"),
            "value_scale": 100,
        },
        "lending_protocol_count": {
            "chart_id": 15954,
            # Protocols with deposits > 0; a protocol Blockworks adds later is
            # counted without a code change
            "count_positive_suffix": "_deposit",
            "count_exclude_prefixes": ("total_",),
            "count_exclude_suffixes": ("_stablecoin_deposit",),
        },
    }

    BASE_URL = "https://api.blockworks.com"
    GRANULARITY = "1d"
    CHART_PAGE_SIZE = 1000
    TIMEOUT_SECONDS = 120

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
        # chart_id -> (earliest date covered, rows); "" means the whole chart
        self._chart_cache: Dict[int, Tuple[str, List[Dict[str, Any]]]] = {}

    # -- private helpers ----------------------------------------------------

    @staticmethod
    def _resolve_api_key() -> Optional[str]:
        return os.environ.get("BLOCKWORKS_API_KEY")

    def _get(self, endpoint: str, *, params: Optional[Dict[str, Any]] = None) -> dict:
        url = f"{self.base_url}{endpoint}"
        resp = self._session.get(
            url,
            headers={"X-Blockworks-API-Key": self.api_key},
            params=params or {},
            timeout=self.TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _row_date(row: Dict[str, Any], date_field: str) -> str:
        return str(row.get(date_field) or "")[:10]

    def _get_chart_rows(
        self, chart_id: int, *, date_field: str, since: str
    ) -> List[Dict[str, Any]]:
        """Return a chart's rows from `since` onward, cached per instance.

        Pages newest-first and stops once a page reaches dates before `since`,
        so long charts (e.g. one row per DEX per day) aren't read in full.
        Metrics sharing a chart (lending on 15954) reuse one set of calls.
        """
        cached = self._chart_cache.get(chart_id)
        if cached is not None and cached[0] <= since:
            return cached[1]

        rows: List[Dict[str, Any]] = []
        covered = since
        page = 1
        while True:
            body = self._get(
                f"/v1/charts/{chart_id}/data",
                params={
                    "order_by": date_field,
                    "order_dir": "desc",
                    "limit": self.CHART_PAGE_SIZE,
                    "page": page,
                },
            )
            page_data = body.get("data") or []
            rows.extend(page_data)
            total = body.get("total") or 0
            if len(page_data) < self.CHART_PAGE_SIZE or len(rows) >= total:
                covered = ""  # reached the start of the chart
                break
            if self._row_date(page_data[-1], date_field) < since:
                break
            page += 1
        self._chart_cache[chart_id] = (covered, rows)
        return rows

    @staticmethod
    def _chart_value(row: Dict[str, Any], config: Dict[str, Any]) -> Optional[float]:
        suffix = config.get("count_positive_suffix")
        if suffix is not None:
            return float(
                sum(
                    1
                    for field, value in row.items()
                    if field.endswith(suffix)
                    and not field.startswith(config.get("count_exclude_prefixes", ()))
                    and not field.endswith(config.get("count_exclude_suffixes", ()))
                    and (value or 0) > 0
                )
            )
        ratio_fields = config.get("ratio_fields")
        if ratio_fields is not None:
            numerator, denominator = (row.get(f) for f in ratio_fields)
            if numerator is None or not denominator:
                return None
            return numerator / denominator * config.get("value_scale", 1)
        value = row.get(config["value_field"])
        return None if value is None else float(value)

    def _fetch_chart_rows(
        self, config: Dict[str, Any], start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        date_field = config.get("date_field", "dt")
        rows = [
            row
            for row in self._get_chart_rows(
                config["chart_id"], date_field=date_field, since=start_date
            )
            if start_date <= self._row_date(row, date_field) <= end_date
        ]

        distinct_field = config.get("count_distinct")
        if distinct_field is not None:
            buckets: Dict[str, set] = {}
            for row in rows:
                if row.get(distinct_field) is not None:
                    buckets.setdefault(self._row_date(row, date_field), set()).add(
                        row[distinct_field]
                    )
            return [
                {"date": d, "value": float(len(s))} for d, s in sorted(buckets.items())
            ]

        result = []
        for row in sorted(rows, key=lambda r: self._row_date(r, date_field)):
            value = self._chart_value(row, config)
            if value is None:
                continue
            result.append({"date": self._row_date(row, date_field), "value": value})
        return result

    def fetch_rows(
        self, metric: str, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """Return normalized {"date": str, "value": Any} records for the given range (both dates inclusive)."""
        config = self.METRIC_MAP[metric]
        if "chart_id" in config:
            return self._fetch_chart_rows(config, start_date, end_date)

        rows = self._fetch_timeseries(config, start_date, end_date)
        divisor_spec = config.get("divide_by")
        if divisor_spec is None:
            return rows
        divisors = {
            r["date"]: r["value"]
            for r in self._fetch_timeseries(divisor_spec, start_date, end_date)
        }
        return [
            {"date": r["date"], "value": r["value"] / divisors[r["date"]]}
            for r in rows
            if divisors.get(r["date"])
        ]

    def _fetch_timeseries(
        self, spec: Dict[str, Any], start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """Fetch one field of one Data API series as {"date", "value"} rows."""
        # The Data API's `end` is exclusive; our end_date is inclusive.
        end_exclusive = datetime.date.fromisoformat(end_date) + datetime.timedelta(
            days=1
        )
        body = self._get(
            f"/query/timeseries/{spec['model']}/{self.GRANULARITY}/{spec['series']}",
            params={
                "start": start_date,
                "end": end_exclusive.isoformat(),
                "selections": spec["field"],
            },
        )
        if body.get("error"):
            raise RuntimeError(f"Blockworks API error: {body['error']}")
        data = body["data"]

        # Each point is [unix_ts, value, ...] in point_schema order.
        fields = [col["field"] for col in data["point_schema"]]
        value_idx = fields.index(spec["field"])
        result = []
        for point in data.get("points", []):
            value = point[value_idx]
            if value is None:
                continue
            row_date = datetime.datetime.fromtimestamp(
                point[0], datetime.timezone.utc
            ).date()
            result.append({"date": row_date.isoformat(), "value": float(value)})
        return result

    # -- BaseProvider interface ---------------------------------------------

    def get_metric(
        self, metric: str, date: str, chain: str
    ) -> Stablecoin | Overview | Defi | Lending | None:
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
            "overview_compute_units": OverviewMetricType.COMPUTE_UNITS,
            "overview_app_revenue": OverviewMetricType.APP_REVENUE,
            "overview_non_vote_tx_count_success": OverviewMetricType.TX_COUNT_NON_VOTE_SUCCESS,
            "overview_non_vote_tx_count_failed": OverviewMetricType.TX_COUNT_NON_VOTE_FAILED,
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
        }
        if metric in defi_metric_map:
            return Defi.from_metric_type(
                metric_type=defi_metric_map[metric],
                date=parsed_date,
                value=value,
            )

        lending_metric_map = {
            "lending_total_deposits": LendingMetricType.TOTAL_DEPOSITS,
            "lending_total_borrowed": LendingMetricType.TOTAL_BORROWED,
            "lending_utilization_rate": LendingMetricType.UTILIZATION_RATE,
            "lending_protocol_count": LendingMetricType.PROTOCOL_COUNT,
        }
        if metric in lending_metric_map:
            return Lending.from_metric_type(
                metric_type=lending_metric_map[metric],
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
