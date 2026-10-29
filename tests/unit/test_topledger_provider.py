"""Unit tests for the Top Ledger provider."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest

from metrics.defi import Defi, DefiMetricType
from metrics.network import Network, NetworkMetricType
from metrics.overview import Overview, OverviewMetricType
from metrics.perps import Perps, PerpsMetricType
from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.topledger import TopLedger

_START = "2026-07-01"
_END = "2026-07-03"

# Simulate three days of block-level data returned by Redash query 15088.
_RAW_ROWS = [
    {
        "block_date": "2026-07-01",
        "successful_non_vote_transactions": 30_000_000,
        "failed_non_vote_transactions": 5_000_000,
        "slots": 432_000,
        "transactions": 80_000_000,
        "vote_transactions": 45_000_000,
        "txns_fees": 12_500.5,
        "avg_tps": 405.09,
    },
    {
        "block_date": "2026-07-02",
        "successful_non_vote_transactions": 29_500_000,
        "failed_non_vote_transactions": 4_800_000,
        "slots": 431_800,
        "transactions": 78_500_000,
        "vote_transactions": 44_200_000,
        "txns_fees": 11_900.25,
        "avg_tps": 396.99,
    },
    {
        "block_date": "2026-07-03",
        "successful_non_vote_transactions": 31_000_000,
        "failed_non_vote_transactions": 5_100_000,
        "slots": 432_100,
        "transactions": 81_200_000,
        "vote_transactions": 45_100_000,
        "txns_fees": 13_050.75,
        "avg_tps": 417.82,
    },
]

_COMPUTE_UNIT_ROWS = [
    {"block_date": "2026-07-01", "avg_cu_per_block": 28_500_000.0},
    {"block_date": "2026-07-02", "avg_cu_per_block": 29_100_000.0},
]


def _make_provider() -> TopLedger:
    return TopLedger(api_key="test-key")


def _immediate_result_resp(rows: list) -> MagicMock:
    """Mock a Redash response that returns a cached query_result immediately."""
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = {"query_result": {"data": {"rows": rows}}}
    return m


def _job_pending_resp(job_id: str) -> MagicMock:
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = {"job": {"id": job_id, "status": 1}}
    return m


def _job_success_resp(job_id: str, rows: list) -> MagicMock:
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = {
        "job": {
            "id": job_id,
            "status": 3,
            "query_result": {"data": {"rows": rows}},
        }
    }
    return m


def _job_failure_resp(job_id: str) -> MagicMock:
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = {"job": {"id": job_id, "status": 4, "error": "query failed"}}
    return m


# -- fetch_rows ----------------------------------------------------------------


def test_fetch_rows_success_non_vote() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_RAW_ROWS)
    ):
        rows = provider.fetch_rows("overview_non_vote_tx_count_success", _START, _END)

    assert rows[0]["value"] == 30_000_000.0


def test_fetch_rows_failed_non_vote() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_RAW_ROWS)
    ):
        rows = provider.fetch_rows("overview_non_vote_tx_count_failed", _START, _END)

    assert rows[0]["value"] == 5_000_000.0


def test_fetch_rows_slots() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_RAW_ROWS)
    ):
        rows = provider.fetch_rows("overview_slots", _START, _END)

    assert rows[0]["value"] == 432_000.0


def test_fetch_rows_tx_count_total() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_RAW_ROWS)
    ):
        rows = provider.fetch_rows("overview_tx_count_total", _START, _END)

    assert rows[0]["value"] == 80_000_000.0


def test_fetch_rows_tx_count_vote() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_RAW_ROWS)
    ):
        rows = provider.fetch_rows("overview_tx_count_vote", _START, _END)

    assert rows[0]["value"] == 45_000_000.0


def test_fetch_rows_fees() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_RAW_ROWS)
    ):
        rows = provider.fetch_rows("overview_fees", _START, _END)

    assert rows[0]["value"] == pytest.approx(12_500.5)


def test_fetch_rows_compute_units() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session,
        "post",
        return_value=_immediate_result_resp(_COMPUTE_UNIT_ROWS),
    ):
        rows = provider.fetch_rows("overview_compute_units", _START, "2026-07-02")

    assert len(rows) == 2
    assert rows[0]["value"] == pytest.approx(28_500_000.0)
    assert rows[1]["value"] == pytest.approx(29_100_000.0)


def test_fetch_rows_sol_price() -> None:
    price_rows = [
        {"block_date": "2026-07-01", "sol_price_usd": 185.42},
        {"block_date": "2026-07-02", "sol_price_usd": 187.10},
    ]
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(price_rows)
    ):
        rows = provider.fetch_rows("overview_sol_price", _START, "2026-07-02")

    assert len(rows) == 2
    assert rows[0] == {"date": "2026-07-01", "value": pytest.approx(185.42)}
    assert rows[1] == {"date": "2026-07-02", "value": pytest.approx(187.10)}


def test_fetch_rows_fee_payers() -> None:
    fee_payer_rows = [
        {"block_date": "2026-07-01", "fee_payer": 1_250_000},
        {"block_date": "2026-07-02", "fee_payer": 1_280_000},
    ]
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(fee_payer_rows)
    ):
        rows = provider.fetch_rows("overview_fee_payers", _START, "2026-07-02")

    assert len(rows) == 2
    assert rows[0] == {"date": "2026-07-01", "value": 1_250_000.0}
    assert rows[1] == {"date": "2026-07-02", "value": 1_280_000.0}


def test_get_metric_fee_payers_returns_overview_model() -> None:
    fee_payer_rows = [{"block_date": _START, "fee_payer": 1_250_000}]
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(fee_payer_rows)
    ):
        result = provider.get_metric("overview_fee_payers", _START, "solana")

    assert isinstance(result, Overview)
    assert result.metric_type == OverviewMetricType.FEE_PAYERS
    assert result.value == 1_250_000.0


# -- caching -------------------------------------------------------------------


def test_same_query_runs_once_for_multiple_metrics() -> None:
    """Metrics sharing query 15088 should trigger only one POST for a given date range."""
    provider = _make_provider()
    mock_post = MagicMock(return_value=_immediate_result_resp(_RAW_ROWS))

    with patch.object(provider._session, "post", mock_post):
        provider.fetch_rows("overview_non_vote_tx_count_success", _START, _END)
        provider.fetch_rows("overview_non_vote_tx_count_failed", _START, _END)
        provider.fetch_rows("overview_slots", _START, _END)
        provider.fetch_rows("overview_tx_count_total", _START, _END)
        provider.fetch_rows("overview_tx_count_vote", _START, _END)
        provider.fetch_rows("overview_fees", _START, _END)

    assert mock_post.call_count == 1


def test_different_query_ids_run_separate_requests() -> None:
    """overview_sol_price uses query 15089, so it posts separately from query 15088."""
    provider = _make_provider()
    price_rows = [{"block_date": _START, "sol_price_usd": 185.0}]
    mock_post = MagicMock(
        side_effect=[
            _immediate_result_resp(_RAW_ROWS),
            _immediate_result_resp(price_rows),
        ]
    )

    with patch.object(provider._session, "post", mock_post):
        provider.fetch_rows("overview_slots", _START, _END)
        provider.fetch_rows("overview_sol_price", _START, _END)

    assert mock_post.call_count == 2


def test_different_date_ranges_run_separate_queries() -> None:
    provider = _make_provider()
    mock_post = MagicMock(return_value=_immediate_result_resp(_RAW_ROWS[:1]))

    with patch.object(provider._session, "post", mock_post):
        provider.fetch_rows("overview_slots", "2026-07-01", "2026-07-01")
        provider.fetch_rows("overview_slots", "2026-07-02", "2026-07-02")

    assert mock_post.call_count == 2


# -- async job polling ---------------------------------------------------------


def test_fetch_rows_polls_until_job_succeeds() -> None:
    provider = _make_provider()
    provider._POLL_INTERVAL = 0  # skip sleep in tests

    post_resp = MagicMock()
    post_resp.raise_for_status = MagicMock()
    post_resp.json.return_value = {"job": {"id": "job-abc", "status": 1}}

    get_pending = _job_pending_resp("job-abc")
    get_success = _job_success_resp("job-abc", _RAW_ROWS[:1])

    with (
        patch.object(provider._session, "post", return_value=post_resp),
        patch.object(provider._session, "get", side_effect=[get_pending, get_success]),
    ):
        rows = provider.fetch_rows("overview_slots", _START, _START)

    assert rows == [{"date": "2026-07-01", "value": 432_000.0}]


def test_fetch_rows_raises_on_job_failure() -> None:
    provider = _make_provider()
    provider._POLL_INTERVAL = 0

    post_resp = MagicMock()
    post_resp.raise_for_status = MagicMock()
    post_resp.json.return_value = {"job": {"id": "job-fail", "status": 1}}

    with (
        patch.object(provider._session, "post", return_value=post_resp),
        patch.object(
            provider._session, "get", return_value=_job_failure_resp("job-fail")
        ),
        pytest.raises(RuntimeError, match="status 4"),
    ):
        provider.fetch_rows("overview_slots", _START, _END)


# -- get_metric ----------------------------------------------------------------


def test_get_metric_returns_overview_model() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_RAW_ROWS)
    ):
        result = provider.get_metric(
            "overview_non_vote_tx_count_success", _START, "solana"
        )

    assert isinstance(result, Overview)
    assert result.metric_type == OverviewMetricType.TX_COUNT_NON_VOTE_SUCCESS
    assert result.value == 30_000_000.0
    assert result.date == datetime.date.fromisoformat(_START)


def test_get_metric_overview_tx_count_total() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_RAW_ROWS)
    ):
        result = provider.get_metric("overview_tx_count_total", _START, "solana")

    assert isinstance(result, Overview)
    assert result.metric_type == OverviewMetricType.TX_COUNT_TOTAL
    assert result.value == 80_000_000.0


def test_get_metric_overview_tx_count_vote() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_RAW_ROWS)
    ):
        result = provider.get_metric("overview_tx_count_vote", _START, "solana")

    assert isinstance(result, Overview)
    assert result.metric_type == OverviewMetricType.TX_COUNT_VOTE
    assert result.value == 45_000_000.0


def test_get_metric_overview_fees() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_RAW_ROWS)
    ):
        result = provider.get_metric("overview_fees", _START, "solana")

    assert isinstance(result, Overview)
    assert result.metric_type == OverviewMetricType.FEES
    assert result.value == pytest.approx(12_500.5)


def test_get_metric_overview_compute_units() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session,
        "post",
        return_value=_immediate_result_resp(_COMPUTE_UNIT_ROWS),
    ):
        result = provider.get_metric("overview_compute_units", _START, "solana")

    assert isinstance(result, Overview)
    assert result.metric_type == OverviewMetricType.COMPUTE_UNITS
    assert result.value == pytest.approx(28_500_000.0)


def test_get_metric_returns_none_when_no_rows() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp([])
    ):
        result = provider.get_metric("overview_slots", _START, "solana")

    assert result is None


def test_get_metric_unknown_metric_raises() -> None:
    provider = _make_provider()
    with (
        patch.object(
            provider._session, "post", return_value=_immediate_result_resp([])
        ),
        pytest.raises(ValueError, match="Unknown metric"),
    ):
        provider.fetch_rows("nonexistent_metric", _START, _END)


# -- date filtering ------------------------------------------------------------


def test_fetch_rows_filters_out_of_range_dates() -> None:
    """Rows outside the requested window should be dropped even if the API returns them."""
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_RAW_ROWS)
    ):
        rows = provider.fetch_rows("overview_slots", "2026-07-02", "2026-07-02")

    assert len(rows) == 1
    assert rows[0]["date"] == "2026-07-02"


def test_fetch_rows_skips_rows_with_null_value() -> None:
    rows_with_null = [{"block_date": "2026-07-01", "slots": None}]
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(rows_with_null)
    ):
        result = provider.fetch_rows("overview_slots", _START, _START)

    assert result == []


# -- stablecoin metrics --------------------------------------------------------

_STABLECOIN_ROWS = [
    {
        "block_date": "2026-07-01",
        "marketcap": 12_500_000_000.0,
        "total_supply": 13_000_000_000.0,
        "stablecoin_count": 8,
    },
    {
        "block_date": "2026-07-02",
        "marketcap": 12_600_000_000.0,
        "total_supply": 13_100_000_000.0,
        "stablecoin_count": 8,
    },
]


def test_fetch_rows_stablecoin_circulating_supply() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_STABLECOIN_ROWS)
    ):
        rows = provider.fetch_rows("stablecoin_circulating_supply", _START, "2026-07-02")

    assert len(rows) == 2
    assert rows[0] == {"date": "2026-07-01", "value": pytest.approx(12_500_000_000.0)}
    assert rows[1] == {"date": "2026-07-02", "value": pytest.approx(12_600_000_000.0)}


def test_fetch_rows_stablecoin_total_supply() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_STABLECOIN_ROWS)
    ):
        rows = provider.fetch_rows("stablecoin_total_supply", _START, "2026-07-02")

    assert len(rows) == 2
    assert rows[0] == {"date": "2026-07-01", "value": pytest.approx(13_000_000_000.0)}
    assert rows[1] == {"date": "2026-07-02", "value": pytest.approx(13_100_000_000.0)}


def test_fetch_rows_stablecoin_count() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_STABLECOIN_ROWS)
    ):
        rows = provider.fetch_rows("stablecoin_count", _START, "2026-07-02")

    assert rows[0] == {"date": "2026-07-01", "value": 8.0}


def test_stablecoin_metrics_share_one_query_call() -> None:
    """Circulating supply, total supply, and count all use query 15090 — one POST."""
    provider = _make_provider()
    mock_post = MagicMock(return_value=_immediate_result_resp(_STABLECOIN_ROWS))

    with patch.object(provider._session, "post", mock_post):
        provider.fetch_rows("stablecoin_circulating_supply", _START, "2026-07-02")
        provider.fetch_rows("stablecoin_total_supply", _START, "2026-07-02")
        provider.fetch_rows("stablecoin_count", _START, "2026-07-02")

    assert mock_post.call_count == 1


def test_get_metric_returns_stablecoin_model() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_STABLECOIN_ROWS)
    ):
        result = provider.get_metric("stablecoin_circulating_supply", _START, "solana")

    assert isinstance(result, Stablecoin)
    assert result.metric_type == StablecoinMetricType.CIRCULATING_SUPPLY
    assert result.value == pytest.approx(12_500_000_000.0)
    assert result.date == datetime.date.fromisoformat(_START)


def test_get_metric_stablecoin_total_supply_returns_stablecoin_model() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_STABLECOIN_ROWS)
    ):
        result = provider.get_metric("stablecoin_total_supply", _START, "solana")

    assert isinstance(result, Stablecoin)
    assert result.metric_type == StablecoinMetricType.TOTAL_SUPPLY
    assert result.value == pytest.approx(13_000_000_000.0)
    assert result.date == datetime.date.fromisoformat(_START)


def test_get_metric_stablecoin_count_returns_stablecoin_model() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_STABLECOIN_ROWS)
    ):
        result = provider.get_metric("stablecoin_count", _START, "solana")

    assert isinstance(result, Stablecoin)
    assert result.metric_type == StablecoinMetricType.COUNT
    assert result.value == 8.0


_TRANSFER_ROWS = [
    {
        "block_date": "2026-07-01",
        "transfer_count": 4_200_000,
        "transfer_volume": 3_800_000_000.0,
    },
    {
        "block_date": "2026-07-02",
        "transfer_count": 4_350_000,
        "transfer_volume": 3_950_000_000.0,
    },
]


def test_fetch_rows_stablecoin_transfer_volume() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_TRANSFER_ROWS)
    ):
        rows = provider.fetch_rows("stablecoin_transfer_volume", _START, "2026-07-02")

    assert len(rows) == 2
    assert rows[0] == {"date": "2026-07-01", "value": pytest.approx(3_800_000_000.0)}
    assert rows[1] == {"date": "2026-07-02", "value": pytest.approx(3_950_000_000.0)}


def test_fetch_rows_stablecoin_transfer_count() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_TRANSFER_ROWS)
    ):
        rows = provider.fetch_rows("stablecoin_transfer_count", _START, "2026-07-02")

    assert rows[0] == {"date": "2026-07-01", "value": 4_200_000.0}
    assert rows[1] == {"date": "2026-07-02", "value": 4_350_000.0}


def test_transfer_metrics_share_one_query_call() -> None:
    """stablecoin_transfer_volume and stablecoin_transfer_count share query 15091."""
    provider = _make_provider()
    mock_post = MagicMock(return_value=_immediate_result_resp(_TRANSFER_ROWS))

    with patch.object(provider._session, "post", mock_post):
        provider.fetch_rows("stablecoin_transfer_volume", _START, "2026-07-02")
        provider.fetch_rows("stablecoin_transfer_count", _START, "2026-07-02")

    assert mock_post.call_count == 1


def test_get_metric_stablecoin_transfer_volume() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_TRANSFER_ROWS)
    ):
        result = provider.get_metric("stablecoin_transfer_volume", _START, "solana")

    assert isinstance(result, Stablecoin)
    assert result.metric_type == StablecoinMetricType.TRANSFER_VOLUME
    assert result.value == pytest.approx(3_800_000_000.0)


def test_get_metric_stablecoin_transfer_count() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_TRANSFER_ROWS)
    ):
        result = provider.get_metric("stablecoin_transfer_count", _START, "solana")

    assert isinstance(result, Stablecoin)
    assert result.metric_type == StablecoinMetricType.TRANSFER_COUNT
    assert result.value == 4_200_000.0


_ACTIVE_ADDRESS_ROWS = [
    {"block_date": "2026-07-01", "active_address": 980_000},
    {"block_date": "2026-07-02", "active_address": 1_020_000},
]


def test_fetch_rows_stablecoin_active_addresses() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session,
        "post",
        return_value=_immediate_result_resp(_ACTIVE_ADDRESS_ROWS),
    ):
        rows = provider.fetch_rows("stablecoin_active_addresses", _START, "2026-07-02")

    assert len(rows) == 2
    assert rows[0] == {"date": "2026-07-01", "value": 980_000.0}
    assert rows[1] == {"date": "2026-07-02", "value": 1_020_000.0}


def test_get_metric_stablecoin_active_addresses() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session,
        "post",
        return_value=_immediate_result_resp(_ACTIVE_ADDRESS_ROWS),
    ):
        result = provider.get_metric("stablecoin_active_addresses", _START, "solana")

    assert isinstance(result, Stablecoin)
    assert result.metric_type == StablecoinMetricType.ACTIVE_ADDRESSES
    assert result.value == 980_000.0


# -- defi metrics --------------------------------------------------------------

_DEX_VOLUME_ROWS = [
    {"block_date": "2026-07-01", "dex_volume": 4_200_000_000.0},
    {"block_date": "2026-07-02", "dex_volume": 3_900_000_000.0},
]

_DEX_ACTIVITY_ROWS = [
    {
        "block_date": "2026-07-01",
        "dex_transactions": 18_000_000,
        "traders": 950_000,
        "dex_counts": 12,
    },
    {
        "block_date": "2026-07-02",
        "dex_transactions": 17_500_000,
        "traders": 920_000,
        "dex_counts": 11,
    },
]


def test_fetch_rows_defi_dex_volume() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_DEX_VOLUME_ROWS)
    ):
        rows = provider.fetch_rows("defi_dex_volume", _START, "2026-07-02")

    assert len(rows) == 2
    assert rows[0] == {"date": "2026-07-01", "value": pytest.approx(4_200_000_000.0)}
    assert rows[1] == {"date": "2026-07-02", "value": pytest.approx(3_900_000_000.0)}


def test_fetch_rows_defi_dex_transactions() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session,
        "post",
        return_value=_immediate_result_resp(_DEX_ACTIVITY_ROWS),
    ):
        rows = provider.fetch_rows("defi_dex_transactions", _START, "2026-07-02")

    assert rows[0]["value"] == 18_000_000.0


def test_fetch_rows_defi_dex_traders() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session,
        "post",
        return_value=_immediate_result_resp(_DEX_ACTIVITY_ROWS),
    ):
        rows = provider.fetch_rows("defi_dex_traders", _START, "2026-07-02")

    assert rows[0]["value"] == 950_000.0


def test_fetch_rows_defi_dex_count() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session,
        "post",
        return_value=_immediate_result_resp(_DEX_ACTIVITY_ROWS),
    ):
        rows = provider.fetch_rows("defi_dex_count", _START, "2026-07-02")

    assert rows[0]["value"] == 12.0


def test_defi_activity_metrics_share_one_query_call() -> None:
    """dex_transactions, dex_traders, and dex_count share query 15103 — one POST."""
    provider = _make_provider()
    mock_post = MagicMock(return_value=_immediate_result_resp(_DEX_ACTIVITY_ROWS))

    with patch.object(provider._session, "post", mock_post):
        provider.fetch_rows("defi_dex_transactions", _START, "2026-07-02")
        provider.fetch_rows("defi_dex_traders", _START, "2026-07-02")
        provider.fetch_rows("defi_dex_count", _START, "2026-07-02")

    assert mock_post.call_count == 1


def test_defi_volume_uses_separate_query_from_activity_metrics() -> None:
    """dex_volume uses query 15093; activity metrics use query 15103."""
    provider = _make_provider()
    mock_post = MagicMock(
        side_effect=[
            _immediate_result_resp(_DEX_VOLUME_ROWS),
            _immediate_result_resp(_DEX_ACTIVITY_ROWS),
        ]
    )

    with patch.object(provider._session, "post", mock_post):
        provider.fetch_rows("defi_dex_volume", _START, "2026-07-02")
        provider.fetch_rows("defi_dex_transactions", _START, "2026-07-02")

    assert mock_post.call_count == 2


def test_get_metric_defi_dex_volume_returns_defi_model() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_DEX_VOLUME_ROWS)
    ):
        result = provider.get_metric("defi_dex_volume", _START, "solana")

    assert isinstance(result, Defi)
    assert result.metric_type == DefiMetricType.DEX_VOLUME
    assert result.value == pytest.approx(4_200_000_000.0)
    assert result.date == datetime.date.fromisoformat(_START)


def test_get_metric_defi_dex_traders_returns_defi_model() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session,
        "post",
        return_value=_immediate_result_resp(_DEX_ACTIVITY_ROWS),
    ):
        result = provider.get_metric("defi_dex_traders", _START, "solana")

    assert isinstance(result, Defi)
    assert result.metric_type == DefiMetricType.DEX_TRADERS
    assert result.value == 950_000.0


# -- perps metrics -------------------------------------------------------------

_PERPS_ACTIVITY_ROWS = [
    {
        "block_date": "2026-07-01",
        "trading_volume_usd": 850_000_000.0,
        "transactions": 125_000,
        "perp_venue_count": 6,
    },
    {
        "block_date": "2026-07-02",
        "trading_volume_usd": 920_000_000.0,
        "transactions": 131_000,
        "perp_venue_count": 7,
    },
]

_PERPS_TRADERS_ROWS = [
    {"block_date": "2026-07-01", "unique_traders": 42_000},
    {"block_date": "2026-07-02", "unique_traders": 45_500},
]

_PERPS_OI_ROWS = [
    {"block_date": "2026-07-01", "total_open_interest_usd": 1_200_000_000.0},
    {"block_date": "2026-07-02", "total_open_interest_usd": 1_250_000_000.0},
]


def test_fetch_rows_perps_trading_volume() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session,
        "post",
        return_value=_immediate_result_resp(_PERPS_ACTIVITY_ROWS),
    ):
        rows = provider.fetch_rows("perps_trading_volume", _START, "2026-07-02")

    assert len(rows) == 2
    assert rows[0] == {"date": "2026-07-01", "value": pytest.approx(850_000_000.0)}
    assert rows[1] == {"date": "2026-07-02", "value": pytest.approx(920_000_000.0)}


def test_fetch_rows_perps_transactions() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session,
        "post",
        return_value=_immediate_result_resp(_PERPS_ACTIVITY_ROWS),
    ):
        rows = provider.fetch_rows("perps_transactions", _START, "2026-07-02")

    assert rows[0]["value"] == 125_000.0


def test_fetch_rows_perps_venue_count() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session,
        "post",
        return_value=_immediate_result_resp(_PERPS_ACTIVITY_ROWS),
    ):
        rows = provider.fetch_rows("perps_venue_count", _START, "2026-07-02")

    assert rows[0]["value"] == 6.0


def test_fetch_rows_perps_traders() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session,
        "post",
        return_value=_immediate_result_resp(_PERPS_TRADERS_ROWS),
    ):
        rows = provider.fetch_rows("perps_traders", _START, "2026-07-02")

    assert rows[0]["value"] == 42_000.0
    assert rows[1]["value"] == 45_500.0


def test_fetch_rows_perps_open_interest() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_PERPS_OI_ROWS)
    ):
        rows = provider.fetch_rows("perps_open_interest", _START, "2026-07-02")

    assert rows[0] == {"date": "2026-07-01", "value": pytest.approx(1_200_000_000.0)}
    assert rows[1] == {"date": "2026-07-02", "value": pytest.approx(1_250_000_000.0)}


def test_perps_activity_metrics_share_one_query_call() -> None:
    """volume, transactions, and venue_count share query 15344 — one POST."""
    provider = _make_provider()
    mock_post = MagicMock(return_value=_immediate_result_resp(_PERPS_ACTIVITY_ROWS))

    with patch.object(provider._session, "post", mock_post):
        provider.fetch_rows("perps_trading_volume", _START, "2026-07-02")
        provider.fetch_rows("perps_transactions", _START, "2026-07-02")
        provider.fetch_rows("perps_venue_count", _START, "2026-07-02")

    assert mock_post.call_count == 1


def test_get_metric_perps_trading_volume_returns_perps_model() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session,
        "post",
        return_value=_immediate_result_resp(_PERPS_ACTIVITY_ROWS),
    ):
        result = provider.get_metric("perps_trading_volume", _START, "solana")

    assert isinstance(result, Perps)
    assert result.metric_type == PerpsMetricType.TRADING_VOLUME
    assert result.value == pytest.approx(850_000_000.0)
    assert result.date == datetime.date.fromisoformat(_START)


def test_get_metric_perps_traders_returns_perps_model() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session,
        "post",
        return_value=_immediate_result_resp(_PERPS_TRADERS_ROWS),
    ):
        result = provider.get_metric("perps_traders", _START, "solana")

    assert isinstance(result, Perps)
    assert result.metric_type == PerpsMetricType.TRADERS
    assert result.value == 42_000.0


def test_get_metric_perps_open_interest_returns_perps_model() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_PERPS_OI_ROWS)
    ):
        result = provider.get_metric("perps_open_interest", _START, "solana")

    assert isinstance(result, Perps)
    assert result.metric_type == PerpsMetricType.OPEN_INTEREST
    assert result.value == pytest.approx(1_200_000_000.0)


# -- network metrics -----------------------------------------------------------

_STAKE_ROWS = [
    {"block_date": "2026-07-01", "sol_staked": 380_000_000.0},
    {"block_date": "2026-07-02", "sol_staked": 381_500_000.0},
]

_VALIDATOR_ROWS = [
    {
        "block_date": "2026-07-01",
        "validators_count": 1_350,
        "asn_share_top3": 28.5,
    },
    {
        "block_date": "2026-07-02",
        "validators_count": 1_355,
        "asn_share_top3": 28.1,
    },
]


def test_fetch_rows_network_total_stake() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_STAKE_ROWS)
    ):
        rows = provider.fetch_rows("network_total_stake", _START, "2026-07-02")

    assert len(rows) == 2
    assert rows[0] == {"date": "2026-07-01", "value": pytest.approx(380_000_000.0)}
    assert rows[1] == {"date": "2026-07-02", "value": pytest.approx(381_500_000.0)}


def test_fetch_rows_network_validator_count() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_VALIDATOR_ROWS)
    ):
        rows = provider.fetch_rows("network_validator_count", _START, "2026-07-02")

    assert rows[0]["value"] == 1_350.0
    assert rows[1]["value"] == 1_355.0


def test_fetch_rows_network_top_3_asn_share() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_VALIDATOR_ROWS)
    ):
        rows = provider.fetch_rows("network_top_3_asn_share", _START, "2026-07-02")

    assert rows[0]["value"] == pytest.approx(28.5)
    assert rows[1]["value"] == pytest.approx(28.1)


def test_fetch_rows_network_avg_tps() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_RAW_ROWS)
    ):
        rows = provider.fetch_rows("network_avg_tps", _START, _END)

    assert rows[0]["value"] == pytest.approx(405.09)


def test_network_validator_metrics_share_one_query_call() -> None:
    """validator_count and top_3_asn_share share query 15380 — one POST."""
    provider = _make_provider()
    mock_post = MagicMock(return_value=_immediate_result_resp(_VALIDATOR_ROWS))

    with patch.object(provider._session, "post", mock_post):
        provider.fetch_rows("network_validator_count", _START, "2026-07-02")
        provider.fetch_rows("network_top_3_asn_share", _START, "2026-07-02")

    assert mock_post.call_count == 1


def test_get_metric_network_total_stake_returns_network_model() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_STAKE_ROWS)
    ):
        result = provider.get_metric("network_total_stake", _START, "solana")

    assert isinstance(result, Network)
    assert result.metric_type == NetworkMetricType.TOTAL_STAKE
    assert result.value == pytest.approx(380_000_000.0)


def test_get_metric_network_validator_count_returns_network_model() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_VALIDATOR_ROWS)
    ):
        result = provider.get_metric("network_validator_count", _START, "solana")

    assert isinstance(result, Network)
    assert result.metric_type == NetworkMetricType.VALIDATOR_COUNT
    assert result.value == 1_350.0


def test_get_metric_network_top_3_asn_share_returns_network_model() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_VALIDATOR_ROWS)
    ):
        result = provider.get_metric("network_top_3_asn_share", _START, "solana")

    assert isinstance(result, Network)
    assert result.metric_type == NetworkMetricType.TOP_3_ASN_SHARE
    assert result.value == pytest.approx(28.5)


def test_get_metric_network_avg_tps_returns_network_model() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_RAW_ROWS)
    ):
        result = provider.get_metric("network_avg_tps", _START, "solana")

    assert isinstance(result, Network)
    assert result.metric_type == NetworkMetricType.AVG_TPS
    assert result.value == pytest.approx(405.09)


# -- constructor ---------------------------------------------------------------


def test_constructor_raises_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("TOPLEDGER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="TOPLEDGER_API_KEY"):
        TopLedger()


def test_constructor_reads_api_key_from_env(monkeypatch) -> None:
    monkeypatch.setenv("TOPLEDGER_API_KEY", "env-key")
    provider = TopLedger()
    assert provider.api_key == "env-key"
