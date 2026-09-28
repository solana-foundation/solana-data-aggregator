"""Unit tests for the Blockworks provider."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from metrics.defi import Defi, DefiMetricType
from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.blockworks import Blockworks


def test_get_stablecoin_total_supply_returns_stablecoin_metric() -> None:
    provider = Blockworks(api_key="key")
    mock_response = {
        "solana": [
            {"date": "2026-01-01", "value": 5_000_000_000.0},
        ]
    }
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_response
    mock_resp.raise_for_status = MagicMock()
    sentinel_metric = object()

    with (
        patch.object(provider._session, "get", return_value=mock_resp),
        patch.object(
            Stablecoin, "from_metric_type", return_value=sentinel_metric
        ) as mock_factory,
    ):
        result = provider.get_metric("stablecoin_total_supply", "2026-01-01", "solana")

    assert result is sentinel_metric
    mock_factory.assert_called_once()
    assert mock_factory.call_args.kwargs["metric_type"] == StablecoinMetricType.TOTAL_SUPPLY
    assert mock_factory.call_args.kwargs["value"] == 5_000_000_000.0


# Charts 7653 / 7655 share one daily lending table
_LENDING_ROWS = [
    {
        "dt": "2026-09-26", "total_deposit": 5_148_000_000.0, "total_borrow": 2_010_000_000.0,
        "total_dep_utilization": 0.3904,
        # Jupiter Lend not live yet; the "other" bucket isn't a protocol and isn't counted
        "protocol_deposit_kamino": 5_148_000_000.0, "protocol_deposit_jup_lend": None,
        "protocol_deposit_other": 1_000.0,
    },
    {
        "dt": "2026-09-27", "total_deposit": 5_171_000_000.0, "total_borrow": 2_019_000_000.0,
        "total_dep_utilization": 0.3905,
        "protocol_deposit_kamino": 2_781_000_000.0, "protocol_deposit_jup_lend": 2_390_000_000.0,
        # A protocol Blockworks adds later is counted without a code change
        "protocol_deposit_marginfi": 50_000_000.0,
        "protocol_deposit_other": None,
        # Different column family (protocol_stablecoin_deposits_*), not counted
        "protocol_stablecoin_deposits_kamino": 1_090_000_000.0,
    },
]


def _chart_resp(rows):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": rows, "page": 1, "total": len(rows)}
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def test_fetch_rows_lending_metrics_read_chart_columns() -> None:
    provider = Blockworks(api_key="key")

    with patch.object(provider._session, "get", return_value=_chart_resp(_LENDING_ROWS)) as mock_get:
        deposits = provider.fetch_rows("defi_lending_total_deposits", "2026-09-27", "2026-09-27")
        utilization = provider.fetch_rows("defi_lending_utilization_rate", "2026-09-26", "2026-09-27")
        borrowed = provider.fetch_rows("defi_lending_total_borrowed", "2026-09-27", "2026-09-27")
        count = provider.fetch_rows("defi_lending_protocol_count", "2026-09-26", "2026-09-27")

    assert deposits == [{"date": "2026-09-27", "value": 5_171_000_000.0}]
    # protocol_deposit_* columns with deposits > 0, excluding the "other" bucket
    assert count == [
        {"date": "2026-09-26", "value": 1.0},
        {"date": "2026-09-27", "value": 3.0},
    ]
    assert borrowed == [{"date": "2026-09-27", "value": 2_019_000_000.0}]
    # Blockworks' 0-1 ratio is stored as a 0-100 percentage
    assert [r["value"] for r in utilization] == [pytest.approx(39.04), pytest.approx(39.05)]
    # Deposits, utilization and protocol count share chart 7653 (fetched once); borrowed is chart 7655
    requested = [c.args[0].rsplit("/charts/", 1)[-1] for c in mock_get.call_args_list]
    assert requested == ["7653/data", "7655/data"]


def test_get_metric_lending_utilization_returns_defi_metric() -> None:
    provider = Blockworks(api_key="key")
    sentinel_metric = object()

    with (
        patch.object(provider._session, "get", return_value=_chart_resp(_LENDING_ROWS)),
        patch.object(Defi, "from_metric_type", return_value=sentinel_metric) as mock_factory,
    ):
        result = provider.get_metric("defi_lending_utilization_rate", "2026-09-27", "solana")

    assert result is sentinel_metric
    assert mock_factory.call_args.kwargs["metric_type"] == DefiMetricType.LENDING_UTILIZATION_RATE
    assert mock_factory.call_args.kwargs["value"] == pytest.approx(39.05)
