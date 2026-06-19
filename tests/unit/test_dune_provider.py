"""Single focused test for stablecoin supply retrieval."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.dune import Dune


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
