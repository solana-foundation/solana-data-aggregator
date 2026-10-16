"""Unit tests for the BAMservatory provider."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest

from metrics.network import Network, NetworkMetricType
from providers.bamservatory import Bamservatory

_METRICS_RAW = {
    "schemaVersion": 5,
    "daily": [
        {"date": "2026-09-30", "bamStakePct": 35.5243, "captures": 1470},
        {"date": "2026-10-01", "bamStakePct": 35.6567, "captures": 1468},
        {"date": "2026-10-02", "bamStakePct": 37.5053, "captures": 1474},
    ],
}


def _mock_resp(payload):
    m = MagicMock()
    m.json.return_value = payload
    m.raise_for_status = MagicMock()
    return m


def test_fetch_rows_returns_inclusive_range_from_one_request() -> None:
    provider = Bamservatory()

    with patch.object(
        provider._session, "get", return_value=_mock_resp(_METRICS_RAW)
    ) as mock_get:
        rows = provider.fetch_rows(
            "network_bam_stake_share", "2026-10-01", "2026-10-02"
        )

    assert rows == [
        {"date": "2026-10-01", "value": 35.6567},
        {"date": "2026-10-02", "value": 37.5053},
    ]
    mock_get.assert_called_once()
    assert mock_get.call_args.args[0].endswith("/metrics.json")


def test_fetch_rows_outside_history_is_empty() -> None:
    provider = Bamservatory()

    with patch.object(provider._session, "get", return_value=_mock_resp(_METRICS_RAW)):
        rows = provider.fetch_rows(
            "network_bam_stake_share", "2025-01-01", "2026-06-19"
        )

    assert rows == []


def test_get_metric_returns_network_metric() -> None:
    provider = Bamservatory()
    sentinel_metric = object()

    with (
        patch.object(provider._session, "get", return_value=_mock_resp(_METRICS_RAW)),
        patch.object(
            Network, "from_metric_type", return_value=sentinel_metric
        ) as mock_factory,
    ):
        result = provider.get_metric("network_bam_stake_share", "2026-10-01", "solana")

    assert result is sentinel_metric
    mock_factory.assert_called_once()
    kwargs = mock_factory.call_args.kwargs
    assert kwargs["metric_type"] == NetworkMetricType.BAM_STAKE_SHARE
    assert kwargs["date"] == datetime.date(2026, 10, 1)
    assert kwargs["value"] == 35.6567


def test_get_metric_builds_canonical_metadata() -> None:
    provider = Bamservatory()

    with patch.object(provider._session, "get", return_value=_mock_resp(_METRICS_RAW)):
        metric = provider.get_metric("network_bam_stake_share", "2026-10-02", "solana")

    assert isinstance(metric, Network)
    assert metric.name == "BAM Stake Share"
    assert metric.unit == "Percent"
    assert metric.value == 37.5053


def test_get_metric_unpublished_day_returns_none() -> None:
    provider = Bamservatory()

    with patch.object(provider._session, "get", return_value=_mock_resp(_METRICS_RAW)):
        result = provider.get_metric("network_bam_stake_share", "2026-10-03", "solana")

    assert result is None


def test_unknown_metric_raises() -> None:
    provider = Bamservatory()

    with pytest.raises(ValueError, match="Unknown metric"):
        provider.fetch_rows("network_total_stake", "2026-10-01", "2026-10-01")


def test_missing_daily_series_raises() -> None:
    provider = Bamservatory()

    with patch.object(
        provider._session, "get", return_value=_mock_resp({"schemaVersion": 5})
    ):
        with pytest.raises(ValueError, match="no 'daily' series"):
            provider.fetch_rows("network_bam_stake_share", "2026-10-01", "2026-10-01")


@pytest.mark.parametrize("value", [None, "35.1", True, -0.5, 100.5])
def test_malformed_row_raises(value) -> None:
    provider = Bamservatory()
    payload = {"daily": [{"date": "2026-10-01", "bamStakePct": value}]}

    with patch.object(provider._session, "get", return_value=_mock_resp(payload)):
        with pytest.raises(ValueError, match="Malformed"):
            provider.fetch_rows("network_bam_stake_share", "2026-10-01", "2026-10-01")


def test_session_retries_transient_http_errors() -> None:
    provider = Bamservatory()
    retry = provider._session.get_adapter(provider.BASE_URL).max_retries

    assert retry.total == 3
    assert {429, 502, 503, 504} <= set(retry.status_forcelist)
    assert "GET" in retry.allowed_methods
