"""Unit tests for the Solscan provider."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from metrics.defi import Defi, DefiMetricType
from metrics.network import Network, NetworkMetricType
from metrics.overview import Overview, OverviewMetricType
from providers.solscan import Solscan


def _mock_resp(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    return resp


def _series_response(rows):
    return {"success": True, "data": {"series": rows}}


def test_requires_api_key_when_none_configured(monkeypatch) -> None:
    monkeypatch.delenv("SOLSCAN_API_KEY", raising=False)
    with pytest.raises(ValueError):
        Solscan()


def test_get_metric_overview_returns_overview_metric() -> None:
    provider = Solscan(api_key="key")
    mock_response = _series_response([{"block_date": "2026-01-01", "value": 123.0}])
    sentinel_metric = object()

    with (
        patch.object(provider._session, "get", return_value=_mock_resp(mock_response)),
        patch.object(
            Overview, "from_metric_type", return_value=sentinel_metric
        ) as mock_factory,
    ):
        result = provider.get_metric("overview_tx_count_total", "2026-01-01", "solana")

    assert result is sentinel_metric
    mock_factory.assert_called_once()
    assert (
        mock_factory.call_args.kwargs["metric_type"]
        == OverviewMetricType.TX_COUNT_TOTAL
    )
    assert mock_factory.call_args.kwargs["value"] == 123.0


def test_get_metric_defi_returns_defi_metric() -> None:
    provider = Solscan(api_key="key")
    mock_response = _series_response(
        [{"block_date": "2026-01-01", "volume_usd": 987_654.0}]
    )
    sentinel_metric = object()

    with (
        patch.object(provider._session, "get", return_value=_mock_resp(mock_response)),
        patch.object(
            Defi, "from_metric_type", return_value=sentinel_metric
        ) as mock_factory,
    ):
        result = provider.get_metric("defi_dex_volume", "2026-01-01", "solana")

    assert result is sentinel_metric
    mock_factory.assert_called_once()
    assert mock_factory.call_args.kwargs["metric_type"] == DefiMetricType.DEX_VOLUME
    assert mock_factory.call_args.kwargs["value"] == 987_654.0


def test_get_metric_returns_none_when_series_empty() -> None:
    provider = Solscan(api_key="key")

    with patch.object(
        provider._session, "get", return_value=_mock_resp(_series_response([]))
    ):
        result = provider.get_metric("overview_tx_count_total", "2026-01-01", "solana")

    assert result is None


def test_get_metric_network_returns_network_metric() -> None:
    provider = Solscan(api_key="key")
    mock_response = _series_response(
        [{"block_date": "2026-01-01", "total_stake_sol": 1_000.0}]
    )
    sentinel_metric = object()

    with (
        patch.object(provider._session, "get", return_value=_mock_resp(mock_response)),
        patch.object(
            Network, "from_metric_type", return_value=sentinel_metric
        ) as mock_factory,
    ):
        result = provider.get_metric("network_total_stake", "2026-01-01", "solana")

    assert result is sentinel_metric
    mock_factory.assert_called_once()
    assert mock_factory.call_args.kwargs["metric_type"] == NetworkMetricType.TOTAL_STAKE
    assert mock_factory.call_args.kwargs["value"] == 1_000.0


def test_fetch_rows_filters_by_date_range() -> None:
    provider = Solscan(api_key="key")
    raw = _series_response(
        [
            {"block_date": "2024-01-01", "value": 1.0},
            {"block_date": "2026-01-01", "value": 5_000.0},
            {"block_date": "2027-01-01", "value": 9_000.0},
        ]
    )

    with patch.object(provider._session, "get", return_value=_mock_resp(raw)):
        rows = provider.fetch_rows(
            "overview_tx_count_total", "2025-01-01", "2026-06-01"
        )

    assert len(rows) == 1
    assert rows[0] == {"date": "2026-01-01", "value": 5_000.0}


def test_fetch_rows_sends_filter_and_unix_time_range_params() -> None:
    provider = Solscan(api_key="key")
    mock_resp = _mock_resp(_series_response([]))

    with patch.object(provider._session, "get", return_value=mock_resp) as mock_get:
        provider.fetch_rows(
            "overview_non_vote_tx_count_failed", "2026-01-01", "2026-01-02"
        )

    mock_get.assert_called_once()
    _, kwargs = mock_get.call_args
    assert kwargs["params"]["filter"] == "nonvote_fail"
    assert kwargs["params"]["from_time"] == 1767225600  # 2026-01-01T00:00:00Z
    assert kwargs["params"]["to_time"] == 1767312000  # 2026-01-02T00:00:00Z


def test_fetch_rows_raises_on_unknown_metric() -> None:
    provider = Solscan(api_key="key")
    with pytest.raises(KeyError):
        provider.fetch_rows("nonexistent_metric", "2026-01-01", "2026-01-31")


def test_get_raises_on_unsuccessful_response() -> None:
    provider = Solscan(api_key="key")
    error_body = {"success": False, "data": None, "error": "boom"}

    with patch.object(provider._session, "get", return_value=_mock_resp(error_body)):
        with pytest.raises(RuntimeError, match="boom"):
            provider.fetch_rows("overview_tx_count_total", "2026-01-01", "2026-01-01")
