"""Base metric model definitions."""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from datetime import date


@dataclass
class BaseMetric(ABC):
    """Reusable metric record that other metric classes can inherit."""

    name: str
    unit: str
    description: str
    date: date
    value: float

    def __post_init__(self) -> None:
        """Validate common metric fields."""
        if not self.name.strip():
            raise ValueError("name must be a non-empty string")
        if not self.unit.strip():
            raise ValueError("unit must be a non-empty string")
        if not self.description.strip():
            raise ValueError("description must be a non-empty string")
