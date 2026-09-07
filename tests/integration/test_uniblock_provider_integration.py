"""Integration tests for the Uniblock provider (requires UNIBLOCK_API_KEY)."""

from __future__ import annotations

import datetime
import os

import pytest
from dotenv import load_dotenv

from metrics.network import Network, NetworkMetricType
from metrics.overview import Overview, OverviewMetricType
from providers.uniblock import Uniblock

load_dotenv()
API_KEY = os.environ.get("UNIBLOCK_API_KEY")
_TODAY = datetime.date.today().isoformat()

pytestmark = pytest.mark.skipif(not API_KEY, reason="UNIBLOCK_API_KEY not set")


@pytest.mark.integration
def test_fetch_sol_price_series_live_api() -> None:
    """Calls the live Uniblock API and validates the SOL price daily series."""
    end = datetime.date.today() - datetime.timedelta(days=1)
    start = end - datetime.timedelta(days=4)
    provider = Uniblock(api_key=API_KEY)

    rows = provider.fetch_rows("overview_sol_price", start.isoformat(), end.isoformat())

    assert len(rows) > 0
    seen_dates = set()
    previous = ""
    for row in rows:
        assert isinstance(row["date"], str)
        assert isinstance(row["value"], float)
        assert row["value"] > 0
        assert start.isoformat() <= row["date"] <= end.isoformat()
        assert row["date"] not in seen_dates  # one row per day
        seen_dates.add(row["date"])
        assert row["date"] > previous  # ascending
        previous = row["date"]


@pytest.mark.integration
def test_get_metric_overview_sol_price_live_api() -> None:
    date = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
    provider = Uniblock(api_key=API_KEY)

    metric = provider.get_metric("overview_sol_price", date, "solana")

    assert metric is not None
    assert isinstance(metric, Overview)
    assert metric.metric_type == OverviewMetricType.SOL_PRICE
    assert metric.value > 0


@pytest.mark.integration
def test_get_metric_network_sol_price_live_api() -> None:
    date = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
    provider = Uniblock(api_key=API_KEY)

    metric = provider.get_metric("network_sol_price", date, "solana")

    assert metric is not None
    assert isinstance(metric, Network)
    assert metric.metric_type == NetworkMetricType.SOL_PRICE
    assert metric.value > 0


@pytest.mark.integration
def test_get_metric_total_stake_live_api() -> None:
    """getVoteAccounts stake sum should be a large positive SOL figure."""
    provider = Uniblock(api_key=API_KEY)

    metric = provider.get_metric("network_total_stake", _TODAY, "solana")

    assert metric is not None
    assert isinstance(metric, Network)
    assert metric.metric_type == NetworkMetricType.TOTAL_STAKE
    assert metric.value > 1_000_000  # hundreds of millions of SOL staked


@pytest.mark.integration
def test_get_metric_validator_count_live_api() -> None:
    provider = Uniblock(api_key=API_KEY)

    metric = provider.get_metric("network_validator_count", _TODAY, "solana")

    assert metric is not None
    assert isinstance(metric, Network)
    assert metric.metric_type == NetworkMetricType.VALIDATOR_COUNT
    assert metric.value > 100
