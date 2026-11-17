"""Unit tests for the Token Terminal provider."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from metrics.defi import DefiMetricType
from metrics.lending import Lending
from metrics.network import Network, NetworkMetricType
from metrics.overview import Overview, OverviewMetricType
from metrics.stablecoin import Stablecoin, StablecoinMetricType
from providers.token_terminal import TokenTerminal


def test_get_stablecoin_circulating_supply_sums_native_and_bridged() -> None:
    provider = TokenTerminal(api_key="test-token-terminal-key")
    mock_response = [
        {
            "timestamp": "2026-01-01T00:00:00.000Z",
            "ecosystem_stablecoin_supply": 10_987_267_570.64,
            "ecosystem_bridged_stablecoin_supply": 2_500_000_000.0,
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
        result = provider.get_metric(
            "stablecoin_circulating_supply", "2026-01-01", "solana"
        )

    assert result is sentinel_metric
    mock_factory.assert_called_once()
    assert (
        mock_factory.call_args.kwargs["metric_type"]
        == StablecoinMetricType.CIRCULATING_SUPPLY
    )
    # Circulating supply = native issuance + bridged-in supply.
    assert mock_factory.call_args.kwargs["value"] == pytest.approx(13_487_267_570.64)


def test_get_stablecoin_circulating_supply_tolerates_missing_bridged_value() -> None:
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
        result = provider.get_metric(
            "stablecoin_circulating_supply", "2026-01-01", "solana"
        )

    assert result is sentinel_metric
    assert mock_factory.call_args.kwargs["value"] == 10_987_267_570.64


def test_get_validator_count_returns_network_metric() -> None:
    provider = TokenTerminal(api_key="test-token-terminal-key")
    mock_response = [
        {"timestamp": "2026-01-01T00:00:00.000Z", "number_of_validators": 683},
    ]
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_response
    mock_resp.raise_for_status = MagicMock()
    sentinel_metric = object()

    with (
        patch.object(provider._session, "get", return_value=mock_resp),
        patch.object(
            Network, "from_metric_type", return_value=sentinel_metric
        ) as mock_factory,
    ):
        result = provider.get_metric("network_validator_count", "2026-01-01", "solana")

    assert result is sentinel_metric
    mock_factory.assert_called_once()
    assert (
        mock_factory.call_args.kwargs["metric_type"]
        == NetworkMetricType.VALIDATOR_COUNT
    )
    assert mock_factory.call_args.kwargs["value"] == 683


@pytest.mark.parametrize(
    ("metric", "value_field", "value", "metric_type"),
    [
        (
            "overview_slots",
            "slot_count",
            203507,
            OverviewMetricType.SLOTS,
        ),
        (
            "overview_non_vote_tx_count_success",
            "successful_non_vote_transaction_count",
            89424992,
            OverviewMetricType.TX_COUNT_NON_VOTE_SUCCESS,
        ),
        (
            "overview_non_vote_tx_count_failed",
            "failed_non_vote_transaction_count",
            63705940,
            OverviewMetricType.TX_COUNT_NON_VOTE_FAILED,
        ),
        (
            "overview_compute_units",
            "compute_units_per_block",
            33179623,
            OverviewMetricType.COMPUTE_UNITS,
        ),
    ],
)
def test_overview_metrics_map_to_their_metric_type(
    metric: str, value_field: str, value: int, metric_type: OverviewMetricType
) -> None:
    """Each overview metric reads its own response field and types correctly."""
    provider = TokenTerminal(api_key="test-token-terminal-key")
    mock_resp = MagicMock()
    mock_resp.json.return_value = [
        {"timestamp": "2026-08-03T00:00:00.000Z", value_field: value}
    ]
    mock_resp.raise_for_status = MagicMock()
    sentinel_metric = object()

    with (
        patch.object(provider._session, "get", return_value=mock_resp),
        patch.object(
            Overview, "from_metric_type", return_value=sentinel_metric
        ) as mock_factory,
    ):
        result = provider.get_metric(metric, "2026-08-03", "solana")

    assert result is sentinel_metric
    mock_factory.assert_called_once()
    assert mock_factory.call_args.kwargs["metric_type"] == metric_type
    assert mock_factory.call_args.kwargs["value"] == value


def test_every_supported_metric_has_a_metric_type() -> None:
    """Each entry in METRIC_MAP must resolve to a typed metric model."""
    mapped = (
        set(TokenTerminal._OVERVIEW_METRIC_TYPE_MAP)
        | set(TokenTerminal._STABLECOIN_METRIC_TYPE_MAP)
        | set(TokenTerminal._DEFI_METRIC_TYPE_MAP)
        | set(TokenTerminal._LENDING_METRIC_TYPE_MAP)
        | set(TokenTerminal._NETWORK_METRIC_TYPE_MAP)
    )
    assert set(TokenTerminal.METRIC_MAP) == mapped


def _mock_response(payload: object) -> MagicMock:
    """Build a requests response stub that returns the given JSON payload."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# -- overview_fees: USD fees divided by the same day's SOL price ------------


