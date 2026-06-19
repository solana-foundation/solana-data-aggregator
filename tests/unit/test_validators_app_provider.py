"""Unit tests for the ValidatorsApp provider."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest

from metrics.network import Network, NetworkMetricType
from providers.validators_app import ValidatorsApp

TODAY = "2026-06-11"

_SOL_PRICE_RAW = [
    {"datetime_from_exchange": "2026-06-09T00:00:00Z", "average_price": 150.0},
    {"datetime_from_exchange": "2026-06-10T00:00:00Z", "average_price": 155.0},
    {"datetime_from_exchange": "2026-06-11T00:00:00Z", "average_price": 160.0},
]

_VALIDATORS_RAW = [
    {
        "is_active": True,
        "delinquent": False,
        "active_stake": 1_000_000_000_000,
        "autonomous_system_number": 111,
    },
    {
        "is_active": True,
        "delinquent": False,
        "active_stake": 500_000_000_000,
        "autonomous_system_number": 222,
    },
    {
        "is_active": True,
        "delinquent": False,
        "active_stake": 300_000_000_000,
        "autonomous_system_number": 333,
    },
    {
        "is_active": True,
        "delinquent": False,
        "active_stake": 200_000_000_000,
        "autonomous_system_number": 444,
    },
    {
        "is_active": True,
        "delinquent": True,
        "active_stake": 999_000_000_000,
        "autonomous_system_number": 555,
    },
    {
        "is_active": False,
        "delinquent": False,
        "active_stake": 999_000_000_000,
        "autonomous_system_number": 666,
    },
]


def _mock_resp(payload):
    m = MagicMock()
    m.json.return_value = payload
    m.raise_for_status = MagicMock()
    return m


def _provider():
    return ValidatorsApp(api_token="test-token")


def _patch_today():
    return patch(
        "providers.validators_app.datetime.date",
        **{
            "today.return_value": datetime.date.fromisoformat(TODAY),
            "fromisoformat": datetime.date.fromisoformat,
        },
    )


# -- network_sol_price -------------------------------------------------------


def test_fetch_rows_sol_price_filters_by_date_range() -> None:
    provider = _provider()
    with patch.object(
        provider._session, "get", return_value=_mock_resp(_SOL_PRICE_RAW)
    ):
        rows = provider.fetch_rows("network_sol_price", "2026-06-10", "2026-06-11")

    assert len(rows) == 2
    assert rows[0] == {"date": "2026-06-10", "value": 155.0}
    assert rows[1] == {"date": "2026-06-11", "value": 160.0}


def test_fetch_rows_sol_price_returns_empty_outside_range() -> None:
    provider = _provider()
    with patch.object(
        provider._session, "get", return_value=_mock_resp(_SOL_PRICE_RAW)
    ):
        rows = provider.fetch_rows("network_sol_price", "2025-01-01", "2025-12-31")

    assert rows == []


# -- network_total_stake -----------------------------------------------------


def test_fetch_rows_total_stake_sums_active_lamports_to_sol() -> None:
    provider = _provider()
    with (
        patch.object(
            provider._session, "get", return_value=_mock_resp(_VALIDATORS_RAW)
        ),
        _patch_today(),
    ):
        rows = provider.fetch_rows("network_total_stake", TODAY, TODAY)

    assert len(rows) == 1
    # 1_000 + 500 + 300 + 200 = 2_000 SOL (lamports / 1e9), inactive excluded
    assert rows[0]["value"] == pytest.approx(2_000.0)
    assert rows[0]["date"] == TODAY


def test_fetch_rows_total_stake_excludes_inactive_validators() -> None:
    provider = _provider()
    all_inactive = [
        {
            "is_active": False,
            "delinquent": False,
            "active_stake": 999_000_000_000,
            "autonomous_system_number": 1,
        },
        {
            "is_active": True,
            "delinquent": True,
            "active_stake": 999_000_000_000,
            "autonomous_system_number": 2,
        },
    ]
    with (
        patch.object(provider._session, "get", return_value=_mock_resp(all_inactive)),
        _patch_today(),
    ):
        rows = provider.fetch_rows("network_total_stake", TODAY, TODAY)

    assert rows[0]["value"] == pytest.approx(0.0)


# -- network_validator_count -------------------------------------------------


def test_fetch_rows_validator_count_counts_active_only() -> None:
    provider = _provider()
    with (
        patch.object(
            provider._session, "get", return_value=_mock_resp(_VALIDATORS_RAW)
        ),
        _patch_today(),
    ):
        rows = provider.fetch_rows("network_validator_count", TODAY, TODAY)

    assert len(rows) == 1
    assert rows[0]["value"] == 4.0  # 4 active, 1 inactive


# -- network_top_3_asn_share -------------------------------------------------


def test_fetch_rows_top_3_asn_share_correct_percentage() -> None:
    provider = _provider()
    with (
        patch.object(
            provider._session, "get", return_value=_mock_resp(_VALIDATORS_RAW)
        ),
        _patch_today(),
    ):
        rows = provider.fetch_rows("network_top_3_asn_share", TODAY, TODAY)

    assert len(rows) == 1
    # Active stakes: ASN111=1000, ASN222=500, ASN333=300, ASN444=200 → total=2000
    # Top 3: 1000+500+300=1800 → 90%
    assert rows[0]["value"] == pytest.approx(90.0)


def test_fetch_rows_snapshot_returns_empty_when_today_outside_range() -> None:
    provider = _provider()
    with (
        patch.object(
            provider._session, "get", return_value=_mock_resp(_VALIDATORS_RAW)
        ),
        _patch_today(),
    ):
        rows = provider.fetch_rows("network_total_stake", "2025-01-01", "2025-12-31")

    assert rows == []


# -- get_metric --------------------------------------------------------------


def test_get_metric_returns_network_metric() -> None:
    provider = _provider()
    sentinel = object()
    with (
        patch.object(
            provider._session, "get", return_value=_mock_resp(_VALIDATORS_RAW)
        ),
        _patch_today(),
        patch.object(
            Network, "from_metric_type", return_value=sentinel
        ) as mock_factory,
    ):
        result = provider.get_metric("network_total_stake", TODAY, "solana")

    assert result is sentinel
    mock_factory.assert_called_once()
    assert mock_factory.call_args.kwargs["metric_type"] == NetworkMetricType.TOTAL_STAKE


def test_get_metric_returns_none_when_no_rows() -> None:
    provider = _provider()
    with (
        patch.object(
            provider._session, "get", return_value=_mock_resp(_VALIDATORS_RAW)
        ),
        _patch_today(),
    ):
        result = provider.get_metric("network_total_stake", "2025-01-01", "solana")

    assert result is None


# -- error handling ----------------------------------------------------------


def test_fetch_rows_raises_on_unknown_metric() -> None:
    provider = _provider()
    with pytest.raises(ValueError, match="nonexistent_metric"):
        provider.fetch_rows("nonexistent_metric", TODAY, TODAY)
