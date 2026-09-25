"""DefiLlama data provider."""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional

import requests

from metrics.defi import Defi, DefiMetricType
from metrics.overview import Overview, OverviewMetricType
from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.base import BaseProvider


class DefiLlama(BaseProvider):
    """Fetch stablecoin metrics from the DefiLlama API."""

    METRIC_MAP: Dict[str, Dict[str, Any]] = {
        "stablecoin_circulating_supply": {
            "endpoint": "/stablecoins/stablecoincharts/solana",
            "value_path": ["totalCirculating", "peggedUSD"],
            "methodology": "Bridge-aware circulating supply, priced and aggregated across stablecoins and peg types.",
        },
        "stablecoin_transfer_volume": {
            "endpoint": "/stablecoins/chart/volume/chain/solana",
            "methodology": "USD value of stablecoin transfers using adjusted single-direction transfer methodologies.",
        },
        "defi_dex_volume": {
            "endpoint": "/api/v2/chart/dexs/chain/solana",
            "methodology": "Daily USD DEX trade value, sourced from adapters after bad-volume filtering.",
        },
        "defi_dex_count": {
            "endpoint": "/api/v2/chart/dexs/chain/solana/protocol-breakdown",
            "count_active_protocols": True,
            "methodology": "Spot DEX protocols with volume adapters and non-zero Solana trading activity.",
        },
        "stablecoin_count": {
            "endpoint": "/stablecoins/stablecoins",
            "count_solana_stablecoins": True,
        },
        "overview_sol_price": {
            "endpoint": "/coins/chart/coingecko:solana",
            "coins_chart": True,
        },
        "overview_app_revenue": {
            "endpoint": "/api/overview/fees/solana",
            "params": {
                "excludeTotalDataChart": "false",
                "excludeTotalDataChartBreakdown": "true",
                "dataType": "dailyAppRevenue",
            },
            "fees_overview": True,
        },
        "defi_lending_total_deposits": {
            "lending_field": "deposits",
            "methodology": "Solana TVL plus Solana borrowed, summed across DefiLlama Lending-category protocols.",
        },
        "defi_lending_active_loans": {
            "lending_field": "borrowed",
            "methodology": "Solana borrowed balance, summed across DefiLlama Lending-category protocols.",
        },
        "defi_lending_total_borrowed": {
            "lending_field": "borrowed",
            "methodology": "Solana borrowed balance, summed across DefiLlama Lending-category protocols; same source as active loans.",
        },
        "defi_lending_protocol_count": {
            "lending_field": "protocol_count",
            "methodology": "DefiLlama Lending-category protocols with non-zero Solana deposits that day.",
        },
    }

    LENDING_CATEGORY = "Lending"
    LENDING_CHAIN = "Solana"

    BASE_URL = "https://pro-api.llama.fi"

    def __init__(self, *, api_key: Optional[str] = None) -> None:
        resolved_api_key = api_key or os.environ.get("DEFILLAMA_API_KEY") or ""
        super().__init__(
            name="DefiLlama",
            base_url=self.BASE_URL,
            api_key=resolved_api_key,
        )
        self._session = requests.Session()
        self._lending_daily: Optional[Dict[str, Dict[str, float]]] = None

    # -- private helpers ----------------------------------------------------

    def _get(self, url: str, *, params: Optional[Dict[str, Any]] = None) -> Any:
        if self.api_key:
            url = url.replace(self.BASE_URL, f"{self.BASE_URL}/{self.api_key}", 1)
        resp = self._session.get(url, params=params or {}, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _fetch_lending_daily(self) -> Dict[str, Dict[str, float]]:
        """Aggregate Solana lending balances per day across Lending-category protocols.

        DefiLlama has no chain+category TVL chart, so this sums each protocol's
        `Solana` (TVL, net of borrows) and `Solana-borrowed` series from
        /api/protocol/{slug}. Cached on the instance since all four lending
        metrics share the same ~30 protocol calls.
        """
        if self._lending_daily is not None:
            return self._lending_daily

        protocols = self._get(f"{self.base_url}/api/protocols")
        slugs = [
            p["slug"]
            for p in protocols
            if p.get("category") == self.LENDING_CATEGORY
            and self.LENDING_CHAIN in (p.get("chains") or [])
        ]

        daily: Dict[str, Dict[str, float]] = {}
        for slug in slugs:
            chain_tvls = self._get(f"{self.base_url}/api/protocol/{slug}").get("chainTvls", {})
            protocol_day: Dict[str, Dict[str, float]] = {}
            for series_key, field in (
                (self.LENDING_CHAIN, "tvl"),
                (f"{self.LENDING_CHAIN}-borrowed", "borrowed"),
            ):
                for entry in chain_tvls.get(series_key, {}).get("tvl", []):
                    # Series end with an intraday "now" point; keep the day's first (00:00 UTC) snapshot
                    day = protocol_day.setdefault(self._ts_to_date(int(entry["date"])), {})
                    day.setdefault(field, float(entry.get("totalLiquidityUSD") or 0))

            for row_date, values in protocol_day.items():
                deposits = values.get("tvl", 0.0) + values.get("borrowed", 0.0)
                agg = daily.setdefault(
                    row_date, {"deposits": 0.0, "borrowed": 0.0, "protocol_count": 0.0}
                )
                agg["deposits"] += deposits
                agg["borrowed"] += values.get("borrowed", 0.0)
                if deposits > 0:
                    agg["protocol_count"] += 1

        self._lending_daily = daily
        return daily

    # -- BaseProvider interface ---------------------------------------------

    @staticmethod
    def _ts_to_date(ts: int) -> str:
        return (
            datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
            .date()
            .isoformat()
        )

    def fetch_rows(
        self, metric: str, start_date: str, end_date: str, **kwargs: Any
    ) -> List[Dict[str, Any]]:
        """Return normalized {"date": str, "value": float} records for the given range (both dates inclusive)."""
        config = self.METRIC_MAP.get(metric)
        if config is None:
            available = ", ".join(self.METRIC_MAP)
            raise ValueError(f"Unknown metric '{metric}'. Available: {available}")

        result = []

        if config.get("count_solana_stablecoins"):
            raw = self._get(
                f"{self.base_url}{config['endpoint']}",
                params={"includePrices": "true"},
            )
            count = sum(
                1
                for s in raw.get("peggedAssets", [])
                if s.get("pegType") == "peggedUSD"
                and (
                    s.get("chainCirculating", {})
                    .get("Solana", {})
                    .get("current", {})
                    .get("peggedUSD", 0)
                )
                > 0
            )
            today = datetime.date.today().isoformat()
            return [{"date": today, "value": float(count)}]

        if config.get("coins_chart"):
            start_ts = int(
                datetime.datetime.fromisoformat(start_date)
                .replace(hour=12, tzinfo=datetime.timezone.utc)
                .timestamp()
            )
            span = min(
                (
                    datetime.date.fromisoformat(end_date)
                    - datetime.date.fromisoformat(start_date)
                ).days
                + 2,
                365,
            )
            raw = self._get(
                f"{self.base_url}{config['endpoint']}",
                params={"start": start_ts, "span": span, "period": "1d"},
            )
            prices = raw.get("coins", {}).get("coingecko:solana", {}).get("prices", [])
            for entry in prices:
                row_date = self._ts_to_date(int(entry["timestamp"]))
                if not (start_date <= row_date <= end_date):
                    continue
                result.append({"date": row_date, "value": float(entry["price"])})
            return result

        if config.get("lending_field"):
            for row_date, values in sorted(self._fetch_lending_daily().items()):
                if not (start_date <= row_date <= end_date):
                    continue
                result.append({"date": row_date, "value": values[config["lending_field"]]})
            return result

        if config.get("fees_overview"):
            raw = self._get(
                f"{self.base_url}{config['endpoint']}",
                params=config.get("params"),
            )
            for ts, value in raw.get("totalDataChart", []):
                row_date = self._ts_to_date(int(ts))
                if not (start_date <= row_date <= end_date):
                    continue
                result.append({"date": row_date, "value": float(value)})
            return result

        raw = self._get(
            f"{self.base_url}{config['endpoint']}",
            params=config.get("params"),
        )

        value_path = config.get("value_path")
        if value_path:
            for entry in raw:
                row_date = self._ts_to_date(int(entry.get("date", 0)))
                if not (start_date <= row_date <= end_date):
                    continue
                node: Any = entry
                for key in value_path:
                    node = node.get(key, {}) if isinstance(node, dict) else None
                if node is None:
                    continue
                result.append({"date": row_date, "value": float(node)})
        elif config.get("count_active_protocols"):
            chart = raw["chart"] if isinstance(raw, dict) and "chart" in raw else raw
            for ts, protocols in chart:
                row_date = self._ts_to_date(int(ts))
                if not (start_date <= row_date <= end_date):
                    continue
                count = sum(1 for v in protocols.values() if v and v > 0)
                result.append({"date": row_date, "value": float(count)})
        else:
            chart = raw["chart"] if isinstance(raw, dict) and "chart" in raw else raw
            for ts, value in chart:
                row_date = self._ts_to_date(int(ts))
                if not (start_date <= row_date <= end_date):
                    continue
                result.append({"date": row_date, "value": float(value)})

        return result

    def get_metric(
        self, metric: str, date: str, chain: str
    ) -> Defi | Overview | Stablecoin | None:
        """Fetch one metric value and return it as a typed metric model."""
        rows = self.fetch_rows(metric, date, date)
        if not rows:
            return None

        value = rows[0]["value"]
        parsed_date = datetime.date.fromisoformat(date)

        overview_metric_map = {
            "overview_sol_price": OverviewMetricType.SOL_PRICE,
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
            "defi_lending_active_loans": DefiMetricType.LENDING_ACTIVE_LOANS,
            "defi_lending_total_borrowed": DefiMetricType.LENDING_TOTAL_BORROWED,
            "defi_lending_protocol_count": DefiMetricType.LENDING_PROTOCOL_COUNT,
        }
        if metric in defi_metric_map:
            return Defi.from_metric_type(
                metric_type=defi_metric_map[metric],
                date=parsed_date,
                value=value,
            )

        stablecoin_metric_map = {
            "stablecoin_circulating_supply": StablecoinMetricType.CIRCULATING_SUPPLY,
            "stablecoin_transfer_volume": StablecoinMetricType.TRANSFER_VOLUME,
            "stablecoin_count": StablecoinMetricType.COUNT,
        }
        if metric in stablecoin_metric_map:
            return Stablecoin.from_metric_type(
                metric_type=stablecoin_metric_map[metric],
                date=parsed_date,
                value=value,
            )

        return None
