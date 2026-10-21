.PHONY: help dev start seed test test-v lint format clean

# default target shows help
help:
	@echo "RoomLoop Service — Available Commands:"
	@echo "  make dev      - Run development server (uv run python -m roomloop.server)"
	@echo "  make start    - Run production server"
	@echo "  make seed     - Run database seeder (uv run python -m roomloop.seeding)"
	@echo "  make test     - Run pytest test suite"
	@echo "  make test-v   - Run pytest in verbose mode"
	@echo "  make clean    - Remove build artifacts, cache, and test databases"

dev:
	uv run python -m roomloop.server

start:
	uv run python -m roomloop.server

seed:
	uv run python -m roomloop.seeding

test:
	uv run pytest

test-v:
	uv run pytest -v

clean:
	rm -rf .pytest_cache __pycache__ src/**/__pycache__ tests/__pycache__ *.db*
