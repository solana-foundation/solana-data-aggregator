"""Integration tests for the Birdeye provider."""

from __future__ import annotations

import os
import datetime
from dotenv import load_dotenv
import pytest

from metrics.defi import Defi, DefiMetricType
from metrics.overview import Overview, OverviewMetricType
from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.birdeye import Birdeye

load_dotenv()
API_KEY = os.environ.get("BIRDEYE_API_KEY")

_TODAY = datetime.date.today().isoformat()

@pytest.mark.integration
def test_get_sol_price_live_api() -> None:
    """SOL price for Solana should be a positive USD value."""
    provider = Birdeye(api_key=API_KEY)
    metric = provider.get_metric(
        metric="overview_sol_price",
        date=_TODAY,
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, Overview)
    assert metric.metric_type == OverviewMetricType.SOL_PRICE
    assert metric.value > 0

@pytest.mark.integration
def test_get_stablecoin_supply_live_api() -> None:
    """Stablecoin supply for Solana should be a positive value."""
    provider = Birdeye(api_key=API_KEY)
    metric = provider.get_metric(
        metric="stablecoin_supply",
        date=_TODAY,
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, Stablecoin)
    assert metric.metric_type == StablecoinMetricType.SUPPLY
    assert metric.value > 0

@pytest.mark.integration
def test_get_dex_volume_live_api() -> None:
    """Calls the Birdeye public API directly and validates response mapping."""
    provider = Birdeye(api_key=API_KEY)
    metric = provider.get_metric(
        metric="defi_dex_volume",
        date=_TODAY,
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, Defi)
    assert metric.metric_type == DefiMetricType.DEX_VOLUME
    assert metric.value > 0


@pytest.mark.integration
def test_get_dex_transactions_live_api() -> None:
    """Confirms the txns_24h response key exists and maps end-to-end."""
    provider = Birdeye(api_key=API_KEY)
    metric = provider.get_metric(
        metric="defi_dex_transactions",
        date=_TODAY,
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, Defi)
    assert metric.metric_type == DefiMetricType.DEX_TRANSACTIONS
    assert metric.value > 0

