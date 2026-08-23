"""Unit tests for the Goldsky provider's DEX and stablecoin metrics."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from metrics.defi import Defi, DefiMetricType
from metrics.stablecoin import Stablecoin, StablecoinMetricType
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
    # CDC soft-deletes and failed swap attempts must not be counted.
    assert "is_deleted = 0" in sql_sent
    assert "status = 1" in sql_sent
    assert "FORMAT JSON" in sql_sent
    assert mock_post.call_args.kwargs["params"]["database"] == "community"


def test_get_stablecoin_transfer_volume_returns_stablecoin_metric() -> None:
    provider = Goldsky(url="http://localhost:8123", user="default", password="key")

    query_resp = MagicMock()
    query_resp.raise_for_status = MagicMock()
    query_resp.json.return_value = {
        "data": [{"block_date": "2026-08-23", "transfer_volume": 143934926.687}]
    }

    sentinel_metric = object()

    with (
        patch.object(provider._session, "post", return_value=query_resp) as mock_post,
        patch.object(
            Stablecoin, "from_metric_type", return_value=sentinel_metric
        ) as mock_factory,
    ):
        result = provider.get_metric(
            "stablecoin_transfer_volume", "2026-08-23", "solana"
        )

    assert result is sentinel_metric
    assert (
        mock_factory.call_args.kwargs["metric_type"]
        == StablecoinMetricType.TRANSFER_VOLUME
    )
    assert mock_factory.call_args.kwargs["value"] == 143934926.687

    sql_sent = mock_post.call_args.kwargs["data"]
    assert "solana_stable_coin_transfers" in sql_sent
    # Failed transactions inflate volume ~8.5x, and mints/burns are not transfers.
    assert "is_deleted = 0" in sql_sent
    assert "status = 1" in sql_sent
    assert "'MintTo'" in sql_sent
    # No price data in the dataset, so only the 1:1 USD peg is summed.
    assert "asset_id = 'usd'" in sql_sent


def test_active_addresses_pools_both_sides_and_drops_nulls() -> None:
    provider = Goldsky(url="http://localhost:8123", user="default", password="key")

    query_resp = MagicMock()
    query_resp.raise_for_status = MagicMock()
    query_resp.json.return_value = {
        "data": [{"block_date": "2026-08-23", "active_addresses": "33894"}]
    }

    with patch.object(provider._session, "post", return_value=query_resp) as mock_post:
        rows = provider.fetch_rows(
            "stablecoin_active_addresses", "2026-08-23", "2026-08-23"
        )

    assert rows == [{"date": "2026-08-23", "value": 33894.0}]

    sql_sent = mock_post.call_args.kwargs["data"]
    assert "ARRAY JOIN [from_owner, to_owner]" in sql_sent
    assert "owner IS NOT NULL" in sql_sent
