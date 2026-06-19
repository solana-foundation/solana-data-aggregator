"""Unit tests for the Token Terminal provider."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.token_terminal import TokenTerminal


def test_get_stablecoin_supply_returns_stablecoin_metric() -> None:
    provider = TokenTerminal(api_key="test-token-terminal-key")
    mock_response = [
        {
            "timestamp": "2026-01-01T00:00:00.000Z",
            "ecosystem_stablecoin_supply": 10_987_267_570.64,
        },
    ]
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_response
    mock_resp.raise_for_status = MagicMock()
    sentinel_metric = object()

    with (
        patch.object(provider._session, "get", return_value=mock_resp),
        patch.object(
            Stablecoin, "from_metric_type", return_value=sentinel_metric
        ) as mock_factory,
    ):
        result = provider.get_metric("stablecoin_supply", "2026-01-01", "solana")

    assert result is sentinel_metric
    mock_factory.assert_called_once()
    assert mock_factory.call_args.kwargs["metric_type"] == StablecoinMetricType.SUPPLY
    assert mock_factory.call_args.kwargs["value"] == 10_987_267_570.64
