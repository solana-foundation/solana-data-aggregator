"""Token Terminal data provider."""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional

import requests

from metrics.defi import Defi, DefiMetricType
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
        "stablecoin_supply": {
            # Total stablecoin supply = native issuance + bridged-in supply.
            # Token Terminal exposes these as two separate metric_ids; requesting
            # both in one call and summing them yields the bridged-inclusive total.
            "metric_id": "ecosystem_stablecoin_supply,ecosystem_bridged_stablecoin_supply",
            "date_field": "timestamp",
            "value_field": [
                "ecosystem_stablecoin_supply",
                "ecosystem_bridged_stablecoin_supply",
            ],
            "methodology": (
                "Total stablecoin supply on Solana = native issuance "
                "(ecosystem_stablecoin_supply) + bridged-in supply "
                "(ecosystem_bridged_stablecoin_supply). Circulating supply excludes "
                "issuer treasury and pre-minted, not-yet-issued balances."
            ),
        },
        "defi_dex_volume": {
            "metric_id": "ecosystem_dex_trading_volume",
            "date_field": "timestamp",
            "value_field": "ecosystem_dex_trading_volume",
            "methodology": "DEX trade volume varies by indexed venues, pricing, and filtering methodology.",
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
        "stablecoin_supply": StablecoinMetricType.SUPPLY,
    }

    _DEFI_METRIC_TYPE_MAP: Dict[str, DefiMetricType] = {
        "defi_dex_volume": DefiMetricType.DEX_VOLUME,
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

    # -- BaseProvider interface ---------------------------------------------

    @property
    def provider_name(self) -> str:
        return self.name

    def fetch_rows(
        self, metric: str, start_date: str, end_date: str, **kwargs: Any
    ) -> List[Dict[str, Any]]:
        """Return normalized {"date": str, "value": float} records for the given range (both dates inclusive)."""
        config = self.METRIC_MAP[metric]
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
    ) -> Stablecoin | Overview | Defi | Network | None:
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

        network_type = self._NETWORK_METRIC_TYPE_MAP.get(metric)
        if network_type is not None:
            return Network.from_metric_type(
                metric_type=network_type, date=parsed_date, value=value
            )

        return None
