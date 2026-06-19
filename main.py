"""CLI entrypoint: run providers and dump fetched metrics to disk.

Loads credentials from .env and runs fetch_rows for each metric a provider
supports over a date range, writing one JSON file per provider+metric to
_output/<provider>_<metric>.json.

Usage:
    python main.py
    python main.py --providers artemis,dune --start 2026-06-09 --end 2026-06-15
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from dotenv import load_dotenv

from providers.allium import Allium
from providers.artemis import Artemis
from providers.base import BaseProvider
from providers.blockworks import Blockworks
from providers.defillama import DefiLlama
from providers.dune import Dune
from providers.rwa import Rwa
from providers.stakewiz import Stakewiz
from providers.token_terminal import TokenTerminal
from providers.validators_app import ValidatorsApp

OUTPUT_DIR = Path(__file__).parent / "_output"
LOOKBACK_DAYS = 7

# (cli name, class, required env var or None if no key needed)
PROVIDER_REGISTRY: List[tuple[str, Type[BaseProvider], Optional[str]]] = [
    ("allium", Allium, "ALLIUM_API_KEY"),
    ("artemis", Artemis, "ARTEMIS_API_KEY"),
    ("blockworks", Blockworks, "BLOCKWORKS_API_KEY"),
    ("defillama", DefiLlama, "DEFILLAMA_API_KEY"),
    ("dune", Dune, "DUNE_API_KEY"),
    ("rwa", Rwa, "RWA_API_KEY"),
    ("stakewiz", Stakewiz, None),
    ("token_terminal", TokenTerminal, "TOKEN_TERMINAL_API_KEY"),
    ("validators_app", ValidatorsApp, "VALIDATORS_APP_API_TOKEN"),
]


def run_provider(
    provider: BaseProvider, start_date: str, end_date: str
) -> Dict[str, Any]:
    results: Dict[str, Any] = {}
    for metric in provider.METRIC_MAP:
        try:
            results[metric] = provider.fetch_rows(metric, start_date, end_date)
        except Exception as exc:  # noqa: BLE001
            results[metric] = {"error": str(exc)}
    return results


def build_methodology() -> List[Dict[str, str]]:
    records = []
    for cli_name, provider_cls, _ in PROVIDER_REGISTRY:
        for metric, config in provider_cls.METRIC_MAP.items():
            if not isinstance(config, dict) or "methodology" not in config:
                continue
            records.append(
                {
                    "provider": cli_name,
                    "metric": metric,
                    "description": config["methodology"],
                    "methodology_url": config.get("methodology_url", ""),
                }
            )
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run data providers and write fetched metrics to output/."
    )
    parser.add_argument(
        "--providers",
        help="Comma-separated provider names to run (e.g. artemis,dune). Defaults to all providers with a configured key.",
    )
    parser.add_argument(
        "--start",
        help=f"Start date YYYY-MM-DD. Defaults to today minus {LOOKBACK_DAYS - 1} days.",
    )
    parser.add_argument(
        "--end",
        help="End date YYYY-MM-DD. Defaults to today.",
    )
    parser.add_argument(
        "--methodology",
        action="store_true",
        help="Print methodology records for all providers and write output/methodology.json.",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    end_date = (
        datetime.date.fromisoformat(args.end) if args.end else datetime.date.today()
    )
    start_date = (
        datetime.date.fromisoformat(args.start)
        if args.start
        else end_date - datetime.timedelta(days=LOOKBACK_DAYS - 1)
    )

    requested = (
        {name.strip().lower() for name in args.providers.split(",")}
        if args.providers
        else None
    )

    if args.methodology:
        records = build_methodology()
        print(json.dumps(records, indent=2))
        return

    OUTPUT_DIR.mkdir(exist_ok=True)

    for cli_name, provider_cls, env_var in PROVIDER_REGISTRY:
        if requested is not None and cli_name not in requested:
            continue

        if env_var and not os.environ.get(env_var):
            print(f"Skipping {cli_name}: {env_var} not set")
            continue

        print(f"Running {cli_name}...")
        provider = provider_cls()
        results = run_provider(provider, start_date.isoformat(), end_date.isoformat())

        out_path = OUTPUT_DIR / f"{cli_name}.json"
        out_path.write_text(json.dumps(results, indent=2, default=str))
        print(f"  Wrote {out_path.name}")


if __name__ == "__main__":
    main()