def test_overview_fees_divides_usd_fees_by_same_day_price() -> None:
    """Fees are served in USD; SOL is recovered by dividing, never by summing."""
    provider = TokenTerminal(api_key="test-token-terminal-key")
    mock_resp = _mock_response(
        [
            {
                "timestamp": "2026-08-02T00:00:00.000Z",
                "fees": 180.0,
                "price": 180.0,
            },
            {
                "timestamp": "2026-08-03T00:00:00.000Z",
                "fees": 1_000_000.0,
                "price": 200.0,
            },
        ]
    )

    with patch.object(provider._session, "get", return_value=mock_resp) as mock_get:
        rows = provider.fetch_rows("overview_fees", "2026-08-02", "2026-08-03")

    assert rows == [
        {"date": "2026-08-02", "value": pytest.approx(1.0)},
        {"date": "2026-08-03", "value": pytest.approx(5000.0)},
    ]
    params = mock_get.call_args.kwargs["params"]
    assert params["metric_ids"] == "fees,price"


def test_overview_fees_drops_days_with_missing_or_nonpositive_price() -> None:
    """A day without a usable price is dropped, not divided or filled."""
    provider = TokenTerminal(api_key="test-token-terminal-key")
    mock_resp = _mock_response(
        [
            {
                "timestamp": "2026-08-02T00:00:00.000Z",
                "fees": 1_000_000.0,
                "price": None,
            },
            {
                "timestamp": "2026-08-03T00:00:00.000Z",
                "fees": 1_000_000.0,
                "price": 0,
            },
            {
                "timestamp": "2026-08-04T00:00:00.000Z",
                "fees": None,
                "price": 200.0,
            },
            {
                "timestamp": "2026-08-05T00:00:00.000Z",
                "fees": 500_000.0,
                "price": 250.0,
            },
        ]
    )

    with patch.object(provider._session, "get", return_value=mock_resp):
        rows = provider.fetch_rows("overview_fees", "2026-08-02", "2026-08-05")

    assert rows == [{"date": "2026-08-05", "value": pytest.approx(2000.0)}]


def test_get_metric_overview_fees_returns_overview_fee_metric() -> None:
    provider = TokenTerminal(api_key="test-token-terminal-key")
    mock_resp = _mock_response(
        [{"timestamp": "2026-08-03T00:00:00.000Z", "fees": 1_000_000.0, "price": 200.0}]
    )
    sentinel_metric = object()

    with (
        patch.object(provider._session, "get", return_value=mock_resp),
        patch.object(
            Overview, "from_metric_type", return_value=sentinel_metric
        ) as mock_factory,
    ):
        result = provider.get_metric("overview_fees", "2026-08-03", "solana")

    assert result is sentinel_metric
    mock_factory.assert_called_once()
    assert mock_factory.call_args.kwargs["metric_type"] == OverviewMetricType.FEES
    assert mock_factory.call_args.kwargs["value"] == pytest.approx(5000.0)


