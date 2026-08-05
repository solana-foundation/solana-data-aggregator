"""Integration tests for the Goldsky provider."""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from metrics.defi import Defi, DefiMetricType
from providers.goldsky import Goldsky

load_dotenv()
CLICKHOUSE_URL = os.environ.get("GOLDSKY_CLICKHOUSE_URL")


@pytest.mark.integration
def test_get_dex_transactions_live_sink() -> None:
    """Queries the ClickHouse sink directly and validates response mapping."""
    if not CLICKHOUSE_URL:
        pytest.skip("Set GOLDSKY_CLICKHOUSE_URL to run live Goldsky integration tests.")

    provider = Goldsky()
    metric = provider.get_metric(
        metric="defi_dex_transactions",
        date="2026-01-01",
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, Defi)
    assert metric.metric_type == DefiMetricType.DEX_TRANSACTIONS
    assert metric.value >= 0
