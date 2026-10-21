"""Unit tests for network metric definitions."""

from __future__ import annotations

import datetime

import pytest

from metrics.network import Network, NetworkMetricType


@pytest.mark.parametrize("metric_type", list(NetworkMetricType))
def test_every_network_metric_has_metadata(metric_type) -> None:
    metric = Network.from_metric_type(
        metric_type=metric_type, date=datetime.date(2026, 10, 1), value=1.0
    )

    assert metric.name
    assert metric.unit
    assert metric.description


def test_bam_stake_share_definition() -> None:
    metric = Network.from_metric_type(
        metric_type=NetworkMetricType.BAM_STAKE_SHARE,
        date=datetime.date(2026, 10, 1),
        value=35.66,
    )

    assert NetworkMetricType.BAM_STAKE_SHARE.value == "bam_stake_share"
    assert metric.name == "BAM Stake Share"
    assert metric.unit == "Percent"
    assert metric.value == 35.66
