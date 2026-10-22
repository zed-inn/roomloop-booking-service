.PHONY: help setup ensure-env dev start seed seed-rich test test-v lint format format-check verify clean load-generate load-10k load-100k load-1m

help:
	@echo "RoomLoop Service — Available Commands:"
	@echo "  make setup         - Automated 1-step onboarding (config/.env, seed rooms, payloads)"
	@echo "  make dev           - Run development server (uv run python -m roomloop.server)"
	@echo "  make start         - Run production server"
	@echo "  make seed          - Run database seeder (prototype rooms)"
	@echo "  make seed-rich     - Seed prototype rooms plus sample recurring/single bookings"
	@echo "  make lint          - Run ruff linter check"
	@echo "  make format        - Auto-format code with ruff"
	@echo "  make format-check  - Check code formatting with ruff"
	@echo "  make test          - Run pytest test suite"
	@echo "  make test-v        - Run pytest in verbose mode"
	@echo "  make verify        - Verify code quality (linter, format check, and tests)"
	@echo "  make load-generate - Generate 5,000 diverse payload templates for k6"
	@echo "  make load-10k      - Run 10k request k6 benchmark"
	@echo "  make load-100k     - Run 100k request k6 stress benchmark"
	@echo "  make load-1m       - Run 1M request k6 high-volume benchmark"
	@echo "  make load-py-10k   - Run 10k request pure Python async benchmark (no k6 required)"
	@echo "  make clean         - Remove build artifacts, cache, and test databases"

ensure-env:
	@mkdir -p config
	@test -f config/.env || (cp .env.example config/.env && echo "==> [setup] Created config/.env from .env.example")

setup: ensure-env seed ensure-payloads
	@echo ""
	@echo "================================================================================"
	@echo " RoomLoop Setup Complete!"
	@echo " • Environment configured at config/.env"
	@echo " • Prototype rooms seeded (IDs 3, 4, 9, 17)"
	@echo " • Load test payload templates ready"
	@echo "================================================================================"
	@echo " To start the service, run:"
	@echo "   make dev   (or: make start)"
	@echo "================================================================================"
	@echo ""

dev: ensure-env
	ENVIRONMENT=development uv run python -m roomloop.server

start: ensure-env
	ENVIRONMENT=production uv run python -m roomloop.server

seed:
	uv run python -m roomloop.seeding

seed-rich:
	RICH_SEED=true uv run python -m roomloop.seeding

lint:
	uv run ruff check src tests

format:
	uv run ruff format src tests

format-check:
	uv run ruff format --check src tests

test:
	ENVIRONMENT=test uv run pytest

test-v:
	ENVIRONMENT=test uv run pytest -v

verify: lint format-check test

load-generate:
	uv run python tests/load/generate_payloads.py

k6-info:
	@echo ""
	@echo "================================================================================"
	@echo " How to install k6 on your environment:"
	@echo ""
	@echo " • Linux (Standalone binary, no root / no sudo required):"
	@echo "     mkdir -p ~/.local/bin"
	@echo "     curl -sSL https://github.com/grafana/k6/releases/download/v0.56.0/k6-v0.56.0-linux-amd64.tar.gz | tar -xz -C ~/.local/bin/ --strip-components=1 k6-v0.56.0-linux-amd64/k6"
	@echo ""
	@echo " • Ubuntu / Debian:"
	@echo "     sudo gpg -k && sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D34EE24C"
	@echo "     echo \"deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main\" | sudo tee /etc/apt/sources.list.d/k6.list"
	@echo "     sudo apt-get update && sudo apt-get install k6"
	@echo ""
	@echo " • macOS (Homebrew):"
	@echo "     brew install k6"
	@echo ""
	@echo " • Windows (winget or chocolatey):"
	@echo "     winget install k6 --source winget"
	@echo "     # or: choco install k6"
	@echo ""
	@echo " • Docker (no local install):"
	@echo "     docker run --rm -i --network=host -v $$(pwd):/app -w /app grafana/k6 run -e TIER=10k tests/load/k6_load_test.js"
	@echo "================================================================================"
	@echo ""

# Detect configured port from config/.env or .env, defaulting to 8000
DETECTED_PORT := $(shell grep -h -E '^PORT=' config/.env .env 2>/dev/null | head -n 1 | cut -d '=' -f 2 | tr -d ' "' || echo 8000)
PORT ?= $(if $(DETECTED_PORT),$(DETECTED_PORT),8000)
TARGET_URL ?= http://127.0.0.1:$(PORT)

ensure-payloads:
	@test -f tests/load/payloads.json || uv run python tests/load/generate_payloads.py

check-server:
	@curl -s -f $(TARGET_URL)/health >/dev/null 2>&1 || ( \
		echo ""; \
		echo "================================================================================"; \
		echo " [!] RoomLoop server is not running or unreachable at: $(TARGET_URL)"; \
		echo "================================================================================"; \
		echo " Please start the server in another terminal first:"; \
		echo "   make dev"; \
		echo "   (or: make start)"; \
		echo ""; \
		echo " Or if your server runs on a custom port/host, pass TARGET_URL:"; \
		echo "   TARGET_URL=http://localhost:8095 make load-10k"; \
		echo "================================================================================"; \
		echo ""; \
		exit 1 \
	)

load-10k: ensure-payloads check-server
	@if command -v k6 >/dev/null 2>&1; then \
		echo "==> k6 binary detected. Executing k6 load test (10,000 requests)..."; \
		TARGET_URL=$(TARGET_URL) k6 run -e TARGET_URL=$(TARGET_URL) -e TIER=10k tests/load/k6_load_test.js; \
	else \
		echo "==> k6 binary not found in PATH. Seamlessly running pure Python async load test (10,000 requests)..."; \
		TARGET_URL=$(TARGET_URL) COUNT=10000 uv run python tests/load/python_load_test.py; \
	fi

load-100k: ensure-payloads check-server
	@if command -v k6 >/dev/null 2>&1; then \
		echo "==> k6 binary detected. Executing k6 load test (100,000 requests)..."; \
		TARGET_URL=$(TARGET_URL) k6 run -e TARGET_URL=$(TARGET_URL) -e TIER=100k tests/load/k6_load_test.js; \
	else \
		echo "==> k6 binary not found in PATH. Seamlessly running pure Python async load test (100,000 requests)..."; \
		TARGET_URL=$(TARGET_URL) COUNT=100000 uv run python tests/load/python_load_test.py; \
	fi

load-1m: ensure-payloads check-server
	@if command -v k6 >/dev/null 2>&1; then \
		echo "==> k6 binary detected. Executing k6 load test (1,000,000 requests)..."; \
		TARGET_URL=$(TARGET_URL) k6 run -e TARGET_URL=$(TARGET_URL) -e TIER=1m tests/load/k6_load_test.js; \
	else \
		echo "==> k6 binary not found in PATH. Seamlessly running pure Python async load test (1,000,000 requests)..."; \
		TARGET_URL=$(TARGET_URL) COUNT=1000000 uv run python tests/load/python_load_test.py; \
	fi

load-py-10k: ensure-payloads check-server
	TARGET_URL=$(TARGET_URL) COUNT=10000 uv run python tests/load/python_load_test.py

load-py-100k: ensure-payloads check-server
	TARGET_URL=$(TARGET_URL) COUNT=100000 uv run python tests/load/python_load_test.py

clean:
	rm -rf .pytest_cache __pycache__ **/__pycache__/ tests/__pycache__ *.db*
