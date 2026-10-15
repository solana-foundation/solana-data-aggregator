"""Tests for the Solana Compass provider."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

from metrics.defi import Defi, DefiMetricType
from metrics.overview import Overview, OverviewMetricType
from providers.solana_compass import SolanaCompass


def _mock_response(body: dict) -> MagicMock:
    response = MagicMock()
    response.json.return_value = body
    response.raise_for_status = MagicMock()
    return response


def _timestamp_ms(date: str) -> int:
    dt = datetime.datetime.fromisoformat(date).replace(tzinfo=datetime.timezone.utc)
    return int(dt.timestamp() * 1000)


def test_fetch_rows_vote_count_uses_network_overview_summary() -> None:
    provider = SolanaCompass(base_url="https://example.test/api/v1")
    body = {
        "data": {
            "timeSeries": [
                {
                    "timestamp": _timestamp_ms("2026-06-15"),
                    "votes": 4321,
                    "completed": 100,
                    "reverted": 5,
                }
            ]
        }
    }

    with patch.object(provider._session, "get", return_value=_mock_response(body)) as get:
        rows = provider.fetch_rows(
            "overview_tx_count_vote", "2026-06-15", "2026-06-15"
        )

    assert rows == [{"date": "2026-06-15", "value": 4321.0}]
    get.assert_called_once()
    assert get.call_args.args[0] == "https://example.test/api/v1/network/overview"
    assert get.call_args.kwargs["params"]["interval"] == "1d"
    assert get.call_args.kwargs["params"]["range"] == "yesterday"
    assert get.call_args.kwargs["params"]["from"] == "2026-06-15T00:00:00Z"
    assert get.call_args.kwargs["params"]["to"] == "2026-06-16T00:00:00Z"


def test_fetch_rows_total_count_falls_back_to_component_sum() -> None:
    provider = SolanaCompass(base_url="https://example.test/api/v1")
    body = {
        "data": {
            "timeSeries": [
                {
                    "timestamp": _timestamp_ms("2026-06-15"),
                    "completed": 100,
                    "reverted": 5,
                    "votes": 900,
                }
            ]
        }
    }

    with patch.object(provider._session, "get", return_value=_mock_response(body)):
        rows = provider.fetch_rows(
            "overview_tx_count_total", "2026-06-15", "2026-06-15"
        )

    assert rows == [{"date": "2026-06-15", "value": 1005.0}]


def test_fetch_rows_dex_volume_uses_dex_summary() -> None:
    provider = SolanaCompass(base_url="https://example.test/api/v1")
    body = {
        "data": {
            "timeSeries": [
                {
                    "timestamp": _timestamp_ms("2026-06-15"),
                    "volume": 123_456.78,
                    "trades": 42,
                    "traders": 11,
                    "programs": 7,
                }
            ]
        }
    }

    with patch.object(provider._session, "get", return_value=_mock_response(body)) as get:
        rows = provider.fetch_rows("defi_dex_volume", "2026-06-15", "2026-06-15")

    assert rows == [{"date": "2026-06-15", "value": 123456.78}]
    assert get.call_args.args[0] == "https://example.test/api/v1/dex/volume"


def test_fetch_rows_dex_count_uses_daily_program_cardinality() -> None:
    provider = SolanaCompass(base_url="https://example.test/api/v1")
    body = {
        "data": {
            "timeSeries": [
                {"timestamp": _timestamp_ms("2026-06-15"), "programs": 7},
                {"timestamp": _timestamp_ms("2026-06-16"), "programs": 8},
            ]
        }
    }

    with patch.object(provider._session, "get", return_value=_mock_response(body)):
        rows = provider.fetch_rows("defi_dex_count", "2026-06-15", "2026-06-16")

    assert rows == [
        {"date": "2026-06-15", "value": 7.0},
        {"date": "2026-06-16", "value": 8.0},
    ]


def test_fetch_rows_fee_payers_uses_account_signer_summary() -> None:
    provider = SolanaCompass(base_url="https://example.test/api/v1")
    body = {
        "data": {
            "timeSeries": [
                {"timestamp": _timestamp_ms("2026-06-15"), "uniqueSigners": 1234}
            ]
        }
    }

    with patch.object(provider._session, "get", return_value=_mock_response(body)) as get:
        rows = provider.fetch_rows(
            "overview_fee_payers", "2026-06-15", "2026-06-15"
        )

    assert rows == [{"date": "2026-06-15", "value": 1234.0}]
    assert get.call_args.args[0] == "https://example.test/api/v1/network/fees"


def test_get_metric_returns_typed_overview_metric() -> None:
    provider = SolanaCompass(base_url="https://example.test/api/v1")
    body = {
        "data": {
            "timeSeries": [
                {"timestamp": _timestamp_ms("2026-06-15"), "fees": 12.5}
            ]
        }
    }
    sentinel = object()

    with (
        patch.object(provider._session, "get", return_value=_mock_response(body)),
        patch.object(Overview, "from_metric_type", return_value=sentinel) as factory,
    ):
        result = provider.get_metric("overview_fees", "2026-06-15", "solana")

    assert result is sentinel
    factory.assert_called_once()
    assert factory.call_args.kwargs["metric_type"] == OverviewMetricType.FEES
    assert factory.call_args.kwargs["value"] == 12.5


def test_get_metric_returns_typed_defi_metric() -> None:
    provider = SolanaCompass(base_url="https://example.test/api/v1")
    body = {
        "data": {
            "timeSeries": [
                {"timestamp": _timestamp_ms("2026-06-15"), "trades": 42}
            ]
        }
    }
    sentinel = object()

    with (
        patch.object(provider._session, "get", return_value=_mock_response(body)),
        patch.object(Defi, "from_metric_type", return_value=sentinel) as factory,
    ):
        result = provider.get_metric("defi_dex_transactions", "2026-06-15", "solana")

    assert result is sentinel
    factory.assert_called_once()
    assert factory.call_args.kwargs["metric_type"] == DefiMetricType.DEX_TRANSACTIONS
    assert factory.call_args.kwargs["value"] == 42.0
