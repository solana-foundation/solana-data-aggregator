"""Unit tests for the Stakewiz provider."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

from metrics.network import Network, NetworkMetricType
from providers.stakewiz import Stakewiz

TODAY = "2026-06-12"

_VALIDATORS_RAW = [
    {"delinquent": False, "activated_stake": 1_000.0, "asn": "AS111", "epoch": 600},
    {"delinquent": False, "activated_stake": 500.0, "asn": "AS222", "epoch": 600},
    {"delinquent": False, "activated_stake": 300.0, "asn": "AS333", "epoch": 600},
    {"delinquent": False, "activated_stake": 200.0, "asn": "AS444", "epoch": 600},
    {"delinquent": True, "activated_stake": 999.0, "asn": "AS555", "epoch": 600},
    # stale epoch — should be excluded even though not delinquent
    {"delinquent": False, "activated_stake": 999.0, "asn": "AS666", "epoch": 599},
]


def _mock_resp(payload):
    m = MagicMock()
    m.json.return_value = payload
    m.raise_for_status = MagicMock()
    return m


def _patch_today():
    return patch(
        "providers.stakewiz.datetime.date",
        **{
            "today.return_value": datetime.date.fromisoformat(TODAY),
            "fromisoformat": datetime.date.fromisoformat,
        },
    )


def test_get_total_stake_returns_network_metric() -> None:
    provider = Stakewiz()
    sentinel_metric = object()

    with (
        patch.object(
            provider._session, "get", return_value=_mock_resp(_VALIDATORS_RAW)
        ),
        _patch_today(),
        patch.object(
            Network, "from_metric_type", return_value=sentinel_metric
        ) as mock_factory,
    ):
        result = provider.get_metric("network_total_stake", TODAY, "solana")

    assert result is sentinel_metric
    mock_factory.assert_called_once()
    assert mock_factory.call_args.kwargs["metric_type"] == NetworkMetricType.TOTAL_STAKE
    # 1000 + 500 + 300 + 200 = 2000 SOL (delinquent excluded)
    assert mock_factory.call_args.kwargs["value"] == 2_000.0
