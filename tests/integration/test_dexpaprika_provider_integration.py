"""Integration tests for the DexPaprika provider."""

from __future__ import annotations

import datetime

import pytest

from metrics.defi import Defi, DefiMetricType
from metrics.overview import Overview, OverviewMetricType
from providers.dexpaprika import DexPaprika

_TODAY = datetime.date.today().isoformat()


@pytest.mark.integration
def test_get_dex_volume_live_api() -> None:
    """Calls the DexPaprika public API directly and validates response mapping."""
    provider = DexPaprika()
    metric = provider.get_metric(
        metric="defi_dex_volume",
        date=_TODAY,
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, Defi)
    assert metric.metric_type == DefiMetricType.DEX_VOLUME
    assert metric.value > 0


@pytest.mark.integration
def test_get_dex_transactions_live_api() -> None:
    """Confirms the txns_24h response key exists and maps end-to-end."""
    provider = DexPaprika()
    metric = provider.get_metric(
        metric="defi_dex_transactions",
        date=_TODAY,
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, Defi)
    assert metric.metric_type == DefiMetricType.DEX_TRANSACTIONS
    assert metric.value > 0


@pytest.mark.integration
def test_get_dex_count_live_api() -> None:
    """DEX count for Solana should be a positive whole number."""
    provider = DexPaprika()
    metric = provider.get_metric(
        metric="defi_dex_count",
        date=_TODAY,
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, Defi)
    assert metric.metric_type == DefiMetricType.DEX_COUNT
    assert metric.value >= 1
    assert metric.value == int(metric.value)


@pytest.mark.integration
def test_get_sol_price_live_api() -> None:
    """SOL price for Solana should be a positive USD value."""
    provider = DexPaprika()
    metric = provider.get_metric(
        metric="overview_sol_price",
        date=_TODAY,
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, Overview)
    assert metric.metric_type == OverviewMetricType.SOL_PRICE
    assert metric.value > 0
