"""Unit tests for the Token Terminal provider."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from metrics.lending import Lending
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
        result = provider.get_metric(
            "stablecoin_circulating_supply", "2026-01-01", "solana"
        )

    assert result is sentinel_metric
    mock_factory.assert_called_once()
    assert (
        mock_factory.call_args.kwargs["metric_type"]
        == StablecoinMetricType.CIRCULATING_SUPPLY
    )
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
        result = provider.get_metric(
            "stablecoin_circulating_supply", "2026-01-01", "solana"
        )

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
        | set(TokenTerminal._LENDING_METRIC_TYPE_MAP)
        | set(TokenTerminal._NETWORK_METRIC_TYPE_MAP)
    )
    assert set(TokenTerminal.METRIC_MAP) == mapped


def _lending_row(product, date, deposits, borrowed):
    return {
        "timestamp": date,
        "chain_id": "solana",
        "product_id": product,
        "tvl": deposits,
        "active_loans": borrowed,
    }


def _lending_provider(kamino, jupiter):
    provider = TokenTerminal(api_key="test-key")

    def get(endpoint, *, params=None):
        assert params["metric_ids"] == "tvl,active_loans"
        assert params["chain_ids"] == "solana"
        if endpoint == "/projects/kamino/products/kaminolend/metrics":
            return {"data": kamino}
        if endpoint == "/projects/jupiter/products/jupiterlend/metrics":
            return {"data": jupiter}
        raise AssertionError(endpoint)

    provider._get = MagicMock(side_effect=get)
    return provider


def test_lending_uses_supplied_tvl_and_ratio_of_aligned_sums():
    provider = _lending_provider(
        [_lending_row("kaminolend", "2026-01-01", 100, 20)],
        [_lending_row("jupiterlend", "2026-01-01", 300, 180)],
    )
    expected = {
        "lending_total_deposits": 400,
        "lending_total_borrowed": 200,
        "lending_utilization_rate": 50,
        "lending_protocol_count": 2,
    }
    for metric, value in expected.items():
        result = provider.get_metric(metric, "2026-01-01", "solana")
        assert isinstance(result, Lending)
        assert result.value == value
        assert result.metric_type == provider._LENDING_METRIC_TYPE_MAP[metric]
    assert provider._get.call_count == 2


def test_lending_history_membership_and_missing_rows():
    provider = _lending_provider(
        [
            _lending_row("kaminolend", "2024-08-01", 100, 20),
            _lending_row("kaminolend", "2025-08-01", 200, 40),
            _lending_row("kaminolend", "2025-08-02", 250, 50),
        ],
        [
            _lending_row("jupiterlend", "2025-08-01", 100, 10),
            _lending_row("jupiterlend", "2025-08-03", 100, 10),
        ],
    )
    assert provider.fetch_rows(
        "lending_protocol_count", "2024-08-01", "2024-08-01"
    ) == [
        {"date": "2024-08-01", "value": 1},
    ]
    for metric in provider._LENDING_METRIC_TYPE_MAP:
        assert provider.fetch_rows(metric, "2025-08-02", "2025-08-03") == []


def test_lending_zero_deposits_have_no_utilization_or_active_protocols():
    provider = _lending_provider(
        [_lending_row("kaminolend", "2026-01-01", 0, 0)],
        [_lending_row("jupiterlend", "2026-01-01", 0, 0)],
    )
    assert (
        provider.fetch_rows("lending_utilization_rate", "2026-01-01", "2026-01-01")
        == []
    )
    assert provider.fetch_rows(
        "lending_protocol_count", "2026-01-01", "2026-01-01"
    ) == [
        {"date": "2026-01-01", "value": 0},
    ]


def test_lending_partial_success_is_not_a_partial_total():
    provider = TokenTerminal(api_key="test-key")
    with patch.object(
        provider, "_get", return_value={"data": [], "errors": [{"code": "NOT_FOUND"}]}
    ):
        with pytest.raises(ValueError, match="Incomplete lending"):
            provider.fetch_rows("lending_total_deposits", "2026-01-01", "2026-01-01")


@pytest.mark.parametrize("value", [None, float("nan"), -1])
def test_lending_invalid_or_missing_balances_fail(value):
    provider = _lending_provider(
        [_lending_row("kaminolend", "2026-01-01", value, 20)],
        [_lending_row("jupiterlend", "2026-01-01", 300, 180)],
    )
    with pytest.raises(ValueError):
        provider.fetch_rows("lending_total_deposits", "2026-01-01", "2026-01-01")


def test_lending_rejects_duplicate_product_days():
    row = _lending_row("kaminolend", "2026-01-01", 100, 20)
    provider = _lending_provider(
        [row, row], [_lending_row("jupiterlend", "2026-01-01", 300, 180)]
    )
    with pytest.raises(ValueError, match="Duplicate lending"):
        provider.fetch_rows("lending_total_deposits", "2026-01-01", "2026-01-01")
