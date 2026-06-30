"""Unit tests for the DexPaprika provider."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest

from metrics.defi import Defi, DefiMetricType
from metrics.overview import Overview, OverviewMetricType
from providers.dexpaprika import DexPaprika

_TODAY = datetime.date.today().isoformat()

_NETWORKS_RAW = [
    {"id": "ethereum", "volume_usd_24h": 1_000_000.0, "txns_24h": 50_000},
    {"id": "solana", "volume_usd_24h": 5_000_000_000.0, "txns_24h": 28_000_000},
]

_DEXES_RAW = {
    "dexes": [
        {"dex_id": "manifest", "volume_usd_24h": 214_000_000.0},
        {"dex_id": "orca", "volume_usd_24h": 90_000_000.0},
        {"dex_id": "dead-dex", "volume_usd_24h": 0},
    ],
    "page_info": {"limit": 100, "page": 1},
}

_SOL_TOKEN_RAW = {
    "id": "So11111111111111111111111111111111111111112",
    "name": "Wrapped SOL",
    "summary": {"price_usd": 68.42, "liquidity_usd": 1_200_000_000.0},
}


def _make_mock_resp(payload):
    mock_resp = MagicMock()
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def test_get_dex_volume_returns_defi_metric() -> None:
    provider = DexPaprika()

    with patch.object(
        provider._session, "get", return_value=_make_mock_resp(_NETWORKS_RAW)
    ):
        result = provider.get_metric("defi_dex_volume", _TODAY, "solana")

    # Build a real model (no factory mock) so a swapped metadata mapping or a
    # broken Defi/Overview branch would actually fail here.
    assert isinstance(result, Defi)
    assert result.metric_type == DefiMetricType.DEX_VOLUME
    assert result.value == 5_000_000_000.0


def test_fetch_rows_dex_transactions_picks_solana() -> None:
    provider = DexPaprika()
    with patch.object(
        provider._session, "get", return_value=_make_mock_resp(_NETWORKS_RAW)
    ):
        rows = provider.fetch_rows("defi_dex_transactions", _TODAY, _TODAY)

    assert rows == [{"date": _TODAY, "value": 28_000_000.0}]


def test_fetch_rows_dex_count_counts_only_active() -> None:
    provider = DexPaprika()
    with patch.object(
        provider._session, "get", return_value=_make_mock_resp(_DEXES_RAW)
    ):
        rows = provider.fetch_rows("defi_dex_count", _TODAY, _TODAY)

    # 2 of 3 DEXes have non-zero 24h volume
    assert rows == [{"date": _TODAY, "value": 2.0}]


def test_dex_count_ignores_string_typed_volume() -> None:
    # A volume that arrives as a non-numeric string must not be miscounted as active.
    provider = DexPaprika()
    payload = {
        "dexes": [
            {"dex_id": "real", "volume_usd_24h": 5.0},
            {"dex_id": "weird", "volume_usd_24h": "N/A"},
        ]
    }
    with patch.object(provider._session, "get", return_value=_make_mock_resp(payload)):
        rows = provider.fetch_rows("defi_dex_count", _TODAY, _TODAY)

    assert rows == [{"date": _TODAY, "value": 1.0}]


def test_dex_count_raises_if_page_is_full() -> None:
    # A completely full page means the protocol set outgrew one page; refuse to
    # silently under-report rather than capping the count.
    provider = DexPaprika()
    full_page = {
        "dexes": [{"dex_id": f"d{i}", "volume_usd_24h": 1.0} for i in range(100)]
    }
    with patch.object(
        provider._session, "get", return_value=_make_mock_resp(full_page)
    ):
        with pytest.raises(RuntimeError, match="page limit"):
            provider.fetch_rows("defi_dex_count", _TODAY, _TODAY)


def test_dex_count_empty_when_dexes_key_absent() -> None:
    # A 200 whose body lacks "dexes" (schema drift) must skip the row, not
    # record a misleading 0. Mirrors the missing-field handling for other metrics.
    provider = DexPaprika()
    no_dexes = {"page_info": {"limit": 100, "page": 1}}  # no "dexes" key
    with patch.object(provider._session, "get", return_value=_make_mock_resp(no_dexes)):
        assert provider.fetch_rows("defi_dex_count", _TODAY, _TODAY) == []


def test_fetch_rows_empty_when_chain_absent() -> None:
    provider = DexPaprika()
    only_eth = [{"id": "ethereum", "volume_usd_24h": 1.0, "txns_24h": 1}]
    with patch.object(provider._session, "get", return_value=_make_mock_resp(only_eth)):
        assert provider.fetch_rows("defi_dex_volume", _TODAY, _TODAY) == []


def test_fetch_rows_empty_when_field_is_null() -> None:
    provider = DexPaprika()
    null_field = [{"id": "solana", "volume_usd_24h": None, "txns_24h": 1}]
    with patch.object(
        provider._session, "get", return_value=_make_mock_resp(null_field)
    ):
        assert provider.fetch_rows("defi_dex_volume", _TODAY, _TODAY) == []


def test_fetch_rows_empty_when_token_summary_missing() -> None:
    provider = DexPaprika()
    no_summary = {"id": "So111", "name": "Wrapped SOL"}  # no "summary" block
    with patch.object(
        provider._session, "get", return_value=_make_mock_resp(no_summary)
    ):
        assert provider.fetch_rows("overview_sol_price", _TODAY, _TODAY) == []


def test_get_sol_price_returns_overview_metric() -> None:
    provider = DexPaprika()

    with patch.object(
        provider._session, "get", return_value=_make_mock_resp(_SOL_TOKEN_RAW)
    ):
        result = provider.get_metric("overview_sol_price", _TODAY, "solana")

    # Real Overview model: proves the overview branch routes correctly and the
    # SOL_PRICE metadata is wired up.
    assert isinstance(result, Overview)
    assert result.metric_type == OverviewMetricType.SOL_PRICE
    assert result.value == 68.42


def test_fetch_rows_returns_empty_when_today_out_of_range() -> None:
    provider = DexPaprika()
    # No HTTP call should be needed; range is entirely in the past.
    rows = provider.fetch_rows("defi_dex_volume", "2024-01-01", "2024-01-02")
    assert rows == []


def test_fetch_rows_raises_on_unknown_metric() -> None:
    provider = DexPaprika()
    with pytest.raises(ValueError, match="nonexistent_metric"):
        provider.fetch_rows("nonexistent_metric", _TODAY, _TODAY)


def test_get_metric_returns_none_when_no_rows() -> None:
    provider = DexPaprika()
    # Past range -> fetch_rows returns [] -> get_metric returns None.
    assert provider.get_metric("defi_dex_volume", "2024-01-01", "solana") is None


def test_get_metric_returns_none_for_mapped_but_untyped_metric() -> None:
    # Defensive path: a metric present in METRIC_MAP but absent from both type
    # maps degrades to None instead of raising, even when fetch_rows returns data.
    provider = DexPaprika()
    fake = {"endpoint": "/networks", "network_field": "volume_usd_24h"}
    with patch.dict(DexPaprika.METRIC_MAP, {"unmapped_metric": fake}, clear=False):
        with patch.object(
            provider._session, "get", return_value=_make_mock_resp(_NETWORKS_RAW)
        ):
            assert provider.get_metric("unmapped_metric", _TODAY, "solana") is None
