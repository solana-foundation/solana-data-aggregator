# Solana Data Aggregator

Collect and benchmark Solana on-chain metrics across multiple data providers.
This project standardizes provider responses into typed models with unit and integration tests.

## Backfill Requests 
Please create a ticket in [issues](https://github.com/solana-foundation/solana-data-aggregator/issues). 

Backflow requests are processed on the 1st of every month. 

Prefix the with `[Backfill]` indicating the following: 

* Provider
* Metric(s) and/or "All"
* Reason

## Requirements
- Python 3.12+
- `pip` and `venv`
- API keys for the providers you want to run (see `.env.example`)
  - `ZERION_API_KEY` enables the Zerion provider (free key at [dashboard.zerion.io](https://dashboard.zerion.io))

## Project Layout
- `metrics/`: typed metric models and metadata mapping
- `providers/`: provider interfaces (Allium, Artemis, Blockworks, DefiLlama, Dune, RWA, Stakewiz, TokenTerminal, ValidatorsApp, Zerion)
- `tests/unit/`: isolated provider and model behavior tests
- `tests/integration/`: live API integration tests
- `tests/conftest.py`: shared pytest fixtures and test setup
- `requirements.in`: direct Python dependencies
- `requirements.txt`: pinned lock file with transitive dependencies and hashes (generated)
- `Makefile`: setup, lint, format, and test commands
- `_output/`: local JSON output from `main.py` (git-ignored)

## Dependencies

Direct dependencies live in `requirements.in`. `requirements.txt` is generated from that file with [pip-tools](https://github.com/jazzband/pip-tools) and pins every transitive dependency with hashes for reproducible installs.

**Set up the virtual environment and install dependencies:**

```bash
make venv   # create .venv and upgrade pip
make deps   # install from requirements.txt (runs make venv if needed)
```

`make` targets use `.venv` automatically — you do not need to activate it for `make lint`, `make test`, or other Makefile commands.

**Update the lock file** after changing `requirements.in`:

```bash
pip install pip-tools
pip-compile requirements.in --output-file=requirements.txt --generate-hashes
```

## Quick Start
1. Set up Python dependencies:
   ```bash
   make deps
   ```
2. Configure environment variables:
   ```bash
   cp .env.example .env
   # Fill in whichever API keys you have
   ```
3. Run linting and tests:
   ```bash
   make lint
   make test
   make test-integration
   ```

## Test Run (main.py)

Fetch metrics from every provider that has a key set in `.env` and write results to `_output/`.

```bash
# Run all configured providers (last 7 days)
python main.py

# Single provider, single day
python main.py --providers token_terminal --start 2026-06-15 --end 2026-06-15

# Multiple providers, custom date range
python main.py --providers artemis,dune --start 2026-06-09 --end 2026-06-15
```

Output files are written to `_output/<provider>.json`, with all metrics for that provider in a single file. Providers without a configured API key are skipped automatically.

`--methodology` prints a JSON list of `{"provider", "metric", "description", "methodology_url"}` records for every metric with a methodology defined. Metrics without one are skipped.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for the full text.
