# OCPP Proxy Makefile
# Provides convenient commands for development and testing

.PHONY: help install test test-unit test-integration test-e2e test-coverage test-quick test-all lint format check clean build run docker-build docker-run

# Default target
help:
	@echo "OCPP Proxy Development Commands"
	@echo "==============================="
	@echo ""
	@echo "Setup:"
	@echo "  install     Install dependencies"
	@echo "  install-dev Install development dependencies"
	@echo ""
	@echo "Testing:"
	@echo "  test        Run all tests with coverage"
	@echo "  test-unit   Run unit tests only"
	@echo "  test-integration Run integration tests only"
	@echo "  test-e2e    Run end-to-end tests only"
	@echo "  test-coverage Generate coverage report"
	@echo "  test-quick  Run quick test suite (unit tests)"
	@echo "  test-all    Run complete test suite"
	@echo ""
	@echo "Code Quality:"
	@echo "  lint        Run linting (when configured)"
	@echo "  format      Format code (when configured)"
	@echo "  check       Run all quality checks"
	@echo ""
	@echo "Development:"
	@echo "  run         Run the application"
	@echo "  clean       Clean temporary files"
	@echo ""
	@echo "Docker:"
	@echo "  docker-build Build Docker image"
	@echo "  docker-run  Run in Docker container"

# Installation targets
install:
	poetry install --only=main

install-dev:
	poetry install

# Testing targets
test:
	poetry run python run_tests.py

test-unit:
	poetry run python run_tests.py --unit

test-integration:
	poetry run python run_tests.py --integration

test-e2e:
	poetry run python run_tests.py --e2e

test-coverage:
	poetry run python run_tests.py --coverage-html

test-quick:
	poetry run pytest tests/ -m "unit" --cov=src/ocpp_proxy --cov-report=term-missing -v

test-all:
	poetry run pytest tests/ --cov=src/ocpp_proxy --cov-report=term-missing --cov-report=html:htmlcov -v

# Code quality targets (placeholders for when tools are configured)
lint:
	@echo "Linting not yet configured. Add flake8, pylint, or similar to requirements.txt"
	@echo "Example: flake8 src/ tests/"

format:
	@echo "Code formatting not yet configured. Add black, autopep8, or similar to requirements.txt"
	@echo "Example: black src/ tests/"

check: lint
	@echo "Running all quality checks..."
	poetry run python run_tests.py --unit

# Development targets
run:
	poetry run python -m ocpp_proxy.main

clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf .pytest_cache/
	rm -rf build/
	rm -rf dist/
	rm -rf poetry.lock

# Docker targets
docker-build:
	docker build -t ocpp-proxy .

docker-run:
	docker run -p 9000:9000 ocpp-proxy

# Development helpers
deps-check:
	pip list --outdated

deps-tree:
	pip show --verbose ev-charger-proxy || echo "Package not installed in development mode"

# Test database management
test-db-clean:
	rm -f tests/test_*.db
	rm -f usage_log.db

# Coverage targets
coverage-open:
	@if [ -f htmlcov/index.html ]; then \
		echo "Opening coverage report..."; \
		python -m webbrowser htmlcov/index.html; \
	else \
		echo "No coverage report found. Run 'make test-coverage' first."; \
	fi

# Continuous integration simulation
ci:
	@echo "Running CI pipeline simulation..."
	make clean
	make install
	make test-all
	@echo "CI pipeline completed successfully!"

# Development setup
dev-setup:
	@echo "Setting up development environment..."
	@echo "Installing Poetry if not already available..."
	@which poetry || curl -sSL https://install.python-poetry.org | python3 -
	poetry install
	@echo "Development environment ready!"
	@echo "Run 'make test' to verify everything works."