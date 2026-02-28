.PHONY: help setup run run-cli serve demo-webhook test test-live check verify

help:
	@echo "Available commands:"
	@echo "  make setup      - install runtime + dev dependencies into .venv"
	@echo "  make run        - start the real webhook API (main.py) on :8000"
	@echo "  make run-cli    - listen for Sentry webhooks + render live CLI orchestration"
	@echo "  make serve      - start the web dashboard on http://127.0.0.1:8000"
	@echo "  make demo-webhook - send a sample webhook and poll for completion"
	@echo "  make test       - run offline tests (deterministic, no network)"
	@echo "  make test-live  - run live API tests (requires network + provider API key)"
	@echo "  make check      - run static syntax/import compilation check"
	@echo "  make verify     - run check + test"

setup:
	uv sync --dev

run:
	@echo "Starting Alpha SRE webhook API at http://127.0.0.1:8000"
	@echo "Tip: in another terminal run 'make demo-webhook'"
	.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload

run-cli:
	@echo "Starting webhook listener with CLI live orchestration at http://127.0.0.1:8000"
	@echo "Point Sentry webhook to: <ngrok-url>/webhooks/sentry"
	ALPHA_CLI_WEBHOOK_MODE=true .venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000

serve:
	.venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000

demo-webhook:
	.venv/bin/python scripts/demo_webhook.py

test:
	.venv/bin/python -m pytest -q -m "not live"

test-live:
	.venv/bin/python -m pytest -q -m "live"

check:
	.venv/bin/python -m compileall -q .

verify: check test
