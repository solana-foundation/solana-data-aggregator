"""Integration tests for the DefiLlama provider."""

from __future__ import annotations

import datetime
import os

import pytest
from dotenv import load_dotenv

from metrics.prediction_market import PredictionMarket, PredictionMarketMetricType
from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.defillama import DefiLlama

load_dotenv()
API_KEY = os.environ.get("DEFILLAMA_API_KEY")

_YESTERDAY = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()


@pytest.mark.integration
def test_get_stablecoin_supply_live_api() -> None:
    """Calls DefiLlama API directly and validates response mapping."""
    if not API_KEY:
        pytest.skip("Set DEFILLAMA_API_KEY to run live DefiLlama integration tests.")

    provider = DefiLlama(api_key=API_KEY)
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
def test_get_prediction_market_tvl_live_api() -> None:
    """Prediction market TVL on Solana should be a positive USD value."""
    if not API_KEY:
        pytest.skip("Set DEFILLAMA_API_KEY to run live DefiLlama integration tests.")

    provider = DefiLlama(api_key=API_KEY)
    metric = provider.get_metric(
        metric="prediction_market_tvl",
        date=_YESTERDAY,
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, PredictionMarket)
    assert metric.metric_type == PredictionMarketMetricType.TVL
    assert metric.value > 0
