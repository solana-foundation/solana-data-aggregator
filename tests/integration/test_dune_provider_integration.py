"""Integration tests for the Dune provider."""

from __future__ import annotations

import datetime
import os

import pytest
from dotenv import load_dotenv

from metrics.prediction_market import PredictionMarket, PredictionMarketMetricType
from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.dune import Dune

load_dotenv()
API_KEY = os.environ.get("DUNE_API_KEY")

_YESTERDAY = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()


@pytest.mark.integration
def test_get_stablecoin_supply_live_api() -> None:
    """Calls Dune API directly and validates response mapping."""
    if not API_KEY:
        pytest.skip("Set DUNE_API_KEY to run live Dune integration tests.")

    provider = Dune(api_key=API_KEY)
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
def test_get_prediction_market_transactions_live_api() -> None:
    """Prediction market programs should show daily transactions on Solana."""
    if not API_KEY:
        pytest.skip("Set DUNE_API_KEY to run live Dune integration tests.")

    provider = Dune(api_key=API_KEY)
    metric = provider.get_metric(
        metric="prediction_market_transactions",
        date=_YESTERDAY,
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, PredictionMarket)
    assert metric.metric_type == PredictionMarketMetricType.TRANSACTIONS
    assert metric.value > 0


@pytest.mark.integration
def test_get_prediction_market_count_live_api() -> None:
    """At least one prediction market protocol should be active on Solana."""
    if not API_KEY:
        pytest.skip("Set DUNE_API_KEY to run live Dune integration tests.")

    provider = Dune(api_key=API_KEY)
    metric = provider.get_metric(
        metric="prediction_market_count",
        date=_YESTERDAY,
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, PredictionMarket)
    assert metric.metric_type == PredictionMarketMetricType.COUNT
    assert metric.value >= 1


@pytest.mark.integration
def test_get_prediction_market_volume_live_api() -> None:
    """Decoded prediction market trade volume should be a positive USD value."""
    if not API_KEY:
        pytest.skip("Set DUNE_API_KEY to run live Dune integration tests.")

    provider = Dune(api_key=API_KEY)
    metric = provider.get_metric(
        metric="prediction_market_volume",
        date=_YESTERDAY,
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, PredictionMarket)
    assert metric.metric_type == PredictionMarketMetricType.VOLUME
    assert metric.value > 0


@pytest.mark.integration
def test_get_prediction_market_users_live_api() -> None:
    """Prediction market programs should show daily unique users on Solana."""
    if not API_KEY:
        pytest.skip("Set DUNE_API_KEY to run live Dune integration tests.")

    provider = Dune(api_key=API_KEY)
    metric = provider.get_metric(
        metric="prediction_market_users",
        date=_YESTERDAY,
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, PredictionMarket)
    assert metric.metric_type == PredictionMarketMetricType.USERS
    assert metric.value > 0
