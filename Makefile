VENV := .venv
VENV_BIN := $(VENV)/bin
PIP := $(VENV_BIN)/pip
PYTEST := $(VENV_BIN)/pytest
RUFF := $(VENV_BIN)/ruff
BLACK := $(VENV_BIN)/black

.PHONY: venv deps lint lint-fix test test-integration

venv:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip

deps: venv
	$(PIP) install -r requirements.txt

lint:
	$(RUFF) check .
	$(BLACK) --check .

lint-fix:
	$(RUFF) check . --fix
	$(BLACK) .

test:
	$(PYTEST) -q -m "not integration"

test-integration:
	$(PYTEST) -q
