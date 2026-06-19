from abc import ABC, abstractmethod
from typing import Any, Dict, List

from metrics.base import BaseMetric


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
