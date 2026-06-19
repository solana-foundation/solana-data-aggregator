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
        "stablecoin_supply": {
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
    }

    BASE_URL = "https://pro-api.llama.fi"

    def __init__(self, *, api_key: Optional[str] = None) -> None:
        resolved_api_key = api_key or os.environ.get("DEFILLAMA_API_KEY") or ""
        super().__init__(
            name="DefiLlama",
            base_url=self.BASE_URL,
            api_key=resolved_api_key,
        )
        self._session = requests.Session()

    # -- private helpers ----------------------------------------------------

    def _get(self, url: str, *, params: Optional[Dict[str, Any]] = None) -> Any:
        if self.api_key:
            url = url.replace(self.BASE_URL, f"{self.BASE_URL}/{self.api_key}", 1)
        resp = self._session.get(url, params=params or {}, timeout=30)
        resp.raise_for_status()
        return resp.json()

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
                .replace(tzinfo=datetime.timezone.utc)
                .timestamp()
            )
            span = min(
                (
                    datetime.date.fromisoformat(end_date)
                    - datetime.date.fromisoformat(start_date)
                ).days
                + 1,
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

        stablecoin_metric_map = {
            "stablecoin_supply": StablecoinMetricType.SUPPLY,
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