def _volume_provider(rows, unavailable=(), metric_id="asset_transfer_volume"):
    provider = TokenTerminal(api_key="test-token-terminal-key")
    assets = [
        {
            "asset_id": asset,
            "reference_asset_id": "usdollar",
            "addresses": [{"chain_id": "solana", "token_address": asset}],
        }
        for asset in ("usdc", "usdt")
    ]

    def get(endpoint, *, params=None):
        if endpoint == "/assets":
            return {"data": assets, "total_count": len(assets)}
        if endpoint == f"/metrics/{metric_id}":
            assert params["chain_ids"] == "solana"
            assert params["asset_ids"] == "usdc,usdt"
            assert params["start"] == "2020-01-01"
            return {"data": rows}
        asset = endpoint.split("/")[-1]
        return {
            "data": {"available_metrics": ([] if asset in unavailable else [metric_id])}
        }

    provider._get = MagicMock(side_effect=get)
    return provider


def _volume_row(asset, date, value):
    return {
        "asset_id": asset,
        "chain_id": "solana",
        "timestamp": date,
        "metric_id": "asset_transfer_volume",
        "value": value,
    }


def test_stablecoin_volume_uses_historical_membership_and_omits_gaps():
    provider = _volume_provider(
        [
            _volume_row("usdc", "2025-01-01", 10),
            _volume_row("usdc", "2025-01-02", 20),
            _volume_row("usdc", "2025-01-03", 30),
            _volume_row("usdt", "2025-01-02", 5),
            _volume_row("usdt", "2025-01-04", 7),
        ]
    )
    assert provider.fetch_rows(
        "stablecoin_transfer_volume", "2025-01-01", "2025-01-04"
    ) == [
        {"date": "2025-01-01", "value": 10},
        {"date": "2025-01-02", "value": 25},
    ]
    # A subsequent narrow request keeps the same historical membership.
    assert (
        provider.fetch_rows("stablecoin_transfer_volume", "2025-01-03", "2025-01-03")
        == []
    )
    assert provider._get.call_count == 2


def test_stablecoin_volume_distinguishes_unavailable_data_and_zero():
    provider = _volume_provider(
        [_volume_row("usdc", "2025-01-01", 0)], unavailable=("usdt",)
    )
    metric = provider.get_metric("stablecoin_transfer_volume", "2025-01-01", "solana")
    assert isinstance(metric, Stablecoin)
    assert metric.metric_type == StablecoinMetricType.TRANSFER_VOLUME
    assert metric.value == 0


def test_stablecoin_volume_rejects_missing_supported_history():
    provider = _volume_provider([_volume_row("usdc", "2025-01-01", 10)])
    with pytest.raises(ValueError, match="Missing Solana transfer history"):
        provider.fetch_rows("stablecoin_transfer_volume", "2025-01-01", "2025-01-01")


@pytest.mark.parametrize("value", [None, float("nan"), -1])
def test_stablecoin_volume_rejects_invalid_values(value):
    provider = _volume_provider([_volume_row("usdc", "2025-01-01", value)])
    with pytest.raises(ValueError):
        provider.fetch_rows("stablecoin_transfer_volume", "2025-01-01", "2025-01-01")


def test_stablecoin_volume_rejects_partial_api_success():
    provider = TokenTerminal(api_key="test-token-terminal-key")
    with patch.object(
        provider, "_get", return_value={"data": [], "errors": [{"code": "NOT_FOUND"}]}
    ):
        with pytest.raises(ValueError, match="partial API errors"):
            provider.fetch_rows(
                "stablecoin_transfer_volume", "2025-01-01", "2025-01-01"
            )


def test_stablecoin_volume_rejects_duplicate_daily_rows():
    row = _volume_row("usdc", "2025-01-01", 10)
    provider = _volume_provider([row, row])
    with pytest.raises(ValueError, match="Duplicate daily"):
        provider.fetch_rows("stablecoin_transfer_volume", "2025-01-01", "2025-01-01")


