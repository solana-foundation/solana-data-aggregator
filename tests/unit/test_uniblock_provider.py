"""Unit tests for the Uniblock provider."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest

from metrics.network import Network, NetworkMetricType
from metrics.overview import Overview, OverviewMetricType
from providers.uniblock import Uniblock

_DAY_1 = "2026-07-07"
_DAY_2 = "2026-07-08"
_TODAY = datetime.date.today().isoformat()
_PAST = "2000-01-01"


def _ms(date_str: str, hour: int) -> str:
    """Unix-millisecond timestamp (as a string key) for a UTC date + hour."""
    dt = datetime.datetime.fromisoformat(date_str).replace(
        hour=hour, tzinfo=datetime.timezone.utc
    )
    return str(int(dt.timestamp() * 1000))


# Two UTC days, two intraday points each.
# Day 1 prices 77 + 79 -> avg 78; Day 2 prices 80 + 82 -> avg 81.
_CHART_RANGE_RESPONSE = {
    "granularity": 60,
    "data": {
        _ms(_DAY_1, 6): {"price": 77.0, "volume": 1.0, "marketCap": 2.0},
        _ms(_DAY_1, 18): {"price": 79.0, "volume": 1.0, "marketCap": 2.0},
        _ms(_DAY_2, 6): {"price": 80.0, "volume": 1.0, "marketCap": 2.0},
        _ms(_DAY_2, 18): {"price": 82.0, "volume": 1.0, "marketCap": 2.0},
    },
}


def _make_mock_resp(payload: dict) -> MagicMock:
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = payload
    return m


def _make_provider() -> Uniblock:
    return Uniblock(api_key="test-key")


def _date(date_str: str) -> datetime.date:
    return datetime.date.fromisoformat(date_str)


# -- fetch_rows ---------------------------------------------------------------


def test_fetch_rows_overview_sol_price_daily_average() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "get", return_value=_make_mock_resp(_CHART_RANGE_RESPONSE)
    ):
        rows = provider.fetch_rows("overview_sol_price", _DAY_1, _DAY_2)

    assert rows == [
        {"date": _DAY_1, "value": pytest.approx(78.0)},
        {"date": _DAY_2, "value": pytest.approx(81.0)},
    ]


def test_fetch_rows_network_sol_price_uses_same_series() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "get", return_value=_make_mock_resp(_CHART_RANGE_RESPONSE)
    ):
        rows = provider.fetch_rows("network_sol_price", _DAY_1, _DAY_2)

    assert rows[0] == {"date": _DAY_1, "value": pytest.approx(78.0)}
    assert rows[1] == {"date": _DAY_2, "value": pytest.approx(81.0)}


def test_fetch_rows_filters_out_of_range_dates() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "get", return_value=_make_mock_resp(_CHART_RANGE_RESPONSE)
    ):
        rows = provider.fetch_rows("overview_sol_price", _DAY_1, _DAY_1)

    assert rows == [{"date": _DAY_1, "value": pytest.approx(78.0)}]


def test_fetch_rows_skips_non_finite_and_missing_prices() -> None:
    payload = {
        "data": {
            _ms(_DAY_1, 6): {"price": 100.0},
            _ms(_DAY_1, 12): {"price": None},
            _ms(_DAY_1, 18): {"volume": 5.0},  # no price key
        }
    }
    provider = _make_provider()
    with patch.object(provider._session, "get", return_value=_make_mock_resp(payload)):
        rows = provider.fetch_rows("overview_sol_price", _DAY_1, _DAY_1)

    # Only the single valid point contributes to the average.
    assert rows == [{"date": _DAY_1, "value": pytest.approx(100.0)}]


def test_fetch_rows_returns_float_values() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "get", return_value=_make_mock_resp(_CHART_RANGE_RESPONSE)
    ):
        rows = provider.fetch_rows("overview_sol_price", _DAY_1, _DAY_2)

    assert all(isinstance(row["value"], float) for row in rows)


def test_fetch_rows_empty_data_returns_empty_list() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "get", return_value=_make_mock_resp({"data": {}})
    ):
        assert provider.fetch_rows("overview_sol_price", _DAY_1, _DAY_2) == []


def test_fetch_rows_missing_data_key_returns_empty_list() -> None:
    provider = _make_provider()
    with patch.object(provider._session, "get", return_value=_make_mock_resp({})):
        assert provider.fetch_rows("overview_sol_price", _DAY_1, _DAY_2) == []


def test_fetch_rows_unknown_metric_raises() -> None:
    provider = _make_provider()
    with pytest.raises(ValueError, match="Unknown metric"):
        provider.fetch_rows("defi_dex_volume", _DAY_1, _DAY_2)


# -- get_metric ---------------------------------------------------------------


def test_get_metric_overview_returns_overview_model() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "get", return_value=_make_mock_resp(_CHART_RANGE_RESPONSE)
    ):
        result = provider.get_metric("overview_sol_price", _DAY_1, "solana")

    assert isinstance(result, Overview)
    assert result.metric_type == OverviewMetricType.SOL_PRICE
    assert result.value == pytest.approx(78.0)
    assert result.date == _date(_DAY_1)


def test_get_metric_network_returns_network_model() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "get", return_value=_make_mock_resp(_CHART_RANGE_RESPONSE)
    ):
        result = provider.get_metric("network_sol_price", _DAY_1, "solana")

    assert isinstance(result, Network)
    assert result.metric_type == NetworkMetricType.SOL_PRICE
    assert result.value == pytest.approx(78.0)
    assert result.date == _date(_DAY_1)


def test_get_metric_returns_none_when_no_rows() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "get", return_value=_make_mock_resp({"data": {}})
    ):
        assert provider.get_metric("overview_sol_price", _DAY_1, "solana") is None


# -- constructor --------------------------------------------------------------


def test_constructor_raises_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("UNIBLOCK_API_KEY", raising=False)
    with pytest.raises(ValueError, match="UNIBLOCK_API_KEY"):
        Uniblock()


def test_constructor_reads_api_key_from_env(monkeypatch) -> None:
    monkeypatch.setenv("UNIBLOCK_API_KEY", "env-key")
    provider = Uniblock()
    assert provider.api_key == "env-key"


# -- JSON-RPC snapshot metrics ------------------------------------------------

# 2 current + 1 delinquent; stake in lamports.
# current count -> 2; total stake -> (110 + 90 + 1) = 201 SOL.
_VOTE_ACCOUNTS_RESPONSE = {
    "id": 1,
    "jsonrpc": "2.0",
    "result": {
        "current": [
            {"activatedStake": 110_000_000_000, "nodePubkey": "a"},
            {"activatedStake": 90_000_000_000, "nodePubkey": "b"},
        ],
        "delinquent": [
            {"activatedStake": 1_000_000_000, "nodePubkey": "c"},
        ],
    },
}


def test_fetch_rows_total_stake() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session,
        "post",
        return_value=_make_mock_resp(_VOTE_ACCOUNTS_RESPONSE),
    ):
        rows = provider.fetch_rows("network_total_stake", _PAST, _TODAY)

    assert rows == [{"date": _TODAY, "value": pytest.approx(201.0)}]


def test_fetch_rows_validator_count_excludes_delinquent() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session,
        "post",
        return_value=_make_mock_resp(_VOTE_ACCOUNTS_RESPONSE),
    ):
        rows = provider.fetch_rows("network_validator_count", _PAST, _TODAY)

    assert rows == [{"date": _TODAY, "value": 2.0}]


def test_vote_account_metrics_share_one_rpc_call() -> None:
    """total_stake and validator_count both come from one getVoteAccounts POST."""
    provider = _make_provider()
    mock_post = MagicMock(return_value=_make_mock_resp(_VOTE_ACCOUNTS_RESPONSE))
    with patch.object(provider._session, "post", mock_post):
        provider.fetch_rows("network_total_stake", _PAST, _TODAY)
        provider.fetch_rows("network_validator_count", _PAST, _TODAY)

    assert mock_post.call_count == 1


def test_rpc_snapshot_skipped_when_today_out_of_range() -> None:
    provider = _make_provider()
    mock_post = MagicMock(return_value=_make_mock_resp(_VOTE_ACCOUNTS_RESPONSE))
    with patch.object(provider._session, "post", mock_post):
        rows = provider.fetch_rows("network_total_stake", "2000-01-01", "2000-01-02")

    assert rows == []
    assert mock_post.call_count == 0  # no request when today is out of range


def test_get_metric_total_stake_returns_network_model() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session,
        "post",
        return_value=_make_mock_resp(_VOTE_ACCOUNTS_RESPONSE),
    ):
        result = provider.get_metric("network_total_stake", _TODAY, "solana")

    assert isinstance(result, Network)
    assert result.metric_type == NetworkMetricType.TOTAL_STAKE
    assert result.value == pytest.approx(201.0)


def test_post_rpc_raises_on_error() -> None:
    provider = _make_provider()
    error_resp = {"id": 1, "jsonrpc": "2.0", "error": {"code": -1, "message": "boom"}}
    with patch.object(
        provider._session, "post", return_value=_make_mock_resp(error_resp)
    ):
        with pytest.raises(RuntimeError, match="getVoteAccounts failed"):
            provider.fetch_rows("network_total_stake", _PAST, _TODAY)
