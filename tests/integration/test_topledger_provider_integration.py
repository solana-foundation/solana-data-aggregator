"""Integration tests for the Top Ledger provider (requires TOPLEDGER_API_KEY)."""

from __future__ import annotations

import datetime

import pytest

from metrics.overview import Overview, OverviewMetricType
from providers.topledger import TopLedger


@pytest.mark.integration
def test_fetch_non_vote_success_live_api() -> None:
    """Calls the Top Ledger Redash API and validates overview_non_vote_tx_count_success."""
    end = datetime.date.today() - datetime.timedelta(days=2)
    start = end - datetime.timedelta(days=6)
    provider = TopLedger()

    rows = provider.fetch_rows(
        "overview_non_vote_tx_count_success",
        start.isoformat(),
        end.isoformat(),
    )

    assert len(rows) > 0
    for row in rows:
        assert "date" in row
        assert "value" in row
        assert isinstance(row["value"], float)
        assert row["value"] > 0


@pytest.mark.integration
def test_get_metric_overview_slots_live_api() -> None:
    """Calls the live API and checks overview_slots returns a typed Overview model."""
    date = (datetime.date.today() - datetime.timedelta(days=3)).isoformat()
    provider = TopLedger()

    metric = provider.get_metric("overview_slots", date, "solana")

    assert metric is not None
    assert isinstance(metric, Overview)
    assert metric.metric_type == OverviewMetricType.SLOTS
    assert metric.value > 0


@pytest.mark.integration
def test_cache_prevents_duplicate_api_calls() -> None:
    """Metrics sharing the same query_id should hit the API only once per date range."""
    date = "2026-06-15"
    provider = TopLedger()

    overview_metrics = [
        m for m, cfg in provider.METRIC_MAP.items() if cfg["query_id"] == 15088
    ]
    for metric in overview_metrics:
        provider.fetch_rows(metric, date, date)

    assert len(provider._cache) == 1
