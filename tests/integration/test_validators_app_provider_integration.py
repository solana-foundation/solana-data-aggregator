"""Integration tests for the ValidatorsApp provider."""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from metrics.network import Network, NetworkMetricType
from providers.validators_app import ValidatorsApp

load_dotenv()
API_TOKEN = os.environ.get("VALIDATORS_APP_API_TOKEN")


def _provider():
    if not API_TOKEN:
        pytest.skip(
            "Set VALIDATORS_APP_API_TOKEN to run live ValidatorsApp integration tests."
        )
    return ValidatorsApp(api_token=API_TOKEN)


@pytest.mark.integration
def test_get_total_stake_live_api() -> None:
    import datetime

    provider = _provider()
    today = datetime.date.today().isoformat()
    metric = provider.get_metric("network_total_stake", today, "solana")

    assert metric is not None
    assert isinstance(metric, Network)
    assert metric.metric_type == NetworkMetricType.TOTAL_STAKE
    assert metric.value > 0
