"""Unit tests for the Blockworks provider."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from metrics.lending import Lending, LendingMetricType
from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.blockworks import SOLANA_NETWORK_ID, Blockworks


def _mock_response(body: dict) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.json.return_value = body
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def test_get_stablecoin_total_supply_returns_stablecoin_metric() -> None:
    provider = Blockworks(api_key="key")
    mock_resp = _mock_response(
        {
            "error": None,
            "data": {
                "point_schema": [
                    {"field": "time", "time": True},
                    {"field": "stablecoin-outstanding-supply-usd", "time": False},
                ],
                "points": [[1767225600, 5_000_000_000.0]],  # 2026-01-01T00:00:00Z
            },
        }
    )
    sentinel_metric = object()

    with (
        patch.object(provider._session, "get", return_value=mock_resp) as mock_get,
        patch.object(
            Stablecoin, "from_metric_type", return_value=sentinel_metric
        ) as mock_factory,
    ):
        result = provider.get_metric("stablecoin_total_supply", "2026-01-01", "solana")

    assert result is sentinel_metric
    assert mock_get.call_args.args[0] == (
        f"https://api.blockworks.com/query/timeseries/blockchains/1d/{SOLANA_NETWORK_ID}"
    )
    assert mock_get.call_args.kwargs["headers"] == {"X-Blockworks-API-Key": "key"}
    # `end` is exclusive in the Data API, so it is one day past the requested date.
    assert mock_get.call_args.kwargs["params"] == {
        "start": "2026-01-01",
        "end": "2026-01-02",
        "selections": "stablecoin-outstanding-supply-usd",
    }
    mock_factory.assert_called_once()
    assert (
        mock_factory.call_args.kwargs["metric_type"]
        == StablecoinMetricType.TOTAL_SUPPLY
    )
    assert mock_factory.call_args.kwargs["value"] == 5_000_000_000.0


def test_fetch_rows_skips_null_values() -> None:
    provider = Blockworks(api_key="key")
    mock_resp = _mock_response(
        {
            "error": None,
            "data": {
                "point_schema": [
                    {"field": "time", "time": True},
                    {"field": "active-addresses", "time": False},
                ],
                "points": [[1767225600, 2_000_000], [1767312000, None]],
            },
        }
    )

    with patch.object(provider._session, "get", return_value=mock_resp):
        rows = provider.fetch_rows("overview_fee_payers", "2026-01-01", "2026-01-02")

    assert rows == [{"date": "2026-01-01", "value": 2_000_000.0}]


def test_fetch_rows_raises_on_api_error() -> None:
    provider = Blockworks(api_key="key")
    mock_resp = _mock_response({"error": "unknown query parameter", "data": None})

    with (
        patch.object(provider._session, "get", return_value=mock_resp),
        pytest.raises(RuntimeError, match="unknown query parameter"),
    ):
        provider.fetch_rows("defi_dex_volume", "2026-01-01", "2026-01-01")


# Chart 15954: one row per day with totals and per-protocol columns
_LENDING_ROWS = [
    {
        "dt": "2026-09-26",
        "total_deposit": 5_000_000_000.0,
        "total_borrow": 2_000_000_000.0,
        "total_stablecoin_deposit": 2_000_000_000.0,
        "kamino_deposit": 5_000_000_000.0,
        "kamino_borrow": 2_000_000_000.0,
        "kamino_stablecoin_deposit": 2_000_000_000.0,
        # Jupiter Lend not live yet
        "jupiter_deposit": None,
        "jupiter_borrow": None,
        "jupiter_stablecoin_deposit": None,
    },
    {
        "dt": "2026-09-27",
        "total_deposit": 5_200_000_000.0,
        "total_borrow": 2_080_000_000.0,
        "total_stablecoin_deposit": 2_100_000_000.0,
        "kamino_deposit": 2_800_000_000.0,
        "kamino_borrow": 1_100_000_000.0,
        "kamino_stablecoin_deposit": 1_000_000_000.0,
        "jupiter_deposit": 2_350_000_000.0,
        "jupiter_borrow": 960_000_000.0,
        "jupiter_stablecoin_deposit": 1_100_000_000.0,
        # A protocol Blockworks adds later is counted without a code change
        "marginfi_deposit": 50_000_000.0,
        "marginfi_borrow": 20_000_000.0,
    },
]


def _chart_response(rows: list) -> MagicMock:
    return _mock_response({"data": rows, "page": 1, "total": len(rows)})


def test_fetch_rows_lending_metrics_read_chart_columns() -> None:
    provider = Blockworks(api_key="key")

    with patch.object(
        provider._session, "get", return_value=_chart_response(_LENDING_ROWS)
    ) as mock_get:
        deposits = provider.fetch_rows(
            "lending_total_deposits", "2026-09-27", "2026-09-27"
        )
        borrowed = provider.fetch_rows(
            "lending_total_borrowed", "2026-09-27", "2026-09-27"
        )
        utilization = provider.fetch_rows(
            "lending_utilization_rate", "2026-09-26", "2026-09-27"
        )
        count = provider.fetch_rows(
            "lending_protocol_count", "2026-09-26", "2026-09-27"
        )

    assert deposits == [{"date": "2026-09-27", "value": 5_200_000_000.0}]
    assert borrowed == [{"date": "2026-09-27", "value": 2_080_000_000.0}]
    # borrow / deposit as a 0-100 percentage
    assert [r["value"] for r in utilization] == [
        pytest.approx(40.0),
        pytest.approx(40.0),
    ]
    # <protocol>_deposit columns > 0, excluding total_* and *_stablecoin_deposit
    assert count == [
        {"date": "2026-09-26", "value": 1.0},
        {"date": "2026-09-27", "value": 3.0},
    ]
    # All four metrics share chart 15954, fetched once
    mock_get.assert_called_once()
    assert mock_get.call_args.args[0] == (
        "https://api.blockworks.com/v1/charts/15954/data"
    )
    assert mock_get.call_args.kwargs["headers"] == {"X-Blockworks-API-Key": "key"}


def test_get_metric_lending_utilization_returns_lending_metric() -> None:
    provider = Blockworks(api_key="key")
    sentinel_metric = object()

    with (
        patch.object(
            provider._session, "get", return_value=_chart_response(_LENDING_ROWS)
        ),
        patch.object(
            Lending, "from_metric_type", return_value=sentinel_metric
        ) as mock_factory,
    ):
        result = provider.get_metric("lending_utilization_rate", "2026-09-27", "solana")

    assert result is sentinel_metric
    assert (
        mock_factory.call_args.kwargs["metric_type"]
        == LendingMetricType.UTILIZATION_RATE
    )
    assert mock_factory.call_args.kwargs["value"] == pytest.approx(40.0)
