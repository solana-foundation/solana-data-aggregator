"""Unit tests for the Dune provider."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

from metrics.prediction_market import PredictionMarket, PredictionMarketMetricType
from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.dune import (
    PREDICTION_MARKET_PROGRAMS,
    PREDICTION_MARKET_RELAYER_PROTOCOLS,
    PREDICTION_MARKET_VOLUME_DECODERS,
    Dune,
)


def _mock_query_run(rows):
    """Mock the execute -> poll status -> fetch results Dune API flow."""
    post_resp = MagicMock()
    post_resp.raise_for_status = MagicMock()
    post_resp.json.return_value = {"execution_id": "exec-1"}

    status_resp = MagicMock()
    status_resp.raise_for_status = MagicMock()
    status_resp.json.return_value = {"state": "QUERY_STATE_COMPLETED"}

    results_resp = MagicMock()
    results_resp.raise_for_status = MagicMock()
    results_resp.json.return_value = {"result": {"rows": rows}}

    return post_resp, [status_resp, results_resp]


def test_get_stablecoin_supply_returns_stablecoin_metric() -> None:
    provider = Dune(api_key="key", poll_interval=0, timeout=5)

    post_resp = MagicMock()
    post_resp.raise_for_status = MagicMock()
    post_resp.json.return_value = {"execution_id": "exec-1"}

    status_resp = MagicMock()
    status_resp.raise_for_status = MagicMock()
    status_resp.json.return_value = {"state": "QUERY_STATE_COMPLETED"}

    results_resp = MagicMock()
    results_resp.raise_for_status = MagicMock()
    results_resp.json.return_value = {
        "result": {"rows": [{"day": "2026-01-01", "total_supply_usd": 5_000_000_000.0}]}
    }

    sentinel_metric = object()

    with (
        patch.object(provider._session, "post", return_value=post_resp),
        patch.object(provider._session, "get", side_effect=[status_resp, results_resp]),
        patch.object(
            Stablecoin, "from_metric_type", return_value=sentinel_metric
        ) as mock_factory,
    ):
        result = provider.get_metric("stablecoin_supply", "2026-01-01", "solana")

    assert result is sentinel_metric
    mock_factory.assert_called_once()
    assert mock_factory.call_args.kwargs["metric_type"] == StablecoinMetricType.SUPPLY
    assert mock_factory.call_args.kwargs["value"] == 5_000_000_000.0


def test_get_metric_prediction_market_transactions() -> None:
    provider = Dune(api_key="key", poll_interval=0, timeout=5)
    post_resp, get_resps = _mock_query_run(
        [{"block_date": "2026-08-05", "pm_transactions": 22254}]
    )

    with (
        patch.object(provider._session, "post", return_value=post_resp),
        patch.object(provider._session, "get", side_effect=get_resps),
    ):
        result = provider.get_metric(
            "prediction_market_transactions", "2026-08-05", "solana"
        )

    assert isinstance(result, PredictionMarket)
    assert result.metric_type == PredictionMarketMetricType.TRANSACTIONS
    assert result.value == 22254.0
    assert result.date == datetime.date(2026, 8, 5)


def test_get_metric_prediction_market_count() -> None:
    provider = Dune(api_key="key", poll_interval=0, timeout=5)
    post_resp, get_resps = _mock_query_run(
        [{"block_date": "2026-08-05", "pm_count": 5}]
    )

    with (
        patch.object(provider._session, "post", return_value=post_resp),
        patch.object(provider._session, "get", side_effect=get_resps),
    ):
        result = provider.get_metric("prediction_market_count", "2026-08-05", "solana")

    assert isinstance(result, PredictionMarket)
    assert result.metric_type == PredictionMarketMetricType.COUNT
    assert result.value == 5.0
    assert result.date == datetime.date(2026, 8, 5)


def test_prediction_market_count_sql_maps_every_protocol() -> None:
    """Every protocol is named once so programs collapse to their protocol."""
    provider = Dune(api_key="key", poll_interval=0, timeout=5)
    post_resp, get_resps = _mock_query_run([])

    with (
        patch.object(provider._session, "post", return_value=post_resp) as mock_post,
        patch.object(provider._session, "get", side_effect=get_resps),
    ):
        provider.fetch_rows("prediction_market_count", "2026-08-01", "2026-08-05")

    sql = mock_post.call_args.kwargs["json"]["sql"]
    for protocol, program_ids in PREDICTION_MARKET_PROGRAMS.items():
        assert f"THEN '{protocol}'" in sql
        for program_id in program_ids:
            assert program_id in sql
    assert "COUNT(DISTINCT protocol)" in sql


def test_get_metric_prediction_market_volume() -> None:
    provider = Dune(api_key="key", poll_interval=0, timeout=5)
    post_resp, get_resps = _mock_query_run(
        [{"block_date": "2026-08-05", "pm_volume_usd": 324456.0}]
    )

    with (
        patch.object(provider._session, "post", return_value=post_resp),
        patch.object(provider._session, "get", side_effect=get_resps),
    ):
        result = provider.get_metric("prediction_market_volume", "2026-08-05", "solana")

    assert isinstance(result, PredictionMarket)
    assert result.metric_type == PredictionMarketMetricType.VOLUME
    assert result.value == 324456.0
    assert result.date == datetime.date(2026, 8, 5)


def test_prediction_market_volume_sql_covers_every_decoder() -> None:
    """Each protocol with a decoder contributes one branch of the union."""
    provider = Dune(api_key="key", poll_interval=0, timeout=5)
    post_resp, get_resps = _mock_query_run([])

    with (
        patch.object(provider._session, "post", return_value=post_resp) as mock_post,
        patch.object(provider._session, "get", side_effect=get_resps),
    ):
        provider.fetch_rows("prediction_market_volume", "2026-08-01", "2026-08-05")

    sql = mock_post.call_args.kwargs["json"]["sql"]
    branches = sql.count("UNION ALL") + 1
    assert branches == len(PREDICTION_MARKET_VOLUME_DECODERS)

    for protocol in PREDICTION_MARKET_VOLUME_DECODERS:
        for program_id in PREDICTION_MARKET_PROGRAMS[protocol]:
            assert program_id in sql

    assert sql.count("DATE '2026-08-01'") == branches + 1  # world.xyz nests a subquery
    assert "SUM(volume_usd) AS pm_volume_usd" in sql


def test_get_metric_prediction_market_users() -> None:
    provider = Dune(api_key="key", poll_interval=0, timeout=5)
    post_resp, get_resps = _mock_query_run(
        [{"block_date": "2026-08-05", "pm_users": 1509}]
    )

    with (
        patch.object(provider._session, "post", return_value=post_resp),
        patch.object(provider._session, "get", side_effect=get_resps),
    ):
        result = provider.get_metric("prediction_market_users", "2026-08-05", "solana")

    assert isinstance(result, PredictionMarket)
    assert result.metric_type == PredictionMarketMetricType.USERS
    assert result.value == 1509.0
    assert result.date == datetime.date(2026, 8, 5)


def test_prediction_market_users_sql_splits_relayer_protocols() -> None:
    """Relayer protocols are counted by stake token owners, others by signers."""
    provider = Dune(api_key="key", poll_interval=0, timeout=5)
    post_resp, get_resps = _mock_query_run([])

    with (
        patch.object(provider._session, "post", return_value=post_resp) as mock_post,
        patch.object(provider._session, "get", side_effect=get_resps),
    ):
        provider.fetch_rows("prediction_market_users", "2026-08-01", "2026-08-05")

    sql = mock_post.call_args.kwargs["json"]["sql"]
    signer_side, relayer_side = sql.split("UNION")

    for protocol in PREDICTION_MARKET_RELAYER_PROTOCOLS:
        for program_id in PREDICTION_MARKET_PROGRAMS[protocol]:
            assert program_id not in signer_side
            assert program_id in relayer_side

    for protocol, program_ids in PREDICTION_MARKET_PROGRAMS.items():
        if protocol in PREDICTION_MARKET_RELAYER_PROTOCOLS:
            continue
        for program_id in program_ids:
            assert program_id in signer_side

    assert "tx_signer" in signer_side
    assert "from_owner" in relayer_side
    assert "tokens_solana.transfers" in relayer_side


def test_fetch_rows_prediction_market_sql_includes_range() -> None:
    provider = Dune(api_key="key", poll_interval=0, timeout=5)
    post_resp, get_resps = _mock_query_run([])

    with (
        patch.object(provider._session, "post", return_value=post_resp) as mock_post,
        patch.object(provider._session, "get", side_effect=get_resps),
    ):
        provider.fetch_rows(
            "prediction_market_transactions", "2026-08-01", "2026-08-05"
        )

    sql = mock_post.call_args.kwargs["json"]["sql"]
    assert "DATE '2026-08-01'" in sql
    assert "DATE '2026-08-05'" in sql
    assert "solana.instruction_calls" in sql
    assert "tx_success" in sql
    for program_ids in PREDICTION_MARKET_PROGRAMS.values():
        for program_id in program_ids:
            assert f"'{program_id}'" in sql
