"""Integration tests for the Zerion provider."""

from __future__ import annotations

import datetime
import os

import pytest
from dotenv import load_dotenv

from metrics.overview import Overview, OverviewMetricType
from providers.zerion import Zerion

load_dotenv()
API_KEY = os.environ.get("ZERION_API_KEY")


@pytest.mark.integration
def test_get_sol_price_live_api() -> None:
    """Calls the Zerion API directly and validates response mapping."""
    if not API_KEY:
        pytest.skip("Set ZERION_API_KEY to run live Zerion integration tests.")

    provider = Zerion(api_key=API_KEY)
    recent_date = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
    metric = provider.get_metric(
        metric="overview_sol_price",
        date=recent_date,
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, Overview)
    assert metric.metric_type == OverviewMetricType.SOL_PRICE
    # Plausibility bound (not just > 0) to catch unit/scaling regressions.
    assert 10 < metric.value < 10_000