def _count_row(entity, date, value, asset=False, chain="solana"):
    return {
        "asset_id" if asset else "project_id": entity,
        "timestamp": date,
        "chain_id": chain,
        "value": value,
    }


def _count_get(rows, assets=None):
    def get(endpoint, *, params=None):
        if endpoint.startswith("/market-sectors/"):
            ids = {
                "exchange": ["orca", "meteora", "jupiter", "perps"],
                "derivatives": ["perps"],
                "dex-aggregators": ["jupiter"],
            }
            return {
                "data": {
                    "projects": [
                        {"project_id": p} for p in ids[endpoint.split("/")[-1]]
                    ]
                }
            }
        if endpoint == "/assets":
            return {"data": assets, "total_count": len(assets)}
        return {"data": rows}

    return get


def test_dex_count_uses_positive_spot_protocols_and_deduplicates():
    provider = TokenTerminal(api_key="test-key")
    rows = [
        _count_row("orca", "2026-11-09", "10"),
        _count_row("orca", "2026-11-09", 15),
        _count_row("meteora", "2026-11-09", 0),
        _count_row("jupiter", "2026-11-09", 100),
        _count_row("perps", "2026-11-09", 100),
        _count_row("nonexchange", "2026-11-09", 100),
        _count_row("orca", "2026-11-10", 0),
        _count_row("orca", "2026-11-08", 10),
    ]
    with patch.object(provider, "_get", side_effect=_count_get(rows)):
        assert provider.fetch_rows("defi_dex_count", "2026-11-09", "2026-11-10") == [
            {"date": "2026-11-09", "value": 1},
            {"date": "2026-11-10", "value": 0},
        ]
        result = provider.get_metric("defi_dex_count", "2026-11-09", "solana")
        assert result.metric_type == DefiMetricType.DEX_COUNT


def test_stablecoin_count_uses_cap_not_activity_and_includes_bridged():
    assets = [
        {
            "asset_id": asset,
            "reference_asset_id": peg,
            "addresses": [
                {"chain_id": chain, "token_address": asset, "bridged": bridged}
            ],
        }
        for asset, peg, chain, bridged in [
            ("usdc", "usdollar", "solana", False),
            ("dai", "usdollar", "solana", True),
            ("usdt", "usdollar", "solana", False),
            ("eurc", "euro", "solana", False),
            ("other", "usdollar", "ethereum", False),
        ]
    ]
    rows = [
        _count_row(a, "2026-11-09", v, asset=True)
        for a, v in [
            ("usdc", 10),
            ("usdc", 20),
            ("dai", 1),
            ("usdt", 0),
            ("eurc", 5),
            ("other", 5),
        ]
    ]
    provider = TokenTerminal(api_key="test-key")
    with patch.object(provider, "_get", side_effect=_count_get(rows, assets)) as get:
        result = provider.get_metric("stablecoin_count", "2026-11-09", "solana")
    assert result.value == 2
    assert result.metric_type == StablecoinMetricType.COUNT
    params = get.call_args.kwargs["params"]
    assert params["asset_ids"] == "dai,usdc,usdt"
    assert params["assets_bridged"] == "true"
    assert get.call_args.args[0] == "/metrics/asset_market_cap_circulating"


@pytest.mark.parametrize("metric", ["defi_dex_count", "stablecoin_count"])
def test_count_partial_metadata_errors_fail(metric):
    provider = TokenTerminal(api_key="test-key")
    with patch.object(
        provider, "_get", return_value={"data": [], "errors": [{"code": "NOT_FOUND"}]}
    ):
        with pytest.raises(ValueError, match="Incomplete|partial API errors"):
            provider.fetch_rows(metric, "2026-11-09", "2026-11-10")


