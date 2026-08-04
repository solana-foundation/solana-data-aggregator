"""Integration tests for the Token Terminal provider."""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from metrics.network import Network, NetworkMetricType
from metrics.overview import Overview, OverviewMetricType
from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.token_terminal import TokenTerminal

load_dotenv()
API_KEY = os.environ.get("TOKEN_TERMINAL_API_KEY")


@pytest.mark.integration
def test_get_stablecoin_supply_live_api() -> None:
    """Calls Token Terminal API directly and validates response mapping."""
    if not API_KEY:
        pytest.skip(
            "Set TOKEN_TERMINAL_API_KEY to run live Token Terminal integration tests."
        )

    provider = TokenTerminal(api_key=API_KEY)
    metric = provider.get_metric(
        metric="stablecoin_supply",
        date="2025-01-01",
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, Stablecoin)
    assert metric.metric_type == StablecoinMetricType.SUPPLY
    assert metric.value >= 0


@pytest.mark.integration
def test_get_validator_count_live_api() -> None:
    """Validator count is served on the network page and must be a positive count."""
    if not API_KEY:
        pytest.skip(
            "Set TOKEN_TERMINAL_API_KEY to run live Token Terminal integration tests."
        )

    provider = TokenTerminal(api_key=API_KEY)
    metric = provider.get_metric(
        metric="network_validator_count",
        date="2025-01-01",
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, Network)
    assert metric.metric_type == NetworkMetricType.VALIDATOR_COUNT
    assert metric.value > 0


@pytest.mark.integration
@pytest.mark.parametrize(
    ("metric", "metric_type", "low", "high"),
    [
        ("overview_slots", OverviewMetricType.SLOTS, 150_000, 250_000),
        (
            "overview_non_vote_tx_count_success",
            OverviewMetricType.TX_COUNT_NON_VOTE_SUCCESS,
            10_000_000,
            500_000_000,
        ),
        (
            "overview_non_vote_tx_count_failed",
            OverviewMetricType.TX_COUNT_NON_VOTE_FAILED,
            1_000_000,
            500_000_000,
        ),
        (
            "overview_compute_units",
            OverviewMetricType.COMPUTE_UNITS,
            5_000_000,
            100_000_000,
        ),
    ],
)
def test_overview_metrics_live_api(
    metric: str, metric_type: OverviewMetricType, low: int, high: int
) -> None:
    """Each new overview metric resolves against the live API and is in range.

    The bounds are wide on purpose: they catch a wrong metric_id or value_field,
    which would otherwise surface as an empty series rather than an error.
    """
    if not API_KEY:
        pytest.skip(
            "Set TOKEN_TERMINAL_API_KEY to run live Token Terminal integration tests."
        )

    provider = TokenTerminal(api_key=API_KEY)
    result = provider.get_metric(metric=metric, date="2026-08-03", chain="solana")

    assert result is not None
    assert isinstance(result, Overview)
    assert result.metric_type == metric_type
    assert low < result.value < high
