"""Shared helpers in providers/base.py."""

from __future__ import annotations

from providers.base import stablecoin_supply_rows

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
EURC = "HzwqbKZw8HxMN6bF2yFZNrht3c2iXXzpKcFu7uBEDKtr"


def test_stablecoin_supply_rows_normalizes_and_filters() -> None:
    raw = [
        {"d": "2026-01-01T00:00:00", "m": USDC, "t": "usdc", "v": 10},
        {"d": "2026-01-02", "m": USDT, "t": None, "v": "5.5"},
        {"d": "2025-12-31", "m": USDC, "t": "USDC", "v": 1},  # before range
        {"d": "2026-01-01", "m": None, "t": "X", "v": 1},  # no mint
        {"d": "2026-01-01", "m": EURC, "t": "EURC", "v": None},  # no value
    ]
    rows = stablecoin_supply_rows(
        raw,
        date_field="d",
        mint_field="m",
        token_field="t",
        value_field="v",
        start_date="2026-01-01",
        end_date="2026-01-02",
    )
    assert rows == [
        {"date": "2026-01-01", "mint_address": USDC, "token": "USDC", "value": 10.0},
        {"date": "2026-01-02", "mint_address": USDT, "token": None, "value": 5.5},
    ]