@pytest.mark.parametrize("value", [None, float("nan"), -1])
def test_count_invalid_values_are_not_zero(value):
    provider = TokenTerminal(api_key="test-key")
    with patch.object(
        provider,
        "_get",
        side_effect=_count_get([_count_row("orca", "2026-11-09", value)]),
    ):
        with pytest.raises(ValueError):
            provider.fetch_rows("defi_dex_count", "2026-11-09", "2026-11-09")


def test_count_empty_response_does_not_invent_zero_days():
    provider = TokenTerminal(api_key="test-key")
    with patch.object(provider, "_get", side_effect=_count_get([])):
        assert provider.fetch_rows("defi_dex_count", "2026-11-09", "2026-11-10") == []


def _lending_row(product, date, deposits, borrowed):
    return {
        "timestamp": date,
        "chain_id": "solana",
        "product_id": product,
        "tvl": deposits,
        "active_loans": borrowed,
    }


def _lending_provider(kamino, jupiter):
    provider = TokenTerminal(api_key="test-key")

    def get(endpoint, *, params=None):
        assert params["metric_ids"] == "tvl,active_loans"
        assert params["chain_ids"] == "solana"
        if endpoint == "/projects/kamino/products/kaminolend/metrics":
            return {"data": kamino}
        if endpoint == "/projects/jupiter/products/jupiterlend/metrics":
            return {"data": jupiter}
        raise AssertionError(endpoint)

    provider._get = MagicMock(side_effect=get)
    return provider


def test_lending_uses_supplied_tvl_and_ratio_of_aligned_sums():
    provider = _lending_provider(
        [_lending_row("kaminolend", "2026-01-01", 100, 20)],
        [_lending_row("jupiterlend", "2026-01-01", 300, 180)],
    )
    expected = {
        "lending_total_deposits": 400,
        "lending_total_borrowed": 200,
        "lending_utilization_rate": 50,
    }
    for metric, value in expected.items():
        result = provider.get_metric(metric, "2026-01-01", "solana")
        assert isinstance(result, Lending)
        assert result.value == value
        assert result.metric_type == provider._LENDING_METRIC_TYPE_MAP[metric]
    assert provider._get.call_count == 2


def test_lending_history_membership_and_missing_rows():
    provider = _lending_provider(
        [
            _lending_row("kaminolend", "2024-08-01", 100, 20),
            _lending_row("kaminolend", "2025-08-01", 200, 40),
            _lending_row("kaminolend", "2025-08-02", 250, 50),
        ],
        [
            _lending_row("jupiterlend", "2025-08-01", 100, 10),
            _lending_row("jupiterlend", "2025-08-03", 100, 10),
        ],
    )
    assert provider.fetch_rows(
        "lending_total_deposits", "2024-08-01", "2024-08-01"
    ) == [
        {"date": "2024-08-01", "value": 100},
    ]
    for metric in provider._LENDING_METRIC_TYPE_MAP:
        assert provider.fetch_rows(metric, "2025-08-02", "2025-08-03") == []


def test_lending_zero_deposits_have_no_utilization():
    provider = _lending_provider(
        [_lending_row("kaminolend", "2026-01-01", 0, 0)],
        [_lending_row("jupiterlend", "2026-01-01", 0, 0)],
    )
    assert (
        provider.fetch_rows("lending_utilization_rate", "2026-01-01", "2026-01-01")
        == []
    )
    assert provider.fetch_rows(
        "lending_total_deposits", "2026-01-01", "2026-01-01"
    ) == [
        {"date": "2026-01-01", "value": 0},
    ]


def test_lending_partial_success_is_not_a_partial_total():
    provider = TokenTerminal(api_key="test-key")
    with patch.object(
        provider, "_get", return_value={"data": [], "errors": [{"code": "NOT_FOUND"}]}
    ):
        with pytest.raises(ValueError, match="Incomplete lending"):
            provider.fetch_rows("lending_total_deposits", "2026-01-01", "2026-01-01")


