"""Unit tests for the Zerion provider."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from metrics.overview import Overview, OverviewMetricType
from providers.zerion import Zerion

# Zerion chart response: data.attributes.points is a list of [unix_seconds, price].
_MOCK_RAW = {
    "data": {
        "attributes": {
            "points": [
                [1767225600, 200.0],  # 2026-01-01
            ]
        }
    }
}


def _make_mock_resp(payload):
    mock_resp = MagicMock()
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def test_get_sol_price_returns_overview_metric() -> None:
    provider = Zerion()
    sentinel_metric = object()

    with (
        patch.object(provider._session, "get", return_value=_make_mock_resp(_MOCK_RAW)),
        patch.object(
            Overview, "from_metric_type", return_value=sentinel_metric
        ) as mock_factory,
    ):
        result = provider.get_metric("overview_sol_price", "2026-01-01", "solana")

    assert result is sentinel_metric
    mock_factory.assert_called_once()
    assert mock_factory.call_args.kwargs["metric_type"] == OverviewMetricType.SOL_PRICE
    assert mock_factory.call_args.kwargs["value"] == 200.0


def test_fetch_rows_filters_by_date_range() -> None:
    provider = Zerion()
    raw = {
        "data": {
            "attributes": {
                "points": [
                    [1704067200, 100.0],  # 2024-01-01
                    [1767225600, 200.0],  # 2026-01-01
                    [1798761600, 300.0],  # 2027-01-01
                ]
            }
        }
    }

    with patch.object(provider._session, "get", return_value=_make_mock_resp(raw)):
        rows = provider.fetch_rows("overview_sol_price", "2025-01-01", "2026-06-01")

    assert len(rows) == 1
    assert rows[0]["date"] == "2026-01-01"
    assert rows[0]["value"] == 200.0


def test_fetch_rows_collapses_intraday_points_to_one_per_day() -> None:
    provider = Zerion()
    raw = {
        "data": {
            "attributes": {
                "points": [
                    [1767225600, 200.0],  # 2026-01-01 00:00 UTC
                    [1767268800, 210.0],  # 2026-01-01 12:00 UTC (later -> wins)
                ]
            }
        }
    }

    with patch.object(provider._session, "get", return_value=_make_mock_resp(raw)):
        rows = provider.fetch_rows("overview_sol_price", "2026-01-01", "2026-01-01")

    assert rows == [{"date": "2026-01-01", "value": 210.0}]


def test_fetch_rows_raises_on_unknown_metric() -> None:
    provider = Zerion()
    try:
        provider.fetch_rows("nonexistent_metric", "2026-01-01", "2026-01-31")
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "nonexistent_metric" in str(exc)
