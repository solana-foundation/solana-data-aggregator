"""Integration tests for the Stakewiz provider."""

from __future__ import annotations

import datetime

import pytest

from metrics.network import Network, NetworkMetricType
from providers.stakewiz import Stakewiz


@pytest.mark.integration
def test_get_total_stake_live_api() -> None:
    """Calls Stakewiz API directly and validates response mapping."""
    today = datetime.date.today().isoformat()
    provider = Stakewiz()
    metric = provider.get_metric(
        metric="network_total_stake",
        date=today,
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, Network)
    assert metric.metric_type == NetworkMetricType.TOTAL_STAKE
    assert metric.value > 0
