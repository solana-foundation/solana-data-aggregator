"""Integration tests for the Solscan provider."""

from __future__ import annotations

import datetime
import os

import pytest
from dotenv import load_dotenv

from metrics.defi import Defi, DefiMetricType
from metrics.network import Network, NetworkMetricType
from metrics.overview import Overview, OverviewMetricType
from providers.solscan import Solscan

load_dotenv()
API_KEY = os.environ.get("SOLSCAN_API_KEY")

# Daily rollups lag by ~1 day
YESTERDAY = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()


@pytest.mark.integration
def test_get_overview_tx_count_total_live_api() -> None:
    """Calls the Solscan /analytics/transactions endpoint and validates response mapping."""
    if not API_KEY:
        pytest.skip("Set SOLSCAN_API_KEY to run live Solscan integration tests.")

    provider = Solscan(api_key=API_KEY)
    metric = provider.get_metric(
        metric="overview_tx_count_total",
        date=YESTERDAY,
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, Overview)
    assert metric.metric_type == OverviewMetricType.TX_COUNT_TOTAL
    assert metric.value > 0


@pytest.mark.integration
def test_get_defi_dex_volume_live_api() -> None:
    """Calls the Solscan /analytics/dex/activity endpoint and validates response mapping."""
    if not API_KEY:
        pytest.skip("Set SOLSCAN_API_KEY to run live Solscan integration tests.")

    provider = Solscan(api_key=API_KEY)
    metric = provider.get_metric(
        metric="defi_dex_volume",
        date=YESTERDAY,
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, Defi)
    assert metric.metric_type == DefiMetricType.DEX_VOLUME
    assert metric.value >= 0


@pytest.mark.integration
def test_get_network_total_stake_live_api() -> None:
    """Calls the Solscan /analytics/stake endpoint and validates response mapping."""
    if not API_KEY:
        pytest.skip("Set SOLSCAN_API_KEY to run live Solscan integration tests.")

    provider = Solscan(api_key=API_KEY)
    metric = provider.get_metric(
        metric="network_total_stake",
        date=YESTERDAY,
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, Network)
    assert metric.metric_type == NetworkMetricType.TOTAL_STAKE
    assert metric.value > 0


@pytest.mark.integration
def test_fetch_rows_returns_week_of_data_live_api() -> None:
    """Calls the Solscan /analytics/compute-units endpoint over a multi-day range."""
    if not API_KEY:
        pytest.skip("Set SOLSCAN_API_KEY to run live Solscan integration tests.")

    provider = Solscan(api_key=API_KEY)
    start = (datetime.date.today() - datetime.timedelta(days=8)).isoformat()
    rows = provider.fetch_rows("overview_compute_units", start, YESTERDAY)

    assert len(rows) > 0
    for row in rows:
        assert start <= row["date"] <= YESTERDAY
        assert row["value"] >= 0
