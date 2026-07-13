"""Unit tests for the Top Ledger provider."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest

from metrics.defi import Defi, DefiMetricType
from metrics.overview import Overview, OverviewMetricType
from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.topledger import TopLedger

_START = "2026-07-01"
_END = "2026-07-03"

# Simulate three days of block-level data returned by Redash query 15088.
_RAW_ROWS = [
    {
        "block_date": "2026-07-01",
        "transactions": 120_000_000,
        "txns_fees": 75_000.5,
        "successful_non_vote_transactions": 30_000_000,
        "failed_non_vote_transactions": 5_000_000,
        "vote_transactions": 85_000_000,
        "slots": 432_000,
    },
    {
        "block_date": "2026-07-02",
        "transactions": 118_000_000,
        "txns_fees": 74_200.0,
        "successful_non_vote_transactions": 29_500_000,
        "failed_non_vote_transactions": 4_800_000,
        "vote_transactions": 83_700_000,
        "slots": 431_800,
    },
    {
        "block_date": "2026-07-03",
        "transactions": 121_000_000,
        "txns_fees": 76_100.0,
        "successful_non_vote_transactions": 31_000_000,
        "failed_non_vote_transactions": 5_100_000,
        "vote_transactions": 84_900_000,
        "slots": 432_100,
    },
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


def test_fetch_rows_tx_count_total_immediate_result() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_RAW_ROWS)
    ):
        rows = provider.fetch_rows("overview_tx_count_total", _START, _END)

    assert len(rows) == 3
    assert rows[0] == {"date": "2026-07-01", "value": 120_000_000.0}
    assert rows[1] == {"date": "2026-07-02", "value": 118_000_000.0}
    assert rows[2] == {"date": "2026-07-03", "value": 121_000_000.0}


def test_fetch_rows_vote_transactions() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_RAW_ROWS)
    ):
        rows = provider.fetch_rows("overview_tx_count_vote", _START, _END)

    assert rows[0]["value"] == 85_000_000.0


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


def test_fetch_rows_fees() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_RAW_ROWS)
    ):
        rows = provider.fetch_rows("overview_fees", _START, _END)

    assert rows[0]["value"] == pytest.approx(75_000.5)


def test_fetch_rows_slots() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_RAW_ROWS)
    ):
        rows = provider.fetch_rows("overview_slots", _START, _END)

    assert rows[0]["value"] == 432_000.0


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


# -- caching -------------------------------------------------------------------


def test_same_query_runs_once_for_multiple_metrics() -> None:
    """Metrics sharing query 15088 should trigger only one POST for a given date range."""
    provider = _make_provider()
    mock_post = MagicMock(return_value=_immediate_result_resp(_RAW_ROWS))

    with patch.object(provider._session, "post", mock_post):
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
        provider.fetch_rows("overview_tx_count_total", _START, _END)
        provider.fetch_rows("overview_sol_price", _START, _END)

    assert mock_post.call_count == 2


def test_different_date_ranges_run_separate_queries() -> None:
    provider = _make_provider()
    mock_post = MagicMock(return_value=_immediate_result_resp(_RAW_ROWS[:1]))

    with patch.object(provider._session, "post", mock_post):
        provider.fetch_rows("overview_tx_count_total", "2026-07-01", "2026-07-01")
        provider.fetch_rows("overview_tx_count_total", "2026-07-02", "2026-07-02")

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
        rows = provider.fetch_rows("overview_tx_count_total", _START, _START)

    assert rows == [{"date": "2026-07-01", "value": 120_000_000.0}]


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
        provider.fetch_rows("overview_tx_count_total", _START, _END)


# -- get_metric ----------------------------------------------------------------


def test_get_metric_returns_overview_model() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_RAW_ROWS)
    ):
        result = provider.get_metric("overview_tx_count_total", _START, "solana")

    assert isinstance(result, Overview)
    assert result.metric_type == OverviewMetricType.TX_COUNT_TOTAL
    assert result.value == 120_000_000.0
    assert result.date == datetime.date.fromisoformat(_START)


def test_get_metric_returns_none_when_no_rows() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp([])
    ):
        result = provider.get_metric("overview_fees", _START, "solana")

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
        rows = provider.fetch_rows(
            "overview_tx_count_total", "2026-07-02", "2026-07-02"
        )

    assert len(rows) == 1
    assert rows[0]["date"] == "2026-07-02"


def test_fetch_rows_skips_rows_with_null_value() -> None:
    rows_with_null = [{"block_date": "2026-07-01", "transactions": None}]
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(rows_with_null)
    ):
        result = provider.fetch_rows("overview_tx_count_total", _START, _START)

    assert result == []


# -- stablecoin metrics --------------------------------------------------------

_STABLECOIN_ROWS = [
    {"block_date": "2026-07-01", "marketcap": 12_500_000_000.0, "stablecoin_count": 8},
    {"block_date": "2026-07-02", "marketcap": 12_600_000_000.0, "stablecoin_count": 8},
]


def test_fetch_rows_stablecoin_supply() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_STABLECOIN_ROWS)
    ):
        rows = provider.fetch_rows("stablecoin_supply", _START, "2026-07-02")

    assert len(rows) == 2
    assert rows[0] == {"date": "2026-07-01", "value": pytest.approx(12_500_000_000.0)}
    assert rows[1] == {"date": "2026-07-02", "value": pytest.approx(12_600_000_000.0)}


def test_fetch_rows_stablecoin_count() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_STABLECOIN_ROWS)
    ):
        rows = provider.fetch_rows("stablecoin_count", _START, "2026-07-02")

    assert rows[0] == {"date": "2026-07-01", "value": 8.0}


def test_stablecoin_metrics_share_one_query_call() -> None:
    """stablecoin_supply and stablecoin_count both use query 15090 — one POST."""
    provider = _make_provider()
    mock_post = MagicMock(return_value=_immediate_result_resp(_STABLECOIN_ROWS))

    with patch.object(provider._session, "post", mock_post):
        provider.fetch_rows("stablecoin_supply", _START, "2026-07-02")
        provider.fetch_rows("stablecoin_count", _START, "2026-07-02")

    assert mock_post.call_count == 1


def test_get_metric_returns_stablecoin_model() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_STABLECOIN_ROWS)
    ):
        result = provider.get_metric("stablecoin_supply", _START, "solana")

    assert isinstance(result, Stablecoin)
    assert result.metric_type == StablecoinMetricType.SUPPLY
    assert result.value == pytest.approx(12_500_000_000.0)
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

_DEX_ROWS = [
    {
        "block_date": "2026-07-01",
        "dex_volume": 4_200_000_000.0,
        "dex_transactions": 18_000_000,
        "traders": 950_000,
        "dex_counts": 12,
    },
    {
        "block_date": "2026-07-02",
        "dex_volume": 3_900_000_000.0,
        "dex_transactions": 17_500_000,
        "traders": 920_000,
        "dex_counts": 11,
    },
]


def test_fetch_rows_defi_dex_volume() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_DEX_ROWS)
    ):
        rows = provider.fetch_rows("defi_dex_volume", _START, "2026-07-02")

    assert len(rows) == 2
    assert rows[0] == {"date": "2026-07-01", "value": pytest.approx(4_200_000_000.0)}
    assert rows[1] == {"date": "2026-07-02", "value": pytest.approx(3_900_000_000.0)}


def test_fetch_rows_defi_dex_transactions() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_DEX_ROWS)
    ):
        rows = provider.fetch_rows("defi_dex_transactions", _START, "2026-07-02")

    assert rows[0]["value"] == 18_000_000.0


def test_fetch_rows_defi_dex_traders() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_DEX_ROWS)
    ):
        rows = provider.fetch_rows("defi_dex_traders", _START, "2026-07-02")

    assert rows[0]["value"] == 950_000.0


def test_fetch_rows_defi_dex_count() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_DEX_ROWS)
    ):
        rows = provider.fetch_rows("defi_dex_count", _START, "2026-07-02")

    assert rows[0]["value"] == 12.0


def test_defi_metrics_share_one_query_call() -> None:
    """All four DeFi metrics share query 15093 — only one POST per date range."""
    provider = _make_provider()
    mock_post = MagicMock(return_value=_immediate_result_resp(_DEX_ROWS))

    with patch.object(provider._session, "post", mock_post):
        provider.fetch_rows("defi_dex_volume", _START, "2026-07-02")
        provider.fetch_rows("defi_dex_transactions", _START, "2026-07-02")
        provider.fetch_rows("defi_dex_traders", _START, "2026-07-02")
        provider.fetch_rows("defi_dex_count", _START, "2026-07-02")

    assert mock_post.call_count == 1


def test_get_metric_defi_dex_volume_returns_defi_model() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_DEX_ROWS)
    ):
        result = provider.get_metric("defi_dex_volume", _START, "solana")

    assert isinstance(result, Defi)
    assert result.metric_type == DefiMetricType.DEX_VOLUME
    assert result.value == pytest.approx(4_200_000_000.0)
    assert result.date == datetime.date.fromisoformat(_START)


def test_get_metric_defi_dex_traders_returns_defi_model() -> None:
    provider = _make_provider()
    with patch.object(
        provider._session, "post", return_value=_immediate_result_resp(_DEX_ROWS)
    ):
        result = provider.get_metric("defi_dex_traders", _START, "solana")

    assert isinstance(result, Defi)
    assert result.metric_type == DefiMetricType.DEX_TRADERS
    assert result.value == 950_000.0


# -- constructor ---------------------------------------------------------------


def test_constructor_raises_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("TOPLEDGER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="TOPLEDGER_API_KEY"):
        TopLedger()


def test_constructor_reads_api_key_from_env(monkeypatch) -> None:
    monkeypatch.setenv("TOPLEDGER_API_KEY", "env-key")
    provider = TopLedger()
    assert provider.api_key == "env-key"
