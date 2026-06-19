"""Unit tests for the Allium provider."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.allium import Allium

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def provider() -> Allium:
    return Allium(api_key="test-allium-key-12345")


def _mock_two_step(rows: list) -> list:
    """Return side_effect list for the two-step create+run API flow."""
    create_resp = MagicMock()
    create_resp.json.return_value = {"query_id": "test-query-id"}
    create_resp.raise_for_status = MagicMock()

    run_resp = MagicMock()
    run_resp.json.return_value = {"data": rows}
    run_resp.raise_for_status = MagicMock()

    return [create_resp, run_resp]


# ---------------------------------------------------------------------------
# Allium — constructor
# ---------------------------------------------------------------------------


class TestAlliumInit:
    def test_raises_without_api_key(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="API key is required"):
                Allium()

    def test_reads_key_from_env(self) -> None:
        with patch.dict("os.environ", {"ALLIUM_API_KEY": "from-env"}):
            prov = Allium()
            assert prov.api_key == "from-env"

    def test_explicit_key_overrides_env(self) -> None:
        with patch.dict("os.environ", {"ALLIUM_API_KEY": "from-env"}):
            prov = Allium(api_key="explicit")
            assert prov.api_key == "explicit"


# ---------------------------------------------------------------------------
# Allium — properties
# ---------------------------------------------------------------------------


class TestAlliumProperties:
    def test_provider_name(self, provider: Allium) -> None:
        assert provider.provider_name == "Allium"

    def test_base_url(self, provider: Allium) -> None:
        assert provider.base_url == "https://api.allium.so/api/v1"


# ---------------------------------------------------------------------------
# Allium — _post (API key injection)
# ---------------------------------------------------------------------------


class TestAlliumPost:
    def test_injects_api_key_as_header(self, provider: Allium) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": []}
        mock_resp.raise_for_status = MagicMock()

        with patch.object(
            provider._session, "post", return_value=mock_resp
        ) as mock_post:
            provider._post("/explorer/queries", payload={"title": "test"})

        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["headers"]["X-API-Key"] == "test-allium-key-12345"
        assert "api.allium.so" in call_kwargs[0][0]


# ---------------------------------------------------------------------------
# Allium — get_metric (stablecoin_supply)
# ---------------------------------------------------------------------------


class TestGetMetricSupply:
    def test_returns_stablecoin_metric(self, provider: Allium) -> None:
        rows = [{"date": "2026-01-01", "usd": 5_000_000_000.0}]
        sentinel_metric = object()

        with (
            patch.object(provider._session, "post", side_effect=_mock_two_step(rows)),
            patch.object(
                Stablecoin, "from_metric_type", return_value=sentinel_metric
            ) as mock_factory,
        ):
            result = provider.get_metric("stablecoin_supply", "2026-01-01", "solana")

        assert result is sentinel_metric
        mock_factory.assert_called_once()
        assert (
            mock_factory.call_args.kwargs["metric_type"] == StablecoinMetricType.SUPPLY
        )
        assert mock_factory.call_args.kwargs["value"] == 5_000_000_000.0

    def test_returns_none_on_empty_data(self, provider: Allium) -> None:
        with patch.object(provider._session, "post", side_effect=_mock_two_step([])):
            result = provider.get_metric("stablecoin_supply", "2026-01-01", "solana")

        assert result is None

    def test_returns_none_when_value_is_null(self, provider: Allium) -> None:
        rows = [{"date": "2026-01-01", "usd": None}]

        with patch.object(provider._session, "post", side_effect=_mock_two_step(rows)):
            result = provider.get_metric("stablecoin_supply", "2026-01-01", "solana")

        assert result is None


# ---------------------------------------------------------------------------
# Allium — get_metric (stablecoin_transfer_volume)
# ---------------------------------------------------------------------------


class TestGetMetricTransferVolume:
    def test_returns_stablecoin_metric(self, provider: Allium) -> None:
        rows = [{"day": "2026-01-01", "volume_usd": 1_200_000_000.0}]
        sentinel_metric = object()

        with (
            patch.object(provider._session, "post", side_effect=_mock_two_step(rows)),
            patch.object(
                Stablecoin, "from_metric_type", return_value=sentinel_metric
            ) as mock_factory,
        ):
            result = provider.get_metric(
                "stablecoin_transfer_volume", "2026-01-01", "solana"
            )

        assert result is sentinel_metric
        mock_factory.assert_called_once()
        assert (
            mock_factory.call_args.kwargs["metric_type"]
            == StablecoinMetricType.TRANSFER_VOLUME
        )


# ---------------------------------------------------------------------------
# Allium — get_metric (stablecoin_transfer_count)
# ---------------------------------------------------------------------------


class TestGetMetricTransferCount:
    def test_returns_stablecoin_metric(self, provider: Allium) -> None:
        rows = [{"day": "2026-01-01", "transfer_count": 450_000}]
        sentinel_metric = object()

        with (
            patch.object(provider._session, "post", side_effect=_mock_two_step(rows)),
            patch.object(
                Stablecoin, "from_metric_type", return_value=sentinel_metric
            ) as mock_factory,
        ):
            result = provider.get_metric(
                "stablecoin_transfer_count", "2026-01-01", "solana"
            )

        assert result is sentinel_metric
        assert (
            mock_factory.call_args.kwargs["metric_type"]
            == StablecoinMetricType.TRANSFER_COUNT
        )


# ---------------------------------------------------------------------------
# Allium — get_metric (stablecoin_active_addresses)
# ---------------------------------------------------------------------------


class TestGetMetricActiveAddresses:
    def test_returns_stablecoin_metric(self, provider: Allium) -> None:
        rows = [{"day": "2026-01-01", "active_addresses": 85_000}]
        sentinel_metric = object()

        with (
            patch.object(provider._session, "post", side_effect=_mock_two_step(rows)),
            patch.object(
                Stablecoin, "from_metric_type", return_value=sentinel_metric
            ) as mock_factory,
        ):
            result = provider.get_metric(
                "stablecoin_active_addresses", "2026-01-01", "solana"
            )

        assert result is sentinel_metric
        assert (
            mock_factory.call_args.kwargs["metric_type"]
            == StablecoinMetricType.ACTIVE_ADDRESSES
        )


# ---------------------------------------------------------------------------
# Allium — date matching
# ---------------------------------------------------------------------------


class TestDateMatching:
    def test_skips_rows_with_wrong_date(self, provider: Allium) -> None:
        rows = [{"day": "2025-12-31", "total_supply_usd": 4_000_000_000.0}]

        with patch.object(provider._session, "post", side_effect=_mock_two_step(rows)):
            result = provider.get_metric("stablecoin_supply", "2026-01-01", "solana")

        assert result is None

    def test_handles_timestamp_date_field(self, provider: Allium) -> None:
        """Date field may contain a full timestamp; provider should truncate to date."""
        rows = [{"date": "2026-01-01T00:00:00Z", "usd": 5_000_000_000.0}]
        sentinel_metric = object()

        with (
            patch.object(provider._session, "post", side_effect=_mock_two_step(rows)),
            patch.object(Stablecoin, "from_metric_type", return_value=sentinel_metric),
        ):
            result = provider.get_metric("stablecoin_supply", "2026-01-01", "solana")

        assert result is sentinel_metric
