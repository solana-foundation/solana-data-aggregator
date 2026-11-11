"""Unit tests for the DefiLlama provider."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest

from metrics.lending import Lending, LendingMetricType
from metrics.perps import Perps, PerpsMetricType
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
        result = provider.get_metric(
            "stablecoin_circulating_supply", "2026-01-01", "solana"
        )

    assert result is sentinel_metric
    mock_factory.assert_called_once()
    assert (
        mock_factory.call_args.kwargs["metric_type"]
        == StablecoinMetricType.CIRCULATING_SUPPLY
    )
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
        rows = provider.fetch_rows(
            "stablecoin_circulating_supply", "2025-01-01", "2026-06-01"
        )

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
            "Solana": {
                "tvl": [
                    {
                        "date": 1767139200,
                        "totalLiquidityUSD": 0.0,
                    },  # 2025-12-31, nothing deposited yet
                    {"date": 1767225600, "totalLiquidityUSD": 1_000.0},  # 2026-01-01
                    {"date": 1767312000, "totalLiquidityUSD": 1_100.0},  # 2026-01-02
                    {
                        "date": 1767340000,
                        "totalLiquidityUSD": 9_999.0,
                    },  # 2026-01-02 intraday
                ]
            },
            "Solana-borrowed": {
                "tvl": [
                    {"date": 1767225600, "totalLiquidityUSD": 400.0},
                    {"date": 1767312000, "totalLiquidityUSD": 500.0},
                ]
            },
        }
    },
    "save": {
        "chainTvls": {
            "Solana": {
                "tvl": [
                    {"date": 1767225600, "totalLiquidityUSD": 0.0},
                    {"date": 1767312000, "totalLiquidityUSD": 200.0},
                ]
            },
            "Solana-borrowed": {
                "tvl": [
                    {"date": 1767312000, "totalLiquidityUSD": 50.0},
                ]
            },
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
        deposits = provider.fetch_rows(
            "lending_total_deposits", "2026-01-01", "2026-01-02"
        )
        borrowed = provider.fetch_rows(
            "lending_total_borrowed", "2026-01-01", "2026-01-02"
        )
        utilization = provider.fetch_rows(
            "lending_utilization_rate", "2026-01-01", "2026-01-02"
        )
        count = provider.fetch_rows(
            "lending_protocol_count", "2026-01-01", "2026-01-02"
        )

    # Deposits = TVL + borrowed; the intraday point on 2026-01-02 is ignored
    assert deposits == [
        {"date": "2026-01-01", "value": 1_400.0},
        {"date": "2026-01-02", "value": 1_850.0},
    ]
    assert borrowed == [
        {"date": "2026-01-01", "value": 400.0},
        {"date": "2026-01-02", "value": 550.0},
    ]
    # Utilization = total borrowed / total deposits x 100 (ratio of the sums, not an average of ratios)
    assert [r["date"] for r in utilization] == ["2026-01-01", "2026-01-02"]
    assert utilization[0]["value"] == pytest.approx(400 / 1_400 * 100)
    assert utilization[1]["value"] == pytest.approx(550 / 1_850 * 100)
    assert count == [
        {"date": "2026-01-01", "value": 1.0},
        {"date": "2026-01-02", "value": 2.0},
    ]
    # /api/protocols + one call per Solana lending protocol, shared across metrics
    assert mock_get.call_count == 3


def test_fetch_rows_lending_utilization_skips_days_without_deposits() -> None:
    provider = DefiLlama()

    with patch.object(provider._session, "get", side_effect=_lending_get):
        deposits = provider.fetch_rows(
            "lending_total_deposits", "2025-12-31", "2025-12-31"
        )
        utilization = provider.fetch_rows(
            "lending_utilization_rate", "2025-12-31", "2025-12-31"
        )

    assert deposits == [{"date": "2025-12-31", "value": 0.0}]
    assert utilization == []


def test_get_metric_lending_returns_defi_metric() -> None:
    provider = DefiLlama()
    sentinel_metric = object()

    with (
        patch.object(provider._session, "get", side_effect=_lending_get),
        patch.object(
            Lending, "from_metric_type", return_value=sentinel_metric
        ) as mock_factory,
    ):
        result = provider.get_metric("lending_total_deposits", "2026-01-01", "solana")

    assert result is sentinel_metric
    assert (
        mock_factory.call_args.kwargs["metric_type"] == LendingMetricType.TOTAL_DEPOSITS
    )
    assert mock_factory.call_args.kwargs["value"] == 1_400.0


def test_fetch_rows_raises_on_unknown_metric() -> None:
    provider = DefiLlama()
    try:
        provider.fetch_rows("nonexistent_metric", "2026-01-01", "2026-01-31")
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "nonexistent_metric" in str(exc)


# protocol-breakdown chart: [timestamp, {protocol name: value}] per day
_PERPS_BREAKDOWN = [
    [
        1791590400,  # 2026-10-10
        {
            "Jupiter Perpetual Exchange": 65.0,
            "Phoenix Perp": 15.0,
            # GMX Solana not launched yet, so no entry
            "Velocity": 999.0,  # not one of our venues, ignored
        },
    ],
    [
        1791676800,  # 2026-10-11
        {
            "Jupiter Perpetual Exchange": 100.0,
            "Phoenix Perp": 0.0,
            "GMX Solana": 40.0,
            "Velocity": 999.0,
        },
    ],
]


def test_fetch_rows_perps_volume_sums_configured_venues() -> None:
    provider = DefiLlama()

    with patch.object(
        provider._session, "get", return_value=_make_mock_resp(_PERPS_BREAKDOWN)
    ) as mock_get:
        rows = provider.fetch_rows("perps_trading_volume", "2026-10-10", "2026-10-11")

    assert rows == [
        {"date": "2026-10-10", "value": 80.0},
        {"date": "2026-10-11", "value": 140.0},
    ]
    assert mock_get.call_args.args[0].endswith(
        "/api/v2/chart/derivatives/chain/solana/protocol-breakdown"
    )


def test_fetch_rows_perps_open_interest_reads_open_interest_breakdown() -> None:
    provider = DefiLlama()

    with patch.object(
        provider._session, "get", return_value=_make_mock_resp(_PERPS_BREAKDOWN)
    ) as mock_get:
        rows = provider.fetch_rows("perps_open_interest", "2026-10-11", "2026-10-11")

    assert rows == [{"date": "2026-10-11", "value": 140.0}]
    assert mock_get.call_args.args[0].endswith(
        "/api/v2/chart/open-interest/chain/solana/protocol-breakdown"
    )


def test_fetch_rows_perps_venue_count_counts_venues_with_volume() -> None:
    provider = DefiLlama()

    with patch.object(
        provider._session, "get", return_value=_make_mock_resp(_PERPS_BREAKDOWN)
    ):
        rows = provider.fetch_rows("perps_venue_count", "2026-10-10", "2026-10-11")

    # Oct 10: Jupiter + Phoenix; Oct 11: Jupiter + GMX Solana (Phoenix at 0)
    assert rows == [
        {"date": "2026-10-10", "value": 2.0},
        {"date": "2026-10-11", "value": 2.0},
    ]


def test_get_metric_perps_returns_perps_metric() -> None:
    provider = DefiLlama()
    sentinel_metric = object()

    with (
        patch.object(
            provider._session, "get", return_value=_make_mock_resp(_PERPS_BREAKDOWN)
        ),
        patch.object(
            Perps, "from_metric_type", return_value=sentinel_metric
        ) as mock_factory,
    ):
        result = provider.get_metric("perps_trading_volume", "2026-10-11", "solana")

    assert result is sentinel_metric
    assert (
        mock_factory.call_args.kwargs["metric_type"] == PerpsMetricType.TRADING_VOLUME
    )
    assert mock_factory.call_args.kwargs["value"] == 140.0


def _llama_asset(symbol, gecko_id, peg, solana_amount, price=None) -> dict:
    return {
        "symbol": symbol,
        "gecko_id": gecko_id,
        "pegType": peg,
        "price": price,
        "chainCirculating": (
            {"Solana": {"current": {peg: solana_amount}}}
            if solana_amount is not None
            else {}
        ),
    }


def test_fetch_stablecoin_supply_by_token_prices_and_matches_mints() -> None:
    usdc = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    eurc = "HzwqbKZw8HxMN6bF2yFZNrht3c2iXXzpKcFu7uBEDKtr"
    newusd = "NewUSD1111111111111111111111111111111111111"
    xchf = "XCHF11111111111111111111111111111111111111"
    provider = DefiLlama(api_key="")
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    assets = {
        "peggedAssets": [
            _llama_asset("USDC", "usd-coin", "peggedUSD", 1000, price=1.0),
            _llama_asset("EURC", "euro-coin", "peggedEUR", 100, price=1.1),
            _llama_asset("NEWUSD", "new-usd", "peggedUSD", 3),  # no price, USD peg
            # Dropped, like Allium and Dune rows without a mint or a USD value:
            _llama_asset("XEUR", None, "peggedEUR", 5, price=1.1),  # no mint
            _llama_asset("XCHF", "x-chf", "peggedCHF", 7),  # no price, not USD
            _llama_asset("GONE", "gone", "peggedUSD", 0, price=1.0),  # zero on Solana
            _llama_asset("ETHONLY", "eth-only", "peggedUSD", None, price=1.0),
        ]
    }
    coingecko = [
        {"id": "usd-coin", "platforms": {"solana": usdc, "ethereum": "0xa0b8"}},
        {"id": "euro-coin", "platforms": {"solana": eurc}},
        {"id": "new-usd", "platforms": {"solana": newusd}},
        {"id": "x-chf", "platforms": {"solana": xchf}},
        {"id": "eth-only", "platforms": {"ethereum": "0xdead"}},
    ]
    with patch.object(
        provider._session,
        "get",
        side_effect=[_make_mock_resp(assets), _make_mock_resp(coingecko)],
    ):
        rows = provider.fetch_stablecoin_supply_by_token("2000-01-01", "2999-12-31")

    by_token = {r["token"]: r for r in rows}
    assert set(by_token) == {"USDC", "EURC", "NEWUSD"}
    assert all(r["date"] == today for r in rows)
    assert by_token["USDC"] == {
        "date": today,
        "mint_address": usdc,
        "token": "USDC",
        "value": 1000.0,
    }
    assert by_token["EURC"]["mint_address"] == eurc
    assert by_token["EURC"]["value"] == pytest.approx(110.0)
    assert by_token["NEWUSD"]["mint_address"] == newusd
    assert by_token["NEWUSD"]["value"] == 3.0


def test_fetch_stablecoin_supply_by_token_is_empty_outside_today() -> None:
    provider = DefiLlama(api_key="")
    with patch.object(provider._session, "get") as mock_get:
        rows = provider.fetch_stablecoin_supply_by_token("2020-01-01", "2020-01-02")
    assert rows == []
    mock_get.assert_not_called()
