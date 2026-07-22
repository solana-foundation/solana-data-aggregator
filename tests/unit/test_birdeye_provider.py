"""Unit tests for the Birdeye provider."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest

from metrics.defi import Defi, DefiMetricType
from metrics.overview import Overview, OverviewMetricType
from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.birdeye import Birdeye

_DATE_7_7 = "2026-07-07"
_DATE_7_8 = "2026-07-08"

_MARKET_HISTORY_RESPONSE = {
    "data": {
        "success": True,
        "items": [
            {
                "unix_time": 1783382400,
                "volume_usd": 12066695086.76048,
                "tvl": 10852220591.790138,
                "trade_count": 30908550,
                "active_trading_tokens": 69428,
                "stable_coin_market_cap": 14637051338.896027,
                "rwa_market_cap": 1158471324.2037046
            }
        ]
    }
}
_MARKET_HISTORY_RESPONSE_PARTIAL = {
    "data": {
        "success": True,
        "items": [
            {
                "unix_time": 1783468800,
                "volume_usd": 1234567890,
            }
        ]
    }
}
_MARKET_HISTORY_RESPONSE_MULTI_DAY = {
    "data": {
        "success": True,
        "items": [
            {
                "unix_time": 1783382400,
                "volume_usd": 12066695086.76048,
                "tvl": 10852220591.790138,
                "trade_count": 30908550,
                "active_trading_tokens": 69428,
                "stable_coin_market_cap": 14637051338.896027,
                "rwa_market_cap": 1158471324.2037046
            },
            {
                "unix_time": 1783468800,
                "volume_usd": 1234567890,
            }
        ]
    }
}
_PRICE_HISTORY_RESPONSE = {
    "data": {
        "success": True,
        "items": [
            {
                "unixTime": 1783382400,
                "value": 77.77
            }
        ]
    }
}
_PRICE_HISTORY_RESPONSE_MULTI_DAY = {
    "data": {
        "success": True,
        "items": [
            {
                "unixTime": 1783382400,
                "value": 77.77
            },
            {
                "unixTime": 1783468800,
                "value": 78.78
            }
        ]
    }
}
_RESPONSE_FAILURE = {
    "data": {
        "success": False,
        "items": []
    }
}


def _make_mock_resp(payload):
    mock_resp = MagicMock()
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()
    return mock_resp

def _date(date_str: str) -> datetime.date:
    return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()

def _date_to_timestamp(date_str: str) -> int:
    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
    return int(dt.timestamp())

def test_get_metric_overview_sol_price() -> None:
    provider = Birdeye(api_key="xxx")

    with patch.object(
        provider._session, "get", return_value=_make_mock_resp(_PRICE_HISTORY_RESPONSE)
    ):
        result = provider.get_metric("overview_sol_price", _DATE_7_7, "solana")
        assert isinstance(result, Overview)
        assert result.metric_type == OverviewMetricType.SOL_PRICE
        assert result.value == 77.77
        assert result.date == _date(_DATE_7_7)

def test_get_metric_stablecoin_defi() -> None:
    provider = Birdeye(api_key="xxx")

    with patch.object(
        provider._session, "get", return_value=_make_mock_resp(_MARKET_HISTORY_RESPONSE)
    ):
        result = provider.get_metric("stablecoin_supply", _DATE_7_7, "solana")
        assert isinstance(result, Stablecoin)
        assert result.metric_type == StablecoinMetricType.SUPPLY
        assert result.value == 14637051338.896027
        assert result.date == _date(_DATE_7_7)

        result = provider.get_metric("defi_dex_volume", _DATE_7_7, "solana")
        assert isinstance(result, Defi)
        assert result.metric_type == DefiMetricType.DEX_VOLUME
        assert result.value == 12066695086.76048
        assert result.date == _date(_DATE_7_7)

        result = provider.get_metric("defi_dex_transactions", _DATE_7_7, "solana")
        assert isinstance(result, Defi)
        assert result.metric_type == DefiMetricType.DEX_TRANSACTIONS
        assert result.value == 30908550
        assert result.date == _date(_DATE_7_7)

def test_get_metric_stablecoin_defi_partial() -> None:
    provider = Birdeye(api_key="xxx")

    with patch.object(
        provider._session, "get", return_value=_make_mock_resp(_MARKET_HISTORY_RESPONSE_PARTIAL)
    ):
        result = provider.get_metric("stablecoin_supply", _DATE_7_8, "solana")
        assert result is None

        result = provider.get_metric("defi_dex_volume", _DATE_7_8, "solana")
        assert isinstance(result, Defi)
        assert result.metric_type == DefiMetricType.DEX_VOLUME
        assert result.value == 1234567890
        assert result.date == _date(_DATE_7_8)

        result = provider.get_metric("defi_dex_transactions", _DATE_7_8, "solana")
        assert result is None

def test_fetch_rows_overview_sol_price() -> None:
    provider = Birdeye(api_key="xxx")

    with patch.object(
        provider._session, "get", return_value=_make_mock_resp(_PRICE_HISTORY_RESPONSE_MULTI_DAY)
    ):
        rows = provider.fetch_rows("overview_sol_price", _DATE_7_7, _DATE_7_8)
        assert len(rows) == 2
        assert rows[0]["date"] == _date_to_timestamp(_DATE_7_7)
        assert rows[0]["value"] == 77.77
        assert rows[1]["date"] == _date_to_timestamp(_DATE_7_8)
        assert rows[1]["value"] == 78.78

def test_fetch_rows_stablecoin_defi() -> None:
    provider = Birdeye(api_key="xxx")

    with patch.object(
        provider._session, "get", return_value=_make_mock_resp(_MARKET_HISTORY_RESPONSE_MULTI_DAY)
    ):
        rows = provider.fetch_rows("stablecoin_supply", _DATE_7_7, _DATE_7_8)
        assert len(rows) == 1
        assert rows[0]["date"] == _date_to_timestamp(_DATE_7_7)
        assert rows[0]["value"] == 14637051338.896027

        rows = provider.fetch_rows("defi_dex_volume", _DATE_7_7, _DATE_7_8)
        assert len(rows) == 2
        assert rows[0]["date"] == _date_to_timestamp(_DATE_7_7)
        assert rows[0]["value"] == 12066695086.76048
        assert rows[1]["date"] == _date_to_timestamp(_DATE_7_8)
        assert rows[1]["value"] == 1234567890

        rows = provider.fetch_rows("defi_dex_transactions", _DATE_7_7, _DATE_7_8)
        assert len(rows) == 1
        assert rows[0]["date"] == _date_to_timestamp(_DATE_7_7)
        assert rows[0]["value"] == 30908550

def test_get_metric_failed() -> None:
    provider = Birdeye(api_key="xxx")

    with patch.object(
        provider._session, "get", return_value=_make_mock_resp(_RESPONSE_FAILURE)
    ):
        result = provider.get_metric("overview_sol_price", _DATE_7_7, "solana")
        assert result is None

        result = provider.get_metric("stablecoin_supply", _DATE_7_7, "solana")
        assert result is None

        result = provider.get_metric("defi_dex_volume", _DATE_7_7, "solana")
        assert result is None

        result = provider.get_metric("defi_dex_transactions", _DATE_7_7, "solana")
        assert result is None


def test_get_metric_not_supported() -> None:
    provider = Birdeye(api_key="xxx")

    with patch.object(
        provider._session, "get", return_value=_make_mock_resp(_MARKET_HISTORY_RESPONSE)
    ):
        try:
            result = provider.get_metric("defi_dex_count", _DATE_7_7, "solana")
            pytest.fail(f"Expected ValueError for not supported metric, but got result: {result}")
        except ValueError:
            pass
        except Exception as e:
            pytest.fail(f"Unexpected exception raised: {e}")

def test_no_api_key() -> None:
    try:
        provider = Birdeye()
        pytest.fail("Expected ValueError for API key not found")
    except ValueError:
        pass
    except Exception as e:
        pytest.fail(f"Unexpected exception raised: {e}")
        
        