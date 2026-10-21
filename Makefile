.PHONY: help dev start seed test test-v lint format format-check verify clean

help:
	@echo "RoomLoop Service — Available Commands:"
	@echo "  make dev          - Run development server (uv run python -m roomloop.server)"
	@echo "  make start        - Run production server"
	@echo "  make seed         - Run database seeder (uv run python -m roomloop.seeding)"
	@echo "  make lint         - Run ruff linter check"
	@echo "  make format       - Auto-format code with ruff"
	@echo "  make format-check - Check code formatting with ruff"
	@echo "  make test         - Run pytest test suite"
	@echo "  make test-v       - Run pytest in verbose mode"
	@echo "  make verify       - Verify code quality (linter, format check, and tests)"
	@echo "  make clean        - Remove build artifacts, cache, and test databases"

dev:
	uv run python -m roomloop.server

start:
	uv run python -m roomloop.server

seed:
	uv run python -m roomloop.seeding

lint:
	uv run ruff check src tests

format:
	uv run ruff format src tests

format-check:
	uv run ruff format --check src tests

test:
	uv run pytest

test-v:
	uv run pytest -v

verify: lint format-check test

clean:
	rm -rf .pytest_cache __pycache__ src/**/__pycache__ tests/__pycache__ *.db*
