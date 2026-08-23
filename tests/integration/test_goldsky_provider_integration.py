"""Integration tests for the Goldsky provider."""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from metrics.defi import Defi, DefiMetricType
from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.goldsky import Goldsky

load_dotenv()
CLICKHOUSE_URL = os.environ.get("GOLDSKY_CLICKHOUSE_URL")


@pytest.mark.integration
def test_get_dex_transactions_live_sink() -> None:
    """Queries the ClickHouse sink directly and validates response mapping."""
    if not CLICKHOUSE_URL:
        pytest.skip("Set GOLDSKY_CLICKHOUSE_URL to run live Goldsky integration tests.")

    # The sink is backfilled sparsely, so pin a date known to be populated
    # rather than a relative one.
    provider = Goldsky()
    metric = provider.get_metric(
        metric="defi_dex_transactions",
        date="2026-08-15",
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, Defi)
    assert metric.metric_type == DefiMetricType.DEX_TRANSACTIONS
    assert metric.value >= 0


@pytest.mark.integration
def test_get_stablecoin_transfer_volume_live_sink() -> None:
    """Queries the stablecoin table directly and validates response mapping."""
    if not CLICKHOUSE_URL:
        pytest.skip("Set GOLDSKY_CLICKHOUSE_URL to run live Goldsky integration tests.")

    provider = Goldsky()
    metric = provider.get_metric(
        metric="stablecoin_transfer_volume",
        date="2026-08-23",
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, Stablecoin)
    assert metric.metric_type == StablecoinMetricType.TRANSFER_VOLUME
    assert metric.value > 0
