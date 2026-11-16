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
        "lending_protocol_count": {
            "field": "protocol_count",
            "methodology": (
                "Number of covered lending protocols with positive supplied "
                "deposits on Solana that day: Kamino Lend and Jupiter Lend."
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
        "overview_fee_payers": OverviewMetricType.FEE_PAYERS,
        "overview_non_vote_tx_count_success": OverviewMetricType.TX_COUNT_NON_VOTE_SUCCESS,
        "overview_non_vote_tx_count_failed": OverviewMetricType.TX_COUNT_NON_VOTE_FAILED,
        "overview_slots": OverviewMetricType.SLOTS,
        "overview_compute_units": OverviewMetricType.COMPUTE_UNITS,
    }

    _STABLECOIN_METRIC_TYPE_MAP: Dict[str, StablecoinMetricType] = {
        "stablecoin_circulating_supply": StablecoinMetricType.CIRCULATING_SUPPLY,
    }

    _DEFI_METRIC_TYPE_MAP: Dict[str, DefiMetricType] = {
        "defi_dex_volume": DefiMetricType.DEX_VOLUME,
    }

    _LENDING_METRIC_TYPE_MAP: Dict[str, LendingMetricType] = {
        "lending_total_borrowed": LendingMetricType.TOTAL_BORROWED,
        "lending_total_deposits": LendingMetricType.TOTAL_DEPOSITS,
        "lending_utilization_rate": LendingMetricType.UTILIZATION_RATE,
        "lending_protocol_count": LendingMetricType.PROTOCOL_COUNT,
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
                "protocol_count": float(
                    sum(series[p][date]["deposits"] > 0 for p in products)
                ),
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
