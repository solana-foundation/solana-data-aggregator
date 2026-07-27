"""Integration tests for the Solana Compass provider."""

from __future__ import annotations

import pytest

from metrics.defi import Defi, DefiMetricType
from metrics.overview import Overview, OverviewMetricType
from providers.solana_compass import SolanaCompass


@pytest.mark.integration
def test_get_vote_transaction_count_live_api() -> None:
    """Calls the Solana Compass public API and validates overview mapping."""
    provider = SolanaCompass()
    metric = provider.get_metric(
        metric="overview_tx_count_vote",
        date="2026-06-29",
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, Overview)
    assert metric.metric_type == OverviewMetricType.TX_COUNT_VOTE
    assert metric.value > 0


@pytest.mark.integration
def test_fetch_dex_volume_range_live_api() -> None:
    """Range fetch should use one API request and return daily DEX rows."""
    provider = SolanaCompass()
    rows = provider.fetch_rows(
        metric="defi_dex_volume",
        start_date="2026-06-29",
        end_date="2026-06-30",
    )

    assert len(rows) == 2
    assert [row["date"] for row in rows] == ["2026-06-29", "2026-06-30"]
    assert all(row["value"] > 0 for row in rows)

    metric = provider.get_metric(
        metric="defi_dex_volume",
        date="2026-06-29",
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, Defi)
    assert metric.metric_type == DefiMetricType.DEX_VOLUME
    assert metric.value > 0
