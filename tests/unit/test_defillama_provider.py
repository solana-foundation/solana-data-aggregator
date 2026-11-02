"""Unit tests for the DefiLlama provider."""

from __future__ import annotations

import io
import tarfile
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


_PEGGED_DATA = """export default [
  {
    id: "1",
    name: "Tether",
    symbol: "USDT",
    gecko_id: "tether",
  },
  {
    id: "2",
    name: "USD Coin",
    symbol: "USDC",
    gecko_id: "usd-coin",
  },
  {
    id: "50",
    name: "EURC",
    symbol: "EURC",
    gecko_id: "euro-coin",
    module: "eurc",
  },
];
"""

_USDC_CONFIG = """export default {
  solana: {
    issued: ["EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"],
    bridgedFromETH: [
      "A9mUU4qviSctJVPJdBJWkb28deg915LYJKrzQ19ji3FM", // wormhole
    ],
    unreleased: [
      "7VHUFJHWu2CuExkJcJrzhQPJ2oygupTWkL2A2For4BmE",
      // "CcG5MeLP6b7maxMEcmucMkoeY9X37sJ5Wk7R97k9hJL9", // retired
      "42qwJUTbKf3D8ULfWadUSjnHf6pkJ4H1VjCcfSKHvDTN",  // wormhole to FOGO
    ], // study the holders page
  },
  tron: {
    issued: ["TEkxiTehnzSmSe2XqrBj4w32RUN966rdz8"],
    unreleased: ["TKHuVq1oKVruCGLvqVexFs6dawKv6fQgFs"],
  },
};
"""

_USDC_INDEX = """const adapter = {
  solana: {
    minted: solanaMintedOrBridged(chainContracts.solana.issued),
    unreleased: solanaUnreleased(),
  },
};
"""

_USDT_INDEX = """const chainContracts = {
  solana: {
    issued: ["Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"],
    unreleased: ["Q6XprfkF8RQQKoQVG33xT88H7wi8Uk1B1CC7YAs69Gi", "A3znyaRYUvi7GbQv1pp9CqqiVo7anddU9rPKFH55V28R"],
  },
  /*
  solana: {
    issued: ["Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"],
    unreleased: ["DBD8hAwLDRQkTsu6EqviaYNGKPnsAMmQonxf7AH8ZcFY"],
  },
  */
};
"""

_EURC_INDEX = """const chainContracts = {
  solana: {
    issued: ["HzwqbKZw8HxMN6bF2yFZNrht3c2iXXzpKcFu7uBEDKtr"],
  },
};
"""

_EURC_SOLANA = """const PREMINT_ACCOUNTS_URL =
  "https://raw.githubusercontent.com/circlefin/centre-ecosystem/master/eurc/solana/minters.json";
"""

_EURC_REGISTRY = {
    "devnet": ["FvtKTZ5EWdCTPAXmYUmqhZryHh2ZXSgvGhZT37TqcSep"],
    "mainnet": ["89LjSs8wP3EZNCKcs8aCxngQaEuyhUyGE4STkFwNgRT3"],
}


def _pegged_assets_tarball() -> bytes:
    files = {
        "src/peggedData/peggedData.ts": _PEGGED_DATA,
        "src/adapters/peggedAssets/usd-coin/config.ts": _USDC_CONFIG,
        "src/adapters/peggedAssets/usd-coin/index.ts": _USDC_INDEX,
        "src/adapters/peggedAssets/tether/index.ts": _USDT_INDEX,
        "src/adapters/peggedAssets/eurc/index.ts": _EURC_INDEX,
        "src/adapters/peggedAssets/eurc/solana.ts": _EURC_SOLANA,
    }
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path, content in files.items():
            data = content.encode()
            info = tarfile.TarInfo(f"peggedassets-server-abc123/{path}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def test_fetch_stablecoin_exclusions_parses_solana_unreleased_lists() -> None:
    provider = DefiLlama()
    tarball_resp = MagicMock()
    tarball_resp.content = _pegged_assets_tarball()
    tarball_resp.raise_for_status = MagicMock()

    def fake_get(url, **kwargs):
        if url.startswith("https://codeload.github.com/"):
            return tarball_resp
        return _make_mock_resp(_EURC_REGISTRY)

    with patch.object(provider._session, "get", side_effect=fake_get) as mock_get:
        rows = provider.fetch_stablecoin_circulating_supply_exclusions()

    tarball_url = mock_get.call_args_list[0].args[0]
    assert tarball_url.endswith("DefiLlama/peggedassets-server/tar.gz/HEAD")
    usdc = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    usdt = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
    eurc = "HzwqbKZw8HxMN6bF2yFZNrht3c2iXXzpKcFu7uBEDKtr"
    # Bridged mints, commented-out addresses, the commented-out block and
    # other chains' lists are not exclusions.
    assert sorted(rows, key=lambda r: r["excluded_address"]) == [
        {
            "token_name": "USDC",
            "token_address": usdc,
            "excluded_address": "42qwJUTbKf3D8ULfWadUSjnHf6pkJ4H1VjCcfSKHvDTN",
            "label": "wormhole to FOGO",
        },
        {
            "token_name": "USDC",
            "token_address": usdc,
            "excluded_address": "7VHUFJHWu2CuExkJcJrzhQPJ2oygupTWkL2A2For4BmE",
            "label": None,
        },
        {
            "token_name": "EURC",
            "token_address": eurc,
            "excluded_address": "89LjSs8wP3EZNCKcs8aCxngQaEuyhUyGE4STkFwNgRT3",
            "label": "Circle pre-mint",
        },
        {
            "token_name": "USDT",
            "token_address": usdt,
            "excluded_address": "A3znyaRYUvi7GbQv1pp9CqqiVo7anddU9rPKFH55V28R",
            "label": None,
        },
        {
            "token_name": "USDT",
            "token_address": usdt,
            "excluded_address": "Q6XprfkF8RQQKoQVG33xT88H7wi8Uk1B1CC7YAs69Gi",
            "label": None,
        },
    ]
