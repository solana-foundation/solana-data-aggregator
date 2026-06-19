"""Integration tests for the Dune provider."""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.dune import Dune

load_dotenv()
API_KEY = os.environ.get("DUNE_API_KEY")


@pytest.mark.integration
def test_get_stablecoin_supply_live_api() -> None:
    """Calls Dune API directly and validates response mapping."""
    if not API_KEY:
        pytest.skip("Set DUNE_API_KEY to run live Dune integration tests.")

    provider = Dune(api_key=API_KEY)
    metric = provider.get_metric(
        metric="stablecoin_supply",
        date="2025-01-01",
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, Stablecoin)
    assert metric.metric_type == StablecoinMetricType.SUPPLY
    assert metric.value >= 0
