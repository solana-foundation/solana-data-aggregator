"""Unit tests for the DefiLlama provider."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.defillama import DefiLlama

_MOCK_RAW = [
    {
        "date": "1767225600",
        "totalCirculating": {"peggedUSD": 5_000_000_000.0},
    },  # 2026-01-01
]


def _make_mock_resp(payload):
    mock_resp = MagicMock()
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def test_get_stablecoin_supply_returns_stablecoin_metric() -> None:
    provider = DefiLlama()
    sentinel_metric = object()

    with (
        patch.object(provider._session, "get", return_value=_make_mock_resp(_MOCK_RAW)),
        patch.object(
            Stablecoin, "from_metric_type", return_value=sentinel_metric
        ) as mock_factory,
    ):
        result = provider.get_metric("stablecoin_supply", "2026-01-01", "solana")

    assert result is sentinel_metric
    mock_factory.assert_called_once()
    assert mock_factory.call_args.kwargs["metric_type"] == StablecoinMetricType.SUPPLY
    assert mock_factory.call_args.kwargs["value"] == 5_000_000_000.0


def test_fetch_rows_filters_by_date_range() -> None:
    provider = DefiLlama()
    raw = [
        {
            "date": "1704067200",
            "totalCirculating": {"peggedUSD": 1_000.0},
        },  # 2024-01-01
        {
            "date": "1767225600",
            "totalCirculating": {"peggedUSD": 5_000_000_000.0},
        },  # 2026-01-01
        {
            "date": "1798761600",
            "totalCirculating": {"peggedUSD": 9_000_000_000.0},
        },  # 2027-01-01
    ]

    with patch.object(provider._session, "get", return_value=_make_mock_resp(raw)):
        rows = provider.fetch_rows("stablecoin_supply", "2025-01-01", "2026-06-01")

    assert len(rows) == 1
    assert rows[0]["date"] == "2026-01-01"
    assert rows[0]["value"] == 5_000_000_000.0


def test_fetch_rows_raises_on_unknown_metric() -> None:
    provider = DefiLlama()
    try:
        provider.fetch_rows("nonexistent_metric", "2026-01-01", "2026-01-31")
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "nonexistent_metric" in str(exc)
