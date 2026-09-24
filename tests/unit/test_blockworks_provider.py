"""Unit tests for the Blockworks provider."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.blockworks import SOLANA_NETWORK_ID, Blockworks


def _mock_response(body: dict) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.json.return_value = body
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def test_get_stablecoin_total_supply_returns_stablecoin_metric() -> None:
    provider = Blockworks(api_key="key")
    mock_resp = _mock_response(
        {
            "error": None,
            "data": {
                "point_schema": [
                    {"field": "time", "time": True},
                    {"field": "stablecoin-outstanding-supply-usd", "time": False},
                ],
                "points": [[1767225600, 5_000_000_000.0]],  # 2026-01-01T00:00:00Z
            },
        }
    )
    sentinel_metric = object()

    with (
        patch.object(provider._session, "get", return_value=mock_resp) as mock_get,
        patch.object(
            Stablecoin, "from_metric_type", return_value=sentinel_metric
        ) as mock_factory,
    ):
        result = provider.get_metric("stablecoin_total_supply", "2026-01-01", "solana")

    assert result is sentinel_metric
    assert mock_get.call_args.args[0] == (
        f"https://api.blockworks.com/query/timeseries/blockchains/1d/{SOLANA_NETWORK_ID}"
    )
    assert mock_get.call_args.kwargs["headers"] == {"X-Blockworks-API-Key": "key"}
    # `end` is exclusive in the Data API, so it is one day past the requested date.
    assert mock_get.call_args.kwargs["params"] == {
        "start": "2026-01-01",
        "end": "2026-01-02",
        "selections": "stablecoin-outstanding-supply-usd",
    }
    mock_factory.assert_called_once()
    assert (
        mock_factory.call_args.kwargs["metric_type"]
        == StablecoinMetricType.TOTAL_SUPPLY
    )
    assert mock_factory.call_args.kwargs["value"] == 5_000_000_000.0


def test_fetch_rows_skips_null_values() -> None:
    provider = Blockworks(api_key="key")
    mock_resp = _mock_response(
        {
            "error": None,
            "data": {
                "point_schema": [
                    {"field": "time", "time": True},
                    {"field": "active-addresses", "time": False},
                ],
                "points": [[1767225600, 2_000_000], [1767312000, None]],
            },
        }
    )

    with patch.object(provider._session, "get", return_value=mock_resp):
        rows = provider.fetch_rows("overview_fee_payers", "2026-01-01", "2026-01-02")

    assert rows == [{"date": "2026-01-01", "value": 2_000_000.0}]


def test_fetch_rows_raises_on_api_error() -> None:
    provider = Blockworks(api_key="key")
    mock_resp = _mock_response({"error": "unknown query parameter", "data": None})

    with (
        patch.object(provider._session, "get", return_value=mock_resp),
        pytest.raises(RuntimeError, match="unknown query parameter"),
    ):
        provider.fetch_rows("defi_dex_volume", "2026-01-01", "2026-01-01")
