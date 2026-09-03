"""Unit tests for the Token Terminal provider."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from metrics.network import Network, NetworkMetricType
from metrics.overview import Overview, OverviewMetricType
from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.token_terminal import TokenTerminal


def test_get_stablecoin_circulating_supply_sums_native_and_bridged() -> None:
    provider = TokenTerminal(api_key="test-token-terminal-key")
    mock_response = [
        {
            "timestamp": "2026-01-01T00:00:00.000Z",
            "ecosystem_stablecoin_supply": 10_987_267_570.64,
            "ecosystem_bridged_stablecoin_supply": 2_500_000_000.0,
        },
    ]
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
        result = provider.get_metric("stablecoin_circulating_supply", "2026-01-01", "solana")

    assert result is sentinel_metric
    mock_factory.assert_called_once()
    assert mock_factory.call_args.kwargs["metric_type"] == StablecoinMetricType.CIRCULATING_SUPPLY
    # Circulating supply = native issuance + bridged-in supply.
    assert mock_factory.call_args.kwargs["value"] == pytest.approx(13_487_267_570.64)


def test_get_stablecoin_circulating_supply_tolerates_missing_bridged_value() -> None:
    provider = TokenTerminal(api_key="test-token-terminal-key")
    mock_response = [
        {
            "timestamp": "2026-01-01T00:00:00.000Z",
            "ecosystem_stablecoin_supply": 10_987_267_570.64,
        },
    ]
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
        result = provider.get_metric("stablecoin_circulating_supply", "2026-01-01", "solana")

    assert result is sentinel_metric
    assert mock_factory.call_args.kwargs["value"] == 10_987_267_570.64


def test_get_validator_count_returns_network_metric() -> None:
    provider = TokenTerminal(api_key="test-token-terminal-key")
    mock_response = [
        {"timestamp": "2026-01-01T00:00:00.000Z", "number_of_validators": 683},
    ]
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_response
    mock_resp.raise_for_status = MagicMock()
    sentinel_metric = object()

    with (
        patch.object(provider._session, "get", return_value=mock_resp),
        patch.object(
            Network, "from_metric_type", return_value=sentinel_metric
        ) as mock_factory,
    ):
        result = provider.get_metric("network_validator_count", "2026-01-01", "solana")

    assert result is sentinel_metric
    mock_factory.assert_called_once()
    assert (
        mock_factory.call_args.kwargs["metric_type"]
        == NetworkMetricType.VALIDATOR_COUNT
    )
    assert mock_factory.call_args.kwargs["value"] == 683


@pytest.mark.parametrize(
    ("metric", "value_field", "value", "metric_type"),
    [
        (
            "overview_slots",
            "slot_count",
            203507,
            OverviewMetricType.SLOTS,
        ),
        (
            "overview_non_vote_tx_count_success",
            "successful_non_vote_transaction_count",
            89424992,
            OverviewMetricType.TX_COUNT_NON_VOTE_SUCCESS,
        ),
        (
            "overview_non_vote_tx_count_failed",
            "failed_non_vote_transaction_count",
            63705940,
            OverviewMetricType.TX_COUNT_NON_VOTE_FAILED,
        ),
        (
            "overview_compute_units",
            "compute_units_per_block",
            33179623,
            OverviewMetricType.COMPUTE_UNITS,
        ),
    ],
)
def test_overview_metrics_map_to_their_metric_type(
    metric: str, value_field: str, value: int, metric_type: OverviewMetricType
) -> None:
    """Each overview metric reads its own response field and types correctly."""
    provider = TokenTerminal(api_key="test-token-terminal-key")
    mock_resp = MagicMock()
    mock_resp.json.return_value = [
        {"timestamp": "2026-08-03T00:00:00.000Z", value_field: value}
    ]
    mock_resp.raise_for_status = MagicMock()
    sentinel_metric = object()

    with (
        patch.object(provider._session, "get", return_value=mock_resp),
        patch.object(
            Overview, "from_metric_type", return_value=sentinel_metric
        ) as mock_factory,
    ):
        result = provider.get_metric(metric, "2026-08-03", "solana")

    assert result is sentinel_metric
    mock_factory.assert_called_once()
    assert mock_factory.call_args.kwargs["metric_type"] == metric_type
    assert mock_factory.call_args.kwargs["value"] == value


def test_every_supported_metric_has_a_metric_type() -> None:
    """Each entry in METRIC_MAP must resolve to a typed metric model."""
    mapped = (
        set(TokenTerminal._OVERVIEW_METRIC_TYPE_MAP)
        | set(TokenTerminal._STABLECOIN_METRIC_TYPE_MAP)
        | set(TokenTerminal._DEFI_METRIC_TYPE_MAP)
        | set(TokenTerminal._NETWORK_METRIC_TYPE_MAP)
    )
    assert set(TokenTerminal.METRIC_MAP) == mapped
