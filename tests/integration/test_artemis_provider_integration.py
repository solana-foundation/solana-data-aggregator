"""Integration tests for the Artemis provider."""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.artemis import Artemis

load_dotenv()
API_KEY = os.environ.get("ARTEMIS_API_KEY")


@pytest.mark.integration
def test_get_stablecoin_supply_live_api() -> None:
    """Calls Artemis API directly and validates response mapping."""
    if not API_KEY:
        pytest.skip("Set ARTEMIS_API_KEY to run live Artemis integration tests.")

    provider = Artemis(api_key=API_KEY)
    metric = provider.get_metric(
        metric="stablecoin_supply",
        date="2025-01-01",
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, Stablecoin)
    assert metric.metric_type == StablecoinMetricType.SUPPLY
    assert metric.value >= 0
