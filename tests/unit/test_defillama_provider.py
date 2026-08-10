"""Unit tests for the DefiLlama provider."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

from metrics.prediction_market import PredictionMarket, PredictionMarketMetricType
from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.defillama import DefiLlama

_MOCK_RAW = [
    {
        "date": "1767225600",
        "totalCirculating": {"peggedUSD": 5_000_000_000.0},
    },  # 2026-01-01
]


def _make_mock_resp(payload):
    mock_resp = MagicMock()
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def test_get_stablecoin_supply_returns_stablecoin_metric() -> None:
    provider = DefiLlama()
    sentinel_metric = object()

    with (
        patch.object(provider._session, "get", return_value=_make_mock_resp(_MOCK_RAW)),
        patch.object(
            Stablecoin, "from_metric_type", return_value=sentinel_metric
        ) as mock_factory,
    ):
        result = provider.get_metric("stablecoin_supply", "2026-01-01", "solana")

    assert result is sentinel_metric
    mock_factory.assert_called_once()
    assert mock_factory.call_args.kwargs["metric_type"] == StablecoinMetricType.SUPPLY
    assert mock_factory.call_args.kwargs["value"] == 5_000_000_000.0


def test_fetch_rows_filters_by_date_range() -> None:
    provider = DefiLlama()
    raw = [
        {
            "date": "1704067200",
            "totalCirculating": {"peggedUSD": 1_000.0},
        },  # 2024-01-01
        {
            "date": "1767225600",
            "totalCirculating": {"peggedUSD": 5_000_000_000.0},
        },  # 2026-01-01
        {
            "date": "1798761600",
            "totalCirculating": {"peggedUSD": 9_000_000_000.0},
        },  # 2027-01-01
    ]

    with patch.object(provider._session, "get", return_value=_make_mock_resp(raw)):
        rows = provider.fetch_rows("stablecoin_supply", "2025-01-01", "2026-06-01")

    assert len(rows) == 1
    assert rows[0]["date"] == "2026-01-01"
    assert rows[0]["value"] == 5_000_000_000.0


def test_fetch_rows_raises_on_unknown_metric() -> None:
    provider = DefiLlama()
    try:
        provider.fetch_rows("nonexistent_metric", "2026-01-01", "2026-01-31")
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "nonexistent_metric" in str(exc)


_MOCK_PM_PROTOCOLS = [
    {"slug": "alpha-markets", "category": "Prediction Market", "chains": ["Solana"]},
    {
        "slug": "beta-bets",
        "category": "Prediction Market",
        "chains": ["Ethereum", "Solana"],
    },
    {"slug": "gamma-dex", "category": "Dexes", "chains": ["Solana"]},
    {"slug": "delta-markets", "category": "Prediction Market", "chains": ["Ethereum"]},
]
_MOCK_PM_ALPHA = {
    "chainTvls": {
        "Solana": {
            "tvl": [
                {"date": 1767139200, "totalLiquidityUSD": 999.0},  # 2025-12-31
                {"date": 1767225600, "totalLiquidityUSD": 100.0},  # 2026-01-01
                {"date": 1767312000, "totalLiquidityUSD": 120.0},  # 2026-01-02 00:00
                {"date": 1767355200, "totalLiquidityUSD": 150.0},  # 2026-01-02 12:00
            ]
        }
    }
}
_MOCK_PM_BETA = {
    "chainTvls": {
        "Solana": {
            "tvl": [
                {"date": 1767225600, "totalLiquidityUSD": 50.0},  # 2026-01-01
                {"date": 1767312000, "totalLiquidityUSD": 0.0},  # 2026-01-02
            ]
        }
    }
}


def _make_pm_session_mock() -> MagicMock:
    """One listing call, then one detail call per prediction market slug."""
    return MagicMock(
        side_effect=[
            _make_mock_resp(_MOCK_PM_PROTOCOLS),
            _make_mock_resp(_MOCK_PM_ALPHA),
            _make_mock_resp(_MOCK_PM_BETA),
        ]
    )


def test_fetch_rows_prediction_market_tvl_sums_solana_protocols() -> None:
    provider = DefiLlama()

    with patch.object(provider._session, "get", _make_pm_session_mock()):
        rows = provider.fetch_rows("prediction_market_tvl", "2026-01-01", "2026-01-02")

    assert rows == [
        {"date": "2026-01-01", "value": 150.0},
        {"date": "2026-01-02", "value": 150.0},
    ]


def test_get_metric_prediction_market_tvl_returns_typed_metric() -> None:
    provider = DefiLlama()

    with patch.object(provider._session, "get", _make_pm_session_mock()):
        result = provider.get_metric("prediction_market_tvl", "2026-01-01", "solana")

    assert isinstance(result, PredictionMarket)
    assert result.metric_type == PredictionMarketMetricType.TVL
    assert result.value == 150.0
    assert result.date == datetime.date(2026, 1, 1)
