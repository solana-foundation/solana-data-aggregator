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
        "overview_fees": {
            "metric_id": "fees,price",
            "date_field": "timestamp",
            "numerator_field": "fees",
            "denominator_field": "price",
            "methodology": (
                "Daily base and priority transaction fees in SOL, including vote "
                "and failed transactions, excluding Jito tips. USD fees are "
                "divided by the same daily SOL price used for their conversion."
            ),
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
        "stablecoin_transfer_count": {
            "metric_id": "asset_transfer_count",
            "methodology": (
                "Token transfer events for covered USD-pegged stablecoins on Solana, "
                "including bridged deployments. Counts SPL and Token-2022 transfer "
                "instructions, not distinct transactions. Assets enter at their "
                "first served observation; later gaps omit the aggregate day. "
                "Assets without served counts and non-USD pegs are excluded."
            ),
        },
        "stablecoin_transfer_volume": {
            "metric_id": "asset_transfer_volume",
            "methodology": (
                "USD transfer volume for USD-pegged stablecoins covered by Token "
                "Terminal on Solana, including mint and burn flows after "
                "premint/preburn corrections. Each asset enters the aggregate "
                "at its first served Solana observation. Missing days after "
                "that observation are omitted from the aggregate. Non-USD pegs "
                "and assets without served volume are excluded."
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
        "lending_total_deposits": {
            "field": "deposits",
            "methodology": (
                "USD deposits supplied to Kamino Lend and Jupiter Lend on Solana, "
                "including borrowed liquidity. Other lending protocols are not covered."
            ),
        },
        "lending_utilization_rate": {
            "field": "utilization_rate",
            "methodology": (
                "Total borrowed divided by total supplied deposits across Kamino "
                "Lend and Jupiter Lend on Solana, multiplied by 100. Zero-deposit "
                "days are omitted. Both sums use the same covered products."
            ),
        },
        "lending_total_borrowed": {
            "field": "borrowed",
            "methodology": (
                "USD active loans from Kamino Lend and Jupiter Lend on Solana. "
                "Jupiter Lend is counted once, under Jupiter rather than Fluid."
            ),
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
        "overview_fees": OverviewMetricType.FEES,
        "overview_fee_payers": OverviewMetricType.FEE_PAYERS,
        "overview_non_vote_tx_count_success": OverviewMetricType.TX_COUNT_NON_VOTE_SUCCESS,
        "overview_non_vote_tx_count_failed": OverviewMetricType.TX_COUNT_NON_VOTE_FAILED,
        "overview_slots": OverviewMetricType.SLOTS,
        "overview_compute_units": OverviewMetricType.COMPUTE_UNITS,
    }

    _STABLECOIN_METRIC_TYPE_MAP: Dict[str, StablecoinMetricType] = {
        "stablecoin_circulating_supply": StablecoinMetricType.CIRCULATING_SUPPLY,
        "stablecoin_transfer_volume": StablecoinMetricType.TRANSFER_VOLUME,
        "stablecoin_transfer_count": StablecoinMetricType.TRANSFER_COUNT,
        "stablecoin_count": StablecoinMetricType.COUNT,
    }

    _DEFI_METRIC_TYPE_MAP: Dict[str, DefiMetricType] = {
        "defi_dex_volume": DefiMetricType.DEX_VOLUME,
        "defi_dex_count": DefiMetricType.DEX_COUNT,
    }

    _LENDING_METRIC_TYPE_MAP: Dict[str, LendingMetricType] = {
        "lending_total_borrowed": LendingMetricType.TOTAL_BORROWED,
        "lending_total_deposits": LendingMetricType.TOTAL_DEPOSITS,
        "lending_utilization_rate": LendingMetricType.UTILIZATION_RATE,
    }

    _NETWORK_METRIC_TYPE_MAP: Dict[str, NetworkMetricType] = {
        "network_validator_count": NetworkMetricType.VALIDATOR_COUNT,
    }

    BASE_URL = "https://api.tokenterminal.com/v2"
    PROJECT = "solana"
    LENDING_PRODUCTS = (("kamino", "kaminolend"), ("jupiter", "jupiterlend"))

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
        self._lending_daily: Optional[Dict[str, Dict[str, float]]] = None
        self._stablecoin_transfer_cache: Dict[str, List[Dict[str, Any]]] = {}

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
    def _response_rows(body: Any) -> List[Dict[str, Any]]:
        if isinstance(body, dict) and body.get("errors"):
            raise ValueError("Token Terminal returned partial API errors")
        rows = body.get("data") if isinstance(body, dict) else body
        if not isinstance(rows, list):
            raise ValueError("Expected Token Terminal data rows")
        return rows

    def _stablecoin_transfers(self, metric_id: str) -> List[Dict[str, Any]]:
        if metric_id in self._stablecoin_transfer_cache:
            return self._stablecoin_transfer_cache[metric_id]

        assets = []
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
            page = self._response_rows(body)
            assets.extend(page)
            offset += len(page)
            total = body.get("total_count") if isinstance(body, dict) else None
            if not page or (isinstance(total, int) and offset >= total):
                break
            if total is None and len(page) < 1000:
                break

        universe = set()
        deployments: Dict[frozenset[str], str] = {}
        seen_addresses: set[str] = set()
        for asset in assets:
            if asset.get("reference_asset_id") != "usdollar":
                continue
            addresses = frozenset(
                address["token_address"]
                for address in asset.get("addresses", [])
                if address.get("chain_id") == "solana"
            )
            if not addresses:
                continue
            if addresses in deployments:
                continue
            if seen_addresses.intersection(addresses):
                raise ValueError("Overlapping stablecoin deployments")
            deployments[addresses] = asset["asset_id"]
            seen_addresses.update(addresses)
            universe.add(asset["asset_id"])
        if not universe:
            raise ValueError("No USD-pegged Solana stablecoins found")
        if len(universe) > 300:
            raise ValueError("Stablecoin universe exceeds API asset limit")

        # Fetch available history once so a narrow window cannot hide earlier membership.
        yesterday = (
            datetime.datetime.now(datetime.timezone.utc).date()
            - datetime.timedelta(days=1)
        ).isoformat()
        rows = self._response_rows(
            self._get(
                f"/metrics/{metric_id}",
                params={
                    "asset_ids": ",".join(sorted(universe)),
                    "chain_ids": "solana",
                    "start": "2020-01-01",
                    "end": yesterday,
                },
            )
        )
        series: Dict[str, Dict[str, float]] = {}
        for row in rows:
            asset_id = row["asset_id"]
            if asset_id not in universe or row.get("chain_id") != "solana":
                raise ValueError(
                    "Unexpected asset or chain in stablecoin transfer data"
                )
            date = str(row["timestamp"])[:10]
            datetime.date.fromisoformat(date)
            if row.get("value") is None:
                continue
            value = float(row["value"])
            if not math.isfinite(value) or value < 0:
                raise ValueError("Invalid stablecoin transfer data")
            daily = series.setdefault(asset_id, {})
            if date in daily:
                raise ValueError("Duplicate daily stablecoin transfer data")
            daily[date] = value

        for asset_id in universe - series.keys():
            detail = self._get(f"/assets/{asset_id}")
            if detail.get("errors"):
                raise ValueError("Token Terminal returned asset availability errors")
            available = detail.get("data", {}).get("available_metrics")
            if not isinstance(available, list) or metric_id in available:
                raise ValueError(f"Missing Solana transfer history for {asset_id}")

        first_dates = {asset: min(daily) for asset, daily in series.items()}
        dates = sorted({date for daily in series.values() for date in daily})
        result = []
        for date in dates:
            members = [asset for asset, first in first_dates.items() if first <= date]
            if all(date in series[asset] for asset in members):
                result.append(
                    {
                        "date": date,
                        "value": sum(series[asset][date] for asset in members),
                    }
                )
        self._stablecoin_transfer_cache[metric_id] = result
        return result

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

    def _fetch_lending_daily(self) -> Dict[str, Dict[str, float]]:
        if self._lending_daily is not None:
            return self._lending_daily
        yesterday = (
            datetime.datetime.now(datetime.timezone.utc).date()
            - datetime.timedelta(days=1)
        ).isoformat()
        series: Dict[str, Dict[str, Dict[str, float]]] = {}
        for project, product in self.LENDING_PRODUCTS:
            body = self._get(
                f"/projects/{project}/products/{product}/metrics",
                params={
                    "metric_ids": "tvl,active_loans",
                    "chain_ids": "solana",
                    "start": "2020-01-01",
                    "end": yesterday,
                },
            )
            if isinstance(body, dict) and body.get("errors"):
                raise ValueError(f"Incomplete lending API response for {product}")
            rows = body.get("data") if isinstance(body, dict) else body
            if not isinstance(rows, list):
                raise ValueError(f"Missing lending rows for {product}")
            daily = {}
            for row in rows:
                date = str(row.get("timestamp", ""))[:10]
                datetime.date.fromisoformat(date)
                if row.get("chain_id") != "solana" or row.get("product_id") != product:
                    raise ValueError(f"Unexpected lending dimensions for {product}")
                if row.get("tvl") is None or row.get("active_loans") is None:
                    continue
                deposits, borrowed = float(row["tvl"]), float(row["active_loans"])
                if not all(math.isfinite(v) and v >= 0 for v in (deposits, borrowed)):
                    raise ValueError(f"Invalid lending balances for {product}")
                if date in daily:
                    raise ValueError(f"Duplicate lending day for {product}")
                daily[date] = {"deposits": deposits, "borrowed": borrowed}
            if not daily:
                raise ValueError(f"No complete lending history for {product}")
            series[product] = daily

        first_dates = {product: min(daily) for product, daily in series.items()}
        dates = sorted({date for daily in series.values() for date in daily})
        result = {}
        for date in dates:
            products = [
                product for product, first in first_dates.items() if first <= date
            ]
            if not all(date in series[product] for product in products):
                continue
            deposits = sum(series[p][date]["deposits"] for p in products)
            borrowed = sum(series[p][date]["borrowed"] for p in products)
            values = {
                "deposits": deposits,
                "borrowed": borrowed,
            }
            if deposits > 0:
                values["utilization_rate"] = borrowed / deposits * 100
            result[date] = values
        self._lending_daily = result
        return result

    # -- BaseProvider interface ---------------------------------------------

    @property
    def provider_name(self) -> str:
        return self.name

    def fetch_rows(
        self, metric: str, start_date: str, end_date: str, **kwargs: Any
    ) -> List[Dict[str, Any]]:
        """Return normalized {"date": str, "value": float} records for the given range (both dates inclusive)."""
        config = self.METRIC_MAP[metric]
        if metric in self._LENDING_METRIC_TYPE_MAP:
            field = config["field"]
            return [
                {"date": date, "value": values[field]}
                for date, values in sorted(self._fetch_lending_daily().items())
                if start_date <= date <= end_date and field in values
            ]
        if metric in ("defi_dex_count", "stablecoin_count"):
            return self._fetch_count_rows(metric, start_date, end_date)
        if metric in ("stablecoin_transfer_volume", "stablecoin_transfer_count"):
            return [
                row
                for row in self._stablecoin_transfers(config["metric_id"])
                if start_date <= row["date"] <= end_date
            ]
        # A metric may map to one or more Token Terminal metric_ids. When several
        # are provided (e.g. native + bridged stablecoin supply), their per-day
        # values are summed into a single figure.
        numerator_field = config.get("numerator_field")
        denominator_field = config.get("denominator_field")
        if numerator_field is None:
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
            if numerator_field is not None:
                numerator = row.get(numerator_field)
                denominator = row.get(denominator_field)
                if numerator is None or denominator is None:
                    continue
                denominator_value = float(denominator)
                if denominator_value <= 0:
                    continue
                result.append(
                    {
                        "date": row_date,
                        "value": float(numerator) / denominator_value,
                    }
                )
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