@pytest.mark.parametrize("value", [None, float("nan"), -1])
def test_lending_invalid_or_missing_balances_fail(value):
    provider = _lending_provider(
        [_lending_row("kaminolend", "2026-01-01", value, 20)],
        [_lending_row("jupiterlend", "2026-01-01", 300, 180)],
    )
    with pytest.raises(ValueError):
        provider.fetch_rows("lending_total_deposits", "2026-01-01", "2026-01-01")


def test_lending_rejects_duplicate_product_days():
    row = _lending_row("kaminolend", "2026-01-01", 100, 20)
    provider = _lending_provider(
        [row, row], [_lending_row("jupiterlend", "2026-01-01", 300, 180)]
    )
    with pytest.raises(ValueError, match="Duplicate lending"):
        provider.fetch_rows("lending_total_deposits", "2026-01-01", "2026-01-01")


def test_stablecoin_transfer_count_uses_event_counts_and_omits_gaps():
    rows = [
        _volume_row("usdc", "2025-01-01", 3),
        _volume_row("usdc", "2025-01-02", 0),
        _volume_row("usdc", "2025-01-03", 7),
        _volume_row("usdt", "2025-01-02", 4),
    ]
    for row in rows:
        row["metric_id"] = "asset_transfer_count"
    provider = _volume_provider(rows, metric_id="asset_transfer_count")
    assert provider.fetch_rows(
        "stablecoin_transfer_count", "2025-01-01", "2025-01-03"
    ) == [
        {"date": "2025-01-01", "value": 3},
        {"date": "2025-01-02", "value": 4},
    ]
    result = provider.get_metric("stablecoin_transfer_count", "2025-01-02", "solana")
    assert result.metric_type == StablecoinMetricType.TRANSFER_COUNT
    assert result.value == 4
    assert provider._get.call_count == 2


def test_network_average_tps_uses_non_vote_count_and_preserves_zero():
    provider = TokenTerminal(api_key="test-key")
    payload = {
        "data": [
            {
                "timestamp": "2026-11-14",
                "non_vote_transaction_count": 864000,
                "transaction_count": 1728000,
            },
            {"timestamp": "2026-11-15", "non_vote_transaction_count": 0},
            {"timestamp": "2026-11-16", "non_vote_transaction_count": None},
        ]
    }
    with patch.object(provider, "_get", return_value=payload) as get:
        assert provider.fetch_rows("network_avg_tps", "2026-11-14", "2026-11-16") == [
            {"date": "2026-11-14", "value": 10},
            {"date": "2026-11-15", "value": 0},
        ]
        result = provider.get_metric("network_avg_tps", "2026-11-14", "solana")
        assert result.metric_type == NetworkMetricType.AVG_TPS
        assert result.unit == "TPS"
        assert result.value == 10
        assert (
            get.call_args.kwargs["params"]["metric_ids"] == "non_vote_transaction_count"
        )


def test_stablecoin_metrics_share_paginated_asset_cache():
    provider = TokenTerminal(api_key="test-key")
    assets = [
        {
            "asset_id": asset,
            "reference_asset_id": "usdollar",
            "addresses": [{"chain_id": "solana", "token_address": asset}],
        }
        for asset in ("usdc", "usdt")
    ]

    def get(endpoint, *, params=None):
        if endpoint == "/assets":
            return {"data": [assets[params["offset"]]], "total_count": 2}
        assert params["asset_ids"] == "usdc,usdt"
        return {
            "data": [
                {
                    "asset_id": asset["asset_id"],
                    "chain_id": "solana",
                    "timestamp": "2026-11-15",
                    "value": 10,
                }
                for asset in assets
            ]
        }

    with patch.object(provider, "_get", side_effect=get) as request:
        for metric, value in (
            ("stablecoin_transfer_volume", 20),
            ("stablecoin_transfer_count", 20),
            ("stablecoin_count", 2),
        ):
            assert provider.fetch_rows(metric, "2026-11-15", "2026-11-15") == [
                {"date": "2026-11-15", "value": value}
            ]
        listings = [
            call for call in request.call_args_list if call.args[0] == "/assets"
        ]
        assert [call.kwargs["params"]["offset"] for call in listings] == [0, 1]


