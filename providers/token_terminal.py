"""Token Terminal data provider."""

from __future__ import annotations

import datetime
import os
import math
from typing import Any, Dict, List, Optional

import requests

from metrics.defi import Defi, DefiMetricType
from metrics.lending import Lending, LendingMetricType
from metrics.network import Network, NetworkMetricType
from metrics.overview import Overview, OverviewMetricType
from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.base import BaseProvider


class TokenTerminal(BaseProvider):
    """Fetch metrics from the Token Terminal v2 API."""

    METRIC_MAP: Dict[str, Dict[str, Any]] = {
        "overview_tx_count_total": {
            "metric_id": "transaction_count",
            "date_field": "timestamp",
            "value_field": "transaction_count",
        },
        "overview_tx_count_vote": {
            "metric_id": "vote_transaction_count",
            "date_field": "timestamp",
            "value_field": "vote_transaction_count",
        },
        "overview_sol_price": {
            "metric_id": "price",
            "date_field": "timestamp",
            "value_field": "price",
        },
        "overview_fee_payers": {
            "metric_id": "active_addresses_daily",
            "date_field": "timestamp",
            "value_field": "active_addresses_daily",
        },
        "overview_non_vote_tx_count_success": {
            "metric_id": "successful_non_vote_transaction_count",
            "date_field": "timestamp",
            "value_field": "successful_non_vote_transaction_count",
            "methodology": (
                "Non-vote transactions that executed without error, aggregated from "
                "the per-block counts Solana records. Sums with the failed count to "
                "the total non-vote transaction count."
            ),
        },
        "overview_non_vote_tx_count_failed": {
            "metric_id": "failed_non_vote_transaction_count",
            "date_field": "timestamp",
            "value_field": "failed_non_vote_transaction_count",
            "methodology": (
                "Non-vote transactions that reverted with an error. They were "
                "included in a block and paid a fee, so this counts wasted execution "
                "rather than dropped demand."
            ),
        },
        "overview_slots": {
            "metric_id": "slot_count",
            "date_field": "timestamp",
            "value_field": "slot_count",
            "methodology": (
                "Slots in which a leader produced a block. Skipped slots are "
                "excluded, so the shortfall against the slot schedule is the leader "
                "skip rate."
            ),
        },
        "overview_compute_units": {
            "metric_id": "compute_units_per_block",
            "date_field": "timestamp",
            "value_field": "compute_units_per_block",
            "methodology": (
                "Average compute units consumed per produced block. Both successful "
                "and failed non-vote transactions count, since failed transactions "
                "still consume compute. Blocks carrying no transactions remain in "
                "the denominator because they still occupied a slot."
            ),
        },
        "stablecoin_circulating_supply": {
            # Token Terminal's ecosystem_stablecoin_supply is the sum of each
            # issuer's outstanding supply, which excludes issuer treasury and
            # pre-minted, not-yet-issued balances -- i.e. circulating supply, not
            # total supply. Bridged-in stablecoins are tracked as a separate
            # metric_id (ecosystem_bridged_stablecoin_supply); requesting both in
            # one call and summing them yields the bridged-inclusive circulating
            # total on Solana.
            "metric_id": "ecosystem_stablecoin_supply,ecosystem_bridged_stablecoin_supply",
            "date_field": "timestamp",
            "value_field": [
                "ecosystem_stablecoin_supply",
                "ecosystem_bridged_stablecoin_supply",
            ],
            "methodology": (
                "Circulating stablecoin supply on Solana = native issuance "
                "(ecosystem_stablecoin_supply) + bridged-in supply "
                "(ecosystem_bridged_stablecoin_supply). Excludes issuer treasury "
                "and pre-minted, not-yet-issued balances."
            ),
        },
        "defi_dex_count": {
            "metric_id": "trading_volume",
            "methodology": (
                "Number of Token Terminal-covered exchange protocols with "
                "positive spot trading volume on Solana that day, excluding "
                "derivatives and DEX aggregators. Each project is counted once."
            ),
        },
        "stablecoin_count": {
            "metric_id": "asset_market_cap_circulating",
            "methodology": (
                "Number of Token Terminal-covered USD-pegged stablecoin assets "
                "with positive circulating market cap on Solana that day. "
                "Includes bridged deployments; each asset is counted once."
            ),
        },
        "defi_dex_volume": {
            "metric_id": "ecosystem_dex_trading_volume",
            "date_field": "timestamp",
            "value_field": "ecosystem_dex_trading_volume",
            "methodology": "DEX trade volume varies by indexed venues, pricing, and filtering methodology.",
        },
        "lending_total_borrowed": {
            "metric_id": "ecosystem_active_loans",
            "date_field": "timestamp",
            "value_field": "ecosystem_active_loans",
        },
        "network_validator_count": {
            "metric_id": "number_of_validators",
            "date_field": "timestamp",
            "value_field": "number_of_validators",
            "methodology": (
                "Validators are counted from Solana's native rewards system: an "
                "address counts for a day if it received a voting reward on that "
                "day, which only happens for validators taking part in consensus. "
                "Validators that were delinquent for the whole day therefore drop "
                "out of the count."
            ),
        },
    }

    _OVERVIEW_METRIC_TYPE_MAP: Dict[str, OverviewMetricType] = {
        "overview_tx_count_total": OverviewMetricType.TX_COUNT_TOTAL,
        "overview_tx_count_vote": OverviewMetricType.TX_COUNT_VOTE,
        "overview_sol_price": OverviewMetricType.SOL_PRICE,
        "overview_fee_payers": OverviewMetricType.FEE_PAYERS,
        "overview_non_vote_tx_count_success": OverviewMetricType.TX_COUNT_NON_VOTE_SUCCESS,
        "overview_non_vote_tx_count_failed": OverviewMetricType.TX_COUNT_NON_VOTE_FAILED,
        "overview_slots": OverviewMetricType.SLOTS,
        "overview_compute_units": OverviewMetricType.COMPUTE_UNITS,
    }

    _STABLECOIN_METRIC_TYPE_MAP: Dict[str, StablecoinMetricType] = {
        "stablecoin_circulating_supply": StablecoinMetricType.CIRCULATING_SUPPLY,
        "stablecoin_count": StablecoinMetricType.COUNT,
    }

    _DEFI_METRIC_TYPE_MAP: Dict[str, DefiMetricType] = {
        "defi_dex_volume": DefiMetricType.DEX_VOLUME,
        "defi_dex_count": DefiMetricType.DEX_COUNT,
    }

    _LENDING_METRIC_TYPE_MAP: Dict[str, LendingMetricType] = {
        "lending_total_borrowed": LendingMetricType.TOTAL_BORROWED,
    }

    _NETWORK_METRIC_TYPE_MAP: Dict[str, NetworkMetricType] = {
        "network_validator_count": NetworkMetricType.VALIDATOR_COUNT,
    }

    BASE_URL = "https://api.tokenterminal.com/v2"
    PROJECT = "solana"

    def __init__(self, *, api_key: Optional[str] = None) -> None:
        resolved_api_key = api_key or self._resolve_api_key()
        if not resolved_api_key:
            raise ValueError("API key is required")
        super().__init__(
            name="TokenTerminal",
            base_url=self.BASE_URL,
            api_key=resolved_api_key,
        )
        self._session = requests.Session()

    # -- private helpers ----------------------------------------------------

    @staticmethod
    def _resolve_api_key() -> Optional[str]:
        return os.environ.get("TOKEN_TERMINAL_API_KEY")

    def _get(self, endpoint: str, *, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }
        resp = self._session.get(url, headers=headers, params=params or {}, timeout=60)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _count_data(body: Any) -> Any:
        if not isinstance(body, dict) or body.get("errors") or "data" not in body:
            raise ValueError("Incomplete Token Terminal count response")
        return body["data"]

    def _fetch_count_rows(
        self, metric: str, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        params = {"chain_ids": "solana", "start": start_date, "end": end_date}
        if metric == "defi_dex_count":
            sectors = {}
            for sector in ("exchange", "derivatives", "dex-aggregators"):
                data = self._count_data(self._get(f"/market-sectors/{sector}"))
                projects = data.get("projects") if isinstance(data, dict) else None
                if not isinstance(projects, list):
                    raise ValueError("Missing market-sector project list")
                sectors[sector] = {row["project_id"] for row in projects}
            universe = (
                sectors["exchange"]
                - sectors["derivatives"]
                - sectors["dex-aggregators"]
            )
            entity_field = "project_id"
            params["project_ids"] = "all"
        else:
            universe = set()
            offset = 0
            while True:
                body = self._get(
                    "/assets",
                    params={
                        "asset_types": "stablecoin",
                        "reference_asset_ids": "usdollar",
                        "limit": 1000,
                        "offset": offset,
                    },
                )
                page = self._count_data(body)
                if not isinstance(page, list):
                    raise ValueError("Missing stablecoin asset list")
                for asset in page:
                    if asset.get("reference_asset_id") == "usdollar" and any(
                        address.get("chain_id") == "solana"
                        for address in asset.get("addresses", [])
                    ):
                        universe.add(asset["asset_id"])
                offset += len(page)
                total = body.get("total_count")
                if not page or (isinstance(total, int) and offset >= total):
                    break
                if total is None and len(page) < 1000:
                    break
            if not universe or len(universe) > 300:
                raise ValueError(
                    "Stablecoin count universe is empty or exceeds API limit"
                )
            entity_field = "asset_id"
            params["asset_ids"] = ",".join(sorted(universe))
            params["assets_bridged"] = "true"

        rows = self._count_data(
            self._get(
                f"/metrics/{self.METRIC_MAP[metric]['metric_id']}",
                params=params,
            )
        )
        if not isinstance(rows, list):
            raise ValueError("Missing count metric rows")
        daily: Dict[str, set[str]] = {}
        for row in rows:
            date = str(row.get("timestamp", ""))[:10]
            if not start_date <= date <= end_date:
                continue
            if row.get("chain_id") != "solana":
                raise ValueError("Unexpected chain in count metric rows")
            entity = row[entity_field]
            if entity not in universe:
                continue
            if row.get("value") is None:
                raise ValueError("Missing count metric value")
            value = float(row["value"])
            if not math.isfinite(value) or value < 0:
                raise ValueError("Invalid count metric value")
            daily.setdefault(date, set())
            if value > 0:
                daily[date].add(entity)
        return [
            {"date": date, "value": len(entities)}
            for date, entities in sorted(daily.items())
        ]

    # -- BaseProvider interface ---------------------------------------------

    @property
    def provider_name(self) -> str:
        return self.name

    def fetch_rows(
        self, metric: str, start_date: str, end_date: str, **kwargs: Any
    ) -> List[Dict[str, Any]]:
        """Return normalized {"date": str, "value": float} records for the given range (both dates inclusive)."""
        config = self.METRIC_MAP[metric]
        if metric in ("defi_dex_count", "stablecoin_count"):
            return self._fetch_count_rows(metric, start_date, end_date)
        # A metric may map to one or more Token Terminal metric_ids. When several
        # are provided (e.g. native + bridged stablecoin supply), their per-day
        # values are summed into a single figure.
        value_fields = config["value_field"]
        if isinstance(value_fields, str):
            value_fields = [value_fields]
        body = self._get(
            f"/projects/{self.PROJECT}/metrics",
            params={
                "metric_ids": config["metric_id"],
                "start": start_date,
                "end": end_date,
                "granularity": "day",
            },
        )
        raw = body if isinstance(body, list) else body.get("data", [])
        result = []
        for row in raw:
            row_date = str(row.get(config["date_field"], ""))[:10]
            if not row_date or not (start_date <= row_date <= end_date):
                continue
            # Sum the values that are present for this day. If one series has no
            # value for a date (e.g. bridged supply on dates before any bridged
            # stablecoins existed on the chain), the absent series is treated as
            # zero and the day still reports the available total. Only days with
            # no values at all for any requested metric are dropped.
            present = [row.get(field) for field in value_fields]
            present = [v for v in present if v is not None]
            if not present:
                continue
            value = sum(float(v) for v in present)
            result.append({"date": row_date, "value": value})
        return result

    def get_metric(
        self, metric: str, date: str, chain: str
    ) -> Stablecoin | Overview | Defi | Lending | Network | None:
        """Fetch one metric value and return it as a typed metric model."""
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

        stablecoin_type = self._STABLECOIN_METRIC_TYPE_MAP.get(metric)
        if stablecoin_type is not None:
            return Stablecoin.from_metric_type(
                metric_type=stablecoin_type, date=parsed_date, value=value
            )

        defi_type = self._DEFI_METRIC_TYPE_MAP.get(metric)
        if defi_type is not None:
            return Defi.from_metric_type(
                metric_type=defi_type, date=parsed_date, value=value
            )

        lending_type = self._LENDING_METRIC_TYPE_MAP.get(metric)
        if lending_type is not None:
            return Lending.from_metric_type(
                metric_type=lending_type, date=parsed_date, value=value
            )

        network_type = self._NETWORK_METRIC_TYPE_MAP.get(metric)
        if network_type is not None:
            return Network.from_metric_type(
                metric_type=network_type, date=parsed_date, value=value
            )

        return None
