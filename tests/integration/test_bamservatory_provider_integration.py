"""Integration tests for the BAMservatory provider."""

from __future__ import annotations

import datetime

import pytest

from metrics.network import Network, NetworkMetricType
from providers.bamservatory import Bamservatory


@pytest.mark.integration
def test_get_bam_stake_share_live_api() -> None:
    """Calls the BAMservatory endpoint directly and validates response mapping."""
    today = datetime.date.today()
    start = (today - datetime.timedelta(days=7)).isoformat()
    provider = Bamservatory()

    rows = provider.fetch_rows("network_bam_stake_share", start, today.isoformat())
    assert rows, "expected at least one completed day in the last week"
    assert all(0 < row["value"] < 100 for row in rows)

    metric = provider.get_metric(
        metric="network_bam_stake_share",
        date=rows[-1]["date"],
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, Network)
    assert metric.metric_type == NetworkMetricType.BAM_STAKE_SHARE
    assert metric.value == rows[-1]["value"]
