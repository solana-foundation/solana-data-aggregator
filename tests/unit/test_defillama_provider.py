"""Unit tests for the DefiLlama provider."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from metrics.defi import Defi, DefiMetricType
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


def test_get_stablecoin_circulating_supply_returns_stablecoin_metric() -> None:
    provider = DefiLlama()
    sentinel_metric = object()

    with (
        patch.object(provider._session, "get", return_value=_make_mock_resp(_MOCK_RAW)),
        patch.object(
            Stablecoin, "from_metric_type", return_value=sentinel_metric
        ) as mock_factory,
    ):
        result = provider.get_metric("stablecoin_circulating_supply", "2026-01-01", "solana")

    assert result is sentinel_metric
    mock_factory.assert_called_once()
    assert mock_factory.call_args.kwargs["metric_type"] == StablecoinMetricType.CIRCULATING_SUPPLY
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
        rows = provider.fetch_rows("stablecoin_circulating_supply", "2025-01-01", "2026-06-01")

    assert len(rows) == 1
    assert rows[0]["date"] == "2026-01-01"
    assert rows[0]["value"] == 5_000_000_000.0


_LENDING_PROTOCOLS = [
    {"slug": "kamino-lend", "category": "Lending", "chains": ["Solana"]},
    {"slug": "save", "category": "Lending", "chains": ["Solana"]},
    {"slug": "aave-v3", "category": "Lending", "chains": ["Ethereum"]},
    {"slug": "raydium", "category": "Dexs", "chains": ["Solana"]},
]

_LENDING_DETAILS = {
    "kamino-lend": {
        "chainTvls": {
            "Solana": {"tvl": [
                {"date": 1767225600, "totalLiquidityUSD": 1_000.0},  # 2026-01-01
                {"date": 1767312000, "totalLiquidityUSD": 1_100.0},  # 2026-01-02
                {"date": 1767340000, "totalLiquidityUSD": 9_999.0},  # 2026-01-02 intraday
            ]},
            "Solana-borrowed": {"tvl": [
                {"date": 1767225600, "totalLiquidityUSD": 400.0},
                {"date": 1767312000, "totalLiquidityUSD": 500.0},
            ]},
        }
    },
    "save": {
        "chainTvls": {
            "Solana": {"tvl": [
                {"date": 1767225600, "totalLiquidityUSD": 0.0},
                {"date": 1767312000, "totalLiquidityUSD": 200.0},
            ]},
            "Solana-borrowed": {"tvl": [
                {"date": 1767312000, "totalLiquidityUSD": 50.0},
            ]},
        }
    },
}


def _lending_get(url, params=None, timeout=None):
    if url.endswith("/api/protocols"):
        return _make_mock_resp(_LENDING_PROTOCOLS)
    return _make_mock_resp(_LENDING_DETAILS[url.rsplit("/", 1)[-1]])


def test_fetch_rows_lending_aggregates_solana_lending_protocols() -> None:
    provider = DefiLlama()

    with patch.object(provider._session, "get", side_effect=_lending_get) as mock_get:
        deposits = provider.fetch_rows("defi_lending_total_deposits", "2026-01-01", "2026-01-02")
        borrowed = provider.fetch_rows("defi_lending_total_borrowed", "2026-01-01", "2026-01-02")
        loans = provider.fetch_rows("defi_lending_active_loans", "2026-01-01", "2026-01-02")
        count = provider.fetch_rows("defi_lending_protocol_count", "2026-01-01", "2026-01-02")

    # Deposits = TVL + borrowed; the intraday point on 2026-01-02 is ignored
    assert deposits == [
        {"date": "2026-01-01", "value": 1_400.0},
        {"date": "2026-01-02", "value": 1_850.0},
    ]
    assert borrowed == [
        {"date": "2026-01-01", "value": 400.0},
        {"date": "2026-01-02", "value": 550.0},
    ]
    assert loans == borrowed
    assert count == [
        {"date": "2026-01-01", "value": 1.0},
        {"date": "2026-01-02", "value": 2.0},
    ]
    # /api/protocols + one call per Solana lending protocol, shared across metrics
    assert mock_get.call_count == 3


def test_get_metric_lending_returns_defi_metric() -> None:
    provider = DefiLlama()
    sentinel_metric = object()

    with (
        patch.object(provider._session, "get", side_effect=_lending_get),
        patch.object(Defi, "from_metric_type", return_value=sentinel_metric) as mock_factory,
    ):
        result = provider.get_metric("defi_lending_total_deposits", "2026-01-01", "solana")

    assert result is sentinel_metric
    assert mock_factory.call_args.kwargs["metric_type"] == DefiMetricType.LENDING_TOTAL_DEPOSITS
    assert mock_factory.call_args.kwargs["value"] == 1_400.0


def test_fetch_rows_raises_on_unknown_metric() -> None:
    provider = DefiLlama()
    try:
        provider.fetch_rows("nonexistent_metric", "2026-01-01", "2026-01-31")
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "nonexistent_metric" in str(exc)
