from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, List

from metrics.base import BaseMetric


def stablecoin_supply_rows(
    raw_rows: Iterable[Dict[str, Any]],
    *,
    date_field: str,
    mint_field: str,
    token_field: str,
    value_field: str,
    start_date: str,
    end_date: str,
) -> List[Dict[str, Any]]:
    """Normalize per-token supply rows to {"date", "mint_address", "token", "value"}.

    Shared by the providers' fetch_stablecoin_supply_by_token. Rows outside
    [start_date, end_date], without a mint, or without a positive value are
    dropped (a supply of zero or less means no circulating supply, or bad
    data); token is upper-cased (None when the provider gives no symbol).
    """
    result = []
    for row in raw_rows:
        row_date = str(row.get(date_field, ""))[:10]
        mint = row.get(mint_field)
        value = row.get(value_field)
        if not row_date or not (start_date <= row_date <= end_date):
            continue
        if not mint or value is None or float(value) <= 0:
            continue
        token = row.get(token_field)
        result.append(
            {
                "date": row_date,
                "mint_address": str(mint),
                "token": str(token).upper() if token else None,
                "value": float(value),
            }
        )
    return result


class BaseProvider(ABC):
    """Base interface all providers must implement."""

    def __init__(self, name: str, base_url: str, api_key: str) -> None:
        self.name = name
        self.base_url = base_url
        self.api_key = api_key

    @abstractmethod
    def get_metric(self, metric: str, date: str, chain: str) -> BaseMetric | None:
        """Fetch one metric for one date and chain from provider API."""

    @abstractmethod
    def fetch_rows(
        self, metric: str, start_date: str, end_date: str, **kwargs: Any
    ) -> List[Dict[str, Any]]:
        """Return normalized {"date": str, "value": Any} records for the given range (start_date and end_date are both inclusive)."""
