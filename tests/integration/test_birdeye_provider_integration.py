"""Integration tests for the Birdeye provider."""

from __future__ import annotations

import os
import datetime
from dotenv import load_dotenv
import pytest

from metrics.defi import Defi, DefiMetricType
from metrics.overview import Overview, OverviewMetricType
from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.birdeye import Birdeye

load_dotenv()
API_KEY = os.environ.get("BIRDEYE_API_KEY")

_TODAY = datetime.date.today()
_TODAY_STR = _TODAY.isoformat()

def _date_to_timestamp(date_str: str) -> int:
    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
    return int(dt.timestamp())

@pytest.mark.integration
def test_get_sol_price_live_api() -> None:
    """SOL price for Solana should be a positive USD value."""
    provider = Birdeye(api_key=API_KEY)
    metric = provider.get_metric(
        metric="overview_sol_price",
        date=_TODAY_STR,
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, Overview)
    assert metric.metric_type == OverviewMetricType.SOL_PRICE
    assert metric.value > 0

@pytest.mark.integration
def test_get_stablecoin_supply_live_api() -> None:
    """Stablecoin supply for Solana should be a positive value."""
    provider = Birdeye(api_key=API_KEY)
    metric = provider.get_metric(
        metric="stablecoin_supply",
        date=_TODAY_STR,
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, Stablecoin)
    assert metric.metric_type == StablecoinMetricType.SUPPLY
    assert metric.value > 0

@pytest.mark.integration
def test_get_dex_volume_live_api() -> None:
    """Calls the Birdeye public API directly and validates response mapping."""
    provider = Birdeye(api_key=API_KEY)
    metric = provider.get_metric(
        metric="defi_dex_volume",
        date=_TODAY_STR,
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, Defi)
    assert metric.metric_type == DefiMetricType.DEX_VOLUME
    assert metric.value > 0


@pytest.mark.integration
def test_get_dex_transactions_live_api() -> None:
    """Confirms the txns_24h response key exists and maps end-to-end."""
    provider = Birdeye(api_key=API_KEY)
    metric = provider.get_metric(
        metric="defi_dex_transactions",
        date=_TODAY_STR,
        chain="solana",
    )

    assert metric is not None
    assert isinstance(metric, Defi)
    assert metric.metric_type == DefiMetricType.DEX_TRANSACTIONS
    assert metric.value > 0

@pytest.mark.integration
def test_get_sol_price_4_days() -> None:
    """Calls the Birdeye public API directly and validates response mapping."""
    _3DAYS_AGO_STR = (_TODAY - datetime.timedelta(days=3)).isoformat()
    provider = Birdeye(api_key=API_KEY)
    rows = provider.fetch_rows(
        metric="overview_sol_price",
        start_date=_3DAYS_AGO_STR,
        end_date=_TODAY_STR,
        chain="solana",
    )

    start_timestamp = _date_to_timestamp(_3DAYS_AGO_STR)
    end_timestamp = _date_to_timestamp(_TODAY_STR)

    assert len(rows) == 4
    previous_date = 0
    for row in rows:
        assert "date" in row
        assert "value" in row
        assert isinstance(row["date"], str)
        assert isinstance(row["value"], float)
        assert row["value"] > 0
        timestamp = _date_to_timestamp(row["date"])
        assert start_timestamp <= timestamp
        assert timestamp <= end_timestamp
        assert timestamp > previous_date
        previous_date = timestamp

@pytest.mark.integration
def test_get_dex_volume_4_days() -> None:
    """Calls the Birdeye public API directly and validates response mapping."""
    _3DAYS_AGO_STR = (_TODAY - datetime.timedelta(days=3)).isoformat()
    provider = Birdeye(api_key=API_KEY)
    rows = provider.fetch_rows(
        metric="defi_dex_volume",
        start_date=_3DAYS_AGO_STR,
        end_date=_TODAY_STR,
        chain="solana",
    )

    start_timestamp = _date_to_timestamp(_3DAYS_AGO_STR)
    end_timestamp = _date_to_timestamp(_TODAY_STR)
    
    assert len(rows) == 4
    previous_date = 0
    for row in rows:
        assert "date" in row
        assert "value" in row
        assert isinstance(row["date"], str)
        assert isinstance(row["value"], float)
        assert row["value"] > 0
        timestamp = _date_to_timestamp(row["date"])
        assert start_timestamp <= timestamp
        assert timestamp <= end_timestamp
        assert timestamp > previous_date
        previous_date = timestamp

@pytest.mark.integration
def test_get_dex_volume_24_days() -> None:
    """Calls the Birdeye public API directly and validates response mapping."""
    _23DAYS_AGO_STR = (_TODAY - datetime.timedelta(days=23)).isoformat()
    provider = Birdeye(api_key=API_KEY)
    rows = provider.fetch_rows(
        metric="defi_dex_volume",
        start_date=_23DAYS_AGO_STR,
        end_date=_TODAY_STR,
        chain="solana",
    )

    start_timestamp = _date_to_timestamp(_23DAYS_AGO_STR)
    end_timestamp = _date_to_timestamp(_TODAY_STR)
    
    assert len(rows) == 24
    previous_date = 0
    for row in rows:
        assert "date" in row
        assert "value" in row
        assert isinstance(row["date"], str)
        assert isinstance(row["value"], float)
        assert row["value"] > 0
        timestamp = _date_to_timestamp(row["date"])
        assert start_timestamp <= timestamp
        assert timestamp <= end_timestamp
        assert timestamp > previous_date
        previous_date = timestamp