.PHONY: help setup run serve test test-live check verify

help:
	@echo "Available commands:"
	@echo "  make setup      - install runtime + dev dependencies into .venv"
	@echo "  make run        - run the CLI entrypoint"
	@echo "  make serve      - start the web dashboard on http://127.0.0.1:8000"
	@echo "  make test       - run offline tests (deterministic, no network)"
	@echo "  make test-live  - run live API tests (requires network and OPENROUTER_API_KEY)"
	@echo "  make check      - run static syntax/import compilation check"
	@echo "  make verify     - run check + test"

setup:
	uv sync --dev

run:
	.venv/bin/python main.py

serve:
	.venv/bin/python server.py

test:
	.venv/bin/python -m pytest -q -m "not live"

test-live:
	.venv/bin/python -m pytest -q -m "live"

check:
	.venv/bin/python -m compileall -q .

verify: check test
