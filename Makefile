.PHONY: install check lint types test fmt collect excel clean

PY := .venv/bin/python
PIP := .venv/bin/pip

install:
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

check: lint types test

lint:
	.venv/bin/ruff check scpi tests

fmt:
	.venv/bin/ruff format scpi tests
	.venv/bin/ruff check --fix scpi tests

types:
	.venv/bin/mypy scpi

test:
	.venv/bin/pytest

# Collecte une SCPI (ex: make collect SCPI=corum_origin)
collect:
	$(PY) -m scpi.cli collect $(SCPI)

excel:
	$(PY) -m scpi.cli excel

# Application web locale : http://127.0.0.1:8000
web:
	$(PY) -m uvicorn scpi.web.app:app --host 127.0.0.1 --port 8000 --reload

clean:
	rm -rf .venv .mypy_cache .ruff_cache .pytest_cache