def test_stablecoin_asset_cache_retries_after_partial_listing_error():
    provider = TokenTerminal(api_key="test-key")
    with patch.object(
        provider,
        "_get",
        side_effect=[
            {"data": [], "errors": [{"code": "ERROR"}]},
            {"data": [], "total_count": 0},
        ],
    ) as request:
        with pytest.raises(ValueError, match="partial API errors"):
            provider._usd_stablecoin_assets()
        assert provider._usd_stablecoin_assets() == []
        assert provider._usd_stablecoin_assets() == []
        assert request.call_count == 2


def _dex_trade_get(counts, volumes):
    sectors = {
        "exchange": [
            "orca",
            "meteora",
            "raydium",
            "stonkfun",
            "axiomtrade",
            "photon",
            "jupiter",
            "perps",
        ],
        "derivatives": ["perps"],
        "dex-aggregators": ["jupiter"],
    }

    def get(endpoint, *, params=None):
        if endpoint.startswith("/market-sectors/"):
            return {
                "data": {
                    "projects": [
                        {"project_id": p} for p in sectors[endpoint.split("/")[-1]]
                    ]
                }
            }
        assert params["chain_ids"] == "solana"
        return {"data": counts if endpoint == "/metrics/trade_count" else volumes}

    return get


def test_dex_trades_sum_venues_without_aggregators_terminals_or_launchlab_overlap():
    provider = TokenTerminal(api_key="test-key")
    counts = [
        _count_row(p, "2026-11-09", v)
        for p, v in (
            ("orca", 10),
            ("meteora", 20),
            ("raydium", 30),
            ("stonkfun", 5),
            ("axiomtrade", 100),
            ("photon", 100),
            ("jupiter", 100),
            ("perps", 100),
        )
    ]
    with patch.object(provider, "_get", side_effect=_dex_trade_get(counts, counts)):
        assert provider.fetch_rows(
            "defi_dex_transactions", "2026-11-09", "2026-11-09"
        ) == [{"date": "2026-11-09", "value": 60}]
        result = provider.get_metric("defi_dex_transactions", "2026-11-09", "solana")
        assert result.metric_type == DefiMetricType.DEX_TRANSACTIONS


def test_dex_trades_omit_days_with_missing_active_venue():
    provider = TokenTerminal(api_key="test-key")
    counts = [_count_row("orca", "2026-11-09", 10), _count_row("orca", "2026-11-10", 0)]
    volumes = [
        _count_row("orca", "2026-11-09", 100),
        _count_row("raydium", "2026-11-09", 100),
        _count_row("orca", "2026-11-10", 0),
    ]
    with patch.object(provider, "_get", side_effect=_dex_trade_get(counts, volumes)):
        assert provider.fetch_rows(
            "defi_dex_transactions", "2026-11-09", "2026-11-10"
        ) == [{"date": "2026-11-10", "value": 0}]


@pytest.mark.parametrize("value", [None, -1, float("nan"), float("inf")])
def test_dex_trades_reject_invalid_values(value):
    provider = TokenTerminal(api_key="test-key")
    rows = [_count_row("orca", "2026-11-09", value)]
    with patch.object(provider, "_get", side_effect=_dex_trade_get(rows, rows)):
        with pytest.raises(ValueError, match="Invalid DEX metric value"):
            provider.fetch_rows("defi_dex_transactions", "2026-11-09", "2026-11-09")


def test_dex_trades_reject_duplicate_project_rows():
    provider = TokenTerminal(api_key="test-key")
    rows = [_count_row("orca", "2026-11-09", 10)] * 2
    with patch.object(provider, "_get", side_effect=_dex_trade_get(rows, rows)):
        with pytest.raises(ValueError, match="Duplicate DEX project metric row"):
            provider.fetch_rows("defi_dex_transactions", "2026-11-09", "2026-11-09")
