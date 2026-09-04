"""Unit tests for the Bitquery provider."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import pytest

from metrics.defi import Defi, DefiMetricType
from metrics.overview import Overview, OverviewMetricType
from providers.bitquery import Bitquery

_START = "2026-08-10"
_END = "2026-08-12"

_TRADES_RESPONSE = {
    "data": {
        "Trading": {
            "Trades": [
                {"Block": {"Date": "2026-08-10"}, "value": "31540934"},
                {"Block": {"Date": "2026-08-11"}, "value": "31572024"},
                {"Block": {"Date": "2026-08-12"}, "value": "29783967"},
                # Sliver of the next day echoed by the till bound; must be dropped.
                {"Block": {"Date": "2026-08-13"}, "value": "257"},
            ]
        }
    }
}

_PAIRS_RESPONSE = {
    "data": {
        "Trading": {
            "Pairs": [
                {"Block": {"Date": "2026-08-10"}, "value": "5856833485.5"},
                {"Block": {"Date": "2026-08-11"}, "value": "5735027474.1"},
                {"Block": {"Date": "2026-08-12"}, "value": "4962759327.9"},
            ]
        }
    }
}

_TOKENS_RESPONSE = {
    "data": {
        "Trading": {
            "Tokens": [
                {"Block": {"Date": "2026-08-11"}, "value": 75.73054663340251},
            ]
        }
    }
}


def _provider_with_response(payload: dict) -> Bitquery:
    provider = Bitquery(api_key="test-key")
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    provider._session = MagicMock()
    provider._session.post.return_value = response
    return provider


def test_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BITQUERY_API_KEY", raising=False)
    with pytest.raises(ValueError):
        Bitquery()


def test_unknown_metric_raises() -> None:
    provider = _provider_with_response(_TRADES_RESPONSE)
    with pytest.raises(ValueError):
        provider.fetch_rows("no_such_metric", _START, _END)


def test_fetch_rows_trades_counts_are_ints_and_range_filtered() -> None:
    provider = _provider_with_response(_TRADES_RESPONSE)
    rows = provider.fetch_rows("defi_dex_transactions", _START, _END)

    assert [r["date"] for r in rows] == ["2026-08-10", "2026-08-11", "2026-08-12"]
    assert rows[1]["value"] == 31572024
    assert all(isinstance(r["value"], int) for r in rows)


def test_fetch_rows_volume_parses_string_floats() -> None:
    provider = _provider_with_response(_PAIRS_RESPONSE)
    rows = provider.fetch_rows("defi_dex_volume", _START, _END)

    assert len(rows) == 3
    assert rows[0]["value"] == pytest.approx(5856833485.5)
    assert all(isinstance(r["value"], float) for r in rows)


def test_fetch_rows_skips_malformed_values() -> None:
    payload = {
        "data": {
            "Trading": {
                "Trades": [
                    {"Block": {"Date": "2026-08-10"}, "value": None},
                    {"Block": {"Date": "2026-08-11"}, "value": "not-a-number"},
                    {"Block": {"Date": "2026-08-12"}, "value": "nan"},
                    {"Block": {}, "value": "5"},
                ]
            }
        }
    }
    provider = _provider_with_response(payload)
    assert provider.fetch_rows("defi_dex_traders", _START, _END) == []


def test_fetch_rows_raises_on_graphql_errors() -> None:
    provider = _provider_with_response({"errors": [{"message": "limit reached"}]})
    with pytest.raises(RuntimeError):
        provider.fetch_rows("defi_dex_volume", _START, _END)


def test_query_uses_inclusive_day_bounds() -> None:
    provider = _provider_with_response(_TRADES_RESPONSE)
    provider.fetch_rows("defi_dex_transactions", _START, _END)

    query = provider._session.post.call_args.kwargs["json"]["query"]
    assert '"2026-08-10T00:00:00Z"' in query
    assert '"2026-08-13T00:00:00Z"' in query  # end_date + 1 day
    assert "bid:solana" in query


def test_get_metric_defi() -> None:
    provider = _provider_with_response(_PAIRS_RESPONSE)
    metric = provider.get_metric("defi_dex_volume", "2026-08-11", "solana")

    assert isinstance(metric, Defi)
    assert metric.metric_type == DefiMetricType.DEX_VOLUME
    assert metric.date == datetime.date(2026, 8, 11)
    assert metric.value == pytest.approx(5735027474.1)


def test_get_metric_overview_sol_price() -> None:
    provider = _provider_with_response(_TOKENS_RESPONSE)
    metric = provider.get_metric("overview_sol_price", "2026-08-11", "solana")

    assert isinstance(metric, Overview)
    assert metric.metric_type == OverviewMetricType.SOL_PRICE
    assert metric.value == pytest.approx(75.7305, rel=1e-4)


def test_get_metric_returns_none_when_no_rows() -> None:
    provider = _provider_with_response({"data": {"Trading": {"Tokens": []}}})
    assert provider.get_metric("overview_sol_price", "2026-08-11", "solana") is None
