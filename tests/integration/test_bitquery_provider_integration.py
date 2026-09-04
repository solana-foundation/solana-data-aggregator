"""Integration tests for the Bitquery provider."""

from __future__ import annotations

import datetime
import os

import pytest
from dotenv import load_dotenv

from metrics.defi import Defi, DefiMetricType
from metrics.overview import Overview, OverviewMetricType
from providers.bitquery import Bitquery

load_dotenv()
API_KEY = os.environ.get("BITQUERY_API_KEY")

_YESTERDAY = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

pytestmark = pytest.mark.skipif(not API_KEY, reason="BITQUERY_API_KEY not set")


@pytest.mark.integration
def test_get_sol_price_live_api() -> None:
    """SOL price for Solana should be a positive USD value."""
    provider = Bitquery(api_key=API_KEY)
    metric = provider.get_metric("overview_sol_price", _YESTERDAY, "solana")

    assert metric is not None
    assert isinstance(metric, Overview)
    assert metric.metric_type == OverviewMetricType.SOL_PRICE
    assert metric.value > 0


@pytest.mark.integration
def test_get_dex_volume_live_api() -> None:
    """Daily Solana DEX volume should be a positive USD value."""
    provider = Bitquery(api_key=API_KEY)
    metric = provider.get_metric("defi_dex_volume", _YESTERDAY, "solana")

    assert metric is not None
    assert isinstance(metric, Defi)
    assert metric.metric_type == DefiMetricType.DEX_VOLUME
    assert metric.value > 0


@pytest.mark.integration
def test_fetch_rows_three_day_range_live_api() -> None:
    """A multi-day range should return one row per day inside the range."""
    provider = Bitquery(api_key=API_KEY)
    start = (datetime.date.today() - datetime.timedelta(days=3)).isoformat()
    rows = provider.fetch_rows("defi_dex_transactions", start, _YESTERDAY)

    assert len(rows) == 3
    dates = [row["date"] for row in rows]
    assert dates == sorted(dates)
    assert all(start <= d <= _YESTERDAY for d in dates)
    assert all(row["value"] > 0 for row in rows)
