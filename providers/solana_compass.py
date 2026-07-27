"""Solana Compass data provider."""

from __future__ import annotations

import datetime
import os
from typing import Any, Callable, Dict, List, Optional

import requests

from metrics.defi import Defi, DefiMetricType
from metrics.overview import Overview, OverviewMetricType
from providers.base import BaseProvider


class SolanaCompass(BaseProvider):
    """Fetch overview and DeFi metrics from the Solana Compass analytics API."""

    AVAILABLE_FROM = datetime.date(2025, 12, 1)
    _COVERAGE_NOTE = " Solana Compass Elasticsearch analytics coverage is available from 2025-12-01."

    METRIC_MAP: Dict[str, Dict[str, Any]] = {
        "overview_tx_count_total": {
            "page": "overview",
            "metric_type": OverviewMetricType.TX_COUNT_TOTAL,
            "methodology": "Total daily Solana transactions from Solana Compass block and transaction summary indexes, including vote, successful non-vote, and failed non-vote transactions when vote supplementation is available." + _COVERAGE_NOTE,
            "methodology_url": "https://solanacompass.com",
        },
        "overview_tx_count_vote": {
            "page": "overview",
            "metric_type": OverviewMetricType.TX_COUNT_VOTE,
            "methodology": "Daily vote transaction count from Solana Compass block metrics supplementation." + _COVERAGE_NOTE,
            "methodology_url": "https://solanacompass.com",
        },
        "overview_non_vote_tx_count_success": {
            "page": "overview",
            "metric_type": OverviewMetricType.TX_COUNT_NON_VOTE_SUCCESS,
            "methodology": "Daily successful non-vote transactions from Solana Compass transaction summary indexes." + _COVERAGE_NOTE,
            "methodology_url": "https://solanacompass.com",
        },
        "overview_non_vote_tx_count_failed": {
            "page": "overview",
            "metric_type": OverviewMetricType.TX_COUNT_NON_VOTE_FAILED,
            "methodology": "Daily failed non-vote transactions from Solana Compass transaction summary indexes with block metric supplementation where available." + _COVERAGE_NOTE,
            "methodology_url": "https://solanacompass.com",
        },
        "overview_fees": {
            "page": "overview",
            "metric_type": OverviewMetricType.FEES,
            "methodology": "Daily Solana transaction fees in SOL from Solana Compass fee and block metrics, including fees paid by failed transactions where block supplementation is available." + _COVERAGE_NOTE,
            "methodology_url": "https://solanacompass.com",
        },
        "overview_fee_payers": {
            "page": "fees",
            "metric_type": OverviewMetricType.FEE_PAYERS,
            "methodology": (
                "Distinct signers of user transactions from Solana Compass "
                "transaction summary indexes, not literal fee payer accounts. "
                "This captures fee-sponsored users similarly to Artemis DAU."
                + _COVERAGE_NOTE
            ),
            "methodology_url": "https://solanacompass.com",
        },
        "defi_dex_volume": {
            "page": "defi",
            "metric_type": DefiMetricType.DEX_VOLUME,
            "methodology": "Daily Solana DEX spot volume in USD from Solana Compass DEX program volume indexes." + _COVERAGE_NOTE,
            "methodology_url": "https://solanacompass.com",
        },
        "defi_dex_transactions": {
            "page": "defi",
            "metric_type": DefiMetricType.DEX_TRANSACTIONS,
            "methodology": "Daily Solana DEX trade count from Solana Compass DEX program volume indexes." + _COVERAGE_NOTE,
            "methodology_url": "https://solanacompass.com",
        },
        "defi_dex_traders": {
            "page": "defi",
            "metric_type": DefiMetricType.DEX_TRADERS,
            "methodology": "Daily Solana DEX trader count from Solana Compass DEX program volume indexes." + _COVERAGE_NOTE,
            "methodology_url": "https://solanacompass.com",
        },
        "defi_dex_count": {
            "page": "defi",
            "metric_type": DefiMetricType.DEX_COUNT,
            "methodology": "Daily active Solana DEX program count observed by Solana Compass DEX program volume indexes." + _COVERAGE_NOTE,
            "methodology_url": "https://solanacompass.com",
        },
    }

    BASE_URL = "https://solanacompass.com/api/v1"

    _OVERVIEW_EXTRACTORS: Dict[str, Callable[[Dict[str, Any]], Optional[float]]] = {
        "overview_tx_count_total": lambda summary: _float_or_none(
            summary.get("totalNetworkTransactions")
        )
        or _sum_present(
            summary.get("txCount"),
            summary.get("totalCompleted"),
            summary.get("completed"),
            summary.get("totalReverted"),
            summary.get("reverted"),
            summary.get("totalVotes"),
            summary.get("votes"),
        ),
        "overview_tx_count_vote": lambda summary: _float_or_none(
            summary.get("totalVotes")
            if summary.get("totalVotes") is not None
            else summary.get("votes")
        ),
        "overview_non_vote_tx_count_success": lambda summary: _float_or_none(
            summary.get("totalCompleted")
            if summary.get("totalCompleted") is not None
            else summary.get("completed")
        ),
        "overview_non_vote_tx_count_failed": lambda summary: _float_or_none(
            summary.get("totalReverted")
            if summary.get("totalReverted") is not None
            else summary.get("reverted")
        ),
        "overview_fees": lambda summary: _float_or_none(
            summary.get("totalFees") if summary.get("totalFees") is not None else summary.get("fees")
        ),
    }

    _DEFI_EXTRACTORS: Dict[str, Callable[[Dict[str, Any]], Optional[float]]] = {
        "defi_dex_volume": lambda summary: _float_or_none(
            summary.get("totalVolume")
            if summary.get("totalVolume") is not None
            else summary.get("volume")
        ),
        "defi_dex_transactions": lambda summary: _float_or_none(
            summary.get("totalTrades")
            if summary.get("totalTrades") is not None
            else summary.get("trades")
        ),
        "defi_dex_traders": lambda summary: _float_or_none(
            summary.get("totalTraders")
            if summary.get("totalTraders") is not None
            else summary.get("traders")
        ),
        "defi_dex_count": lambda summary: _float_or_none(summary.get("programs")),
    }

    _FEE_EXTRACTORS: Dict[str, Callable[[Dict[str, Any]], Optional[float]]] = {
        "overview_fee_payers": lambda summary: _float_or_none(
            summary.get("totalUniqueWallets")
            if summary.get("totalUniqueWallets") is not None
            else summary.get("signers")
            if summary.get("signers") is not None
            else summary.get("uniqueSigners")
        ),
    }

    def __init__(
        self, *, api_key: Optional[str] = None, base_url: Optional[str] = None
    ) -> None:
        resolved_api_key = api_key or os.environ.get("SOLANA_COMPASS_API_KEY", "")
        resolved_base_url = (
            base_url or os.environ.get("SOLANA_COMPASS_BASE_URL") or self.BASE_URL
        )
        super().__init__(
            name="SolanaCompass",
            base_url=resolved_base_url.rstrip("/"),
            api_key=resolved_api_key,
        )
        self._session = requests.Session()

    def _get(self, endpoint: str, *, params: Optional[Dict[str, Any]] = None) -> dict:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        resp = self._session.get(
            f"{self.base_url}{endpoint}",
            headers=headers,
            params=params or {},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _date_window(start: datetime.date, end: datetime.date) -> Dict[str, str]:
        next_day = end + datetime.timedelta(days=1)
        return {
            "from": f"{start.isoformat()}T00:00:00Z",
            "to": f"{next_day.isoformat()}T00:00:00Z",
            # Solana Compass analytics controllers use range to choose the
            # backing transform. Keep exact from/to for the date window, and set
            # range=yesterday so DEX/network requests use daily indexes.
            "range": "yesterday",
            "interval": "1d",
        }

    def _fetch_range_data(
        self, page: str, start: datetime.date, end: datetime.date
    ) -> Dict[str, Any]:
        params = self._date_window(start, end)
        if page == "overview":
            body = self._get("/network/overview", params=params)
        elif page == "fees":
            body = self._get("/network/fees", params=params)
        elif page == "defi":
            body = self._get("/dex/volume", params=params)
        else:
            raise ValueError(f"Unknown Solana Compass metric page: {page}")

        data = body.get("data", {})
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _row_date(row: Dict[str, Any]) -> Optional[str]:
        timestamp = row.get("timestamp")
        if timestamp is None:
            return None
        return datetime.datetime.utcfromtimestamp(timestamp / 1000).date().isoformat()

    def fetch_rows(
        self, metric: str, start_date: str, end_date: str, **kwargs: Any
    ) -> List[Dict[str, Any]]:
        """Return normalized {"date": str, "value": Any} records for the given inclusive date range."""
        config = self.METRIC_MAP.get(metric)
        if config is None:
            available = ", ".join(self.METRIC_MAP)
            raise ValueError(f"Unknown metric '{metric}'. Available: {available}")

        page = config["page"]
        extractor = (
            self._OVERVIEW_EXTRACTORS.get(metric)
            if page == "overview"
            else self._FEE_EXTRACTORS.get(metric)
            if page == "fees"
            else self._DEFI_EXTRACTORS.get(metric)
        )
        if extractor is None:
            raise ValueError(f"No extractor configured for metric '{metric}'")

        requested_start = datetime.date.fromisoformat(start_date)
        end = datetime.date.fromisoformat(end_date)
        start = max(requested_start, self.AVAILABLE_FROM)
        if end < start:
            return []

        data = self._fetch_range_data(page, start, end)
        time_series = data.get("timeSeries", [])
        if not isinstance(time_series, list):
            return []

        result = []
        for row in time_series:
            if not isinstance(row, dict):
                continue
            row_date = self._row_date(row)
            if not row_date or not (start.isoformat() <= row_date <= end.isoformat()):
                continue
            value = extractor(row)
            if value is not None:
                result.append({"date": row_date, "value": float(value)})
        return result

    def get_metric(self, metric: str, date: str, chain: str) -> Overview | Defi | None:
        """Fetch one metric value and return it as a typed metric model."""
        rows = self.fetch_rows(metric, date, date)
        if not rows:
            return None

        config = self.METRIC_MAP[metric]
        parsed_date = datetime.date.fromisoformat(date)
        value = rows[0]["value"]
        metric_type = config["metric_type"]

        if isinstance(metric_type, OverviewMetricType):
            return Overview.from_metric_type(
                metric_type=metric_type,
                date=parsed_date,
                value=value,
            )

        return Defi.from_metric_type(
            metric_type=metric_type,
            date=parsed_date,
            value=value,
        )


def _float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    return float(value)


def _sum_present(*values: Any) -> Optional[float]:
    if all(value is None for value in values):
        return None
    return sum(float(value or 0) for value in values)
