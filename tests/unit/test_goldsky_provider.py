"""Single focused test for DEX transaction count retrieval."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from metrics.defi import Defi, DefiMetricType
from providers.goldsky import Goldsky


def test_get_dex_transactions_returns_defi_metric() -> None:
    provider = Goldsky(url="http://localhost:8123", user="default", password="key")

    query_resp = MagicMock()
    query_resp.raise_for_status = MagicMock()
    query_resp.json.return_value = {
        # ClickHouse HTTP JSON output quotes 64-bit integers as strings.
        "data": [{"block_date": "2026-01-01", "transaction_count": "12345"}]
    }

    sentinel_metric = object()

    with (
        patch.object(provider._session, "post", return_value=query_resp) as mock_post,
        patch.object(
            Defi, "from_metric_type", return_value=sentinel_metric
        ) as mock_factory,
    ):
        result = provider.get_metric("defi_dex_transactions", "2026-01-01", "solana")

    assert result is sentinel_metric
    mock_factory.assert_called_once()
    assert (
        mock_factory.call_args.kwargs["metric_type"] == DefiMetricType.DEX_TRANSACTIONS
    )
    assert mock_factory.call_args.kwargs["value"] == 12345.0

    sql_sent = mock_post.call_args.kwargs["data"]
    assert "solana_dex_swaps" in sql_sent
    assert "FORMAT JSON" in sql_sent
