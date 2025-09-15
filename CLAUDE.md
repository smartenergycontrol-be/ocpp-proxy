# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

This project uses Poetry for dependency management and Make for development commands:

```bash
# Setup
poetry install              # Install production dependencies
make install-dev           # Install development dependencies

# Testing
make test                  # Run full test suite with coverage
make test-unit             # Unit tests only
make test-integration      # Integration tests only
make test-e2e             # End-to-end tests only
make test-quick           # Quick unit tests
python run_tests.py       # Custom test runner with options

# Code Quality
make lint                 # Run ruff + mypy checks
make lint-fix            # Auto-fix linting issues
make format              # Format code with ruff
make type-check          # Run mypy type checking
make check              # All quality checks

# Development
make run                 # Start the application
poetry run python -m ocpp_proxy.main  # Direct execution
make clean              # Clean temporary files

# Docker
make docker-build       # Build container
make docker-run         # Run in container
```

## Architecture Overview

OCPP Proxy is a WebSocket-based proxy server that enables intelligent EV charger sharing between multiple backend services while maintaining homeowner control.

### Core Components

- **`main.py`**: HTTP server, WebSocket handlers, REST API endpoints
- **`charge_point_base.py`**: Abstract base class providing version-agnostic OCPP interface
- **`charge_point_v16.py`/`charge_point_v201.py`**: OCPP 1.6 and 2.0.1 protocol implementations
- **`charge_point_factory.py`**: Creates appropriate ChargePoint instances based on version detection
- **`backend_manager.py`**: Controls backend arbitration and manages single active control lock
- **`ocpp_service_manager.py`**: Manages outbound connections to OCPP services
- **`ha_bridge.py`**: Home Assistant integration for monitoring and overrides
- **`logger.py`**: Session tracking and SQLite persistence
- **`config.py`**: YAML configuration management

### Key Architecture Patterns

1. **Version Abstraction**: `ChargePointBase` provides unified interface; concrete classes handle protocol specifics
2. **Control Arbitration**: Only one backend can control the charger at a time via `BackendManager`
3. **Dual Connection Types**:
   - Inbound WebSocket backends (`/backend?id=backend_id`)
   - Outbound OCPP service connections (configured in YAML)
4. **Event Broadcasting**: All backends receive real-time charger events regardless of control ownership

### Protocol Version Detection

Auto-detection occurs through:
- WebSocket subprotocols (`ocpp1.6`, `ocpp2.0.1`)
- HTTP headers (`Sec-WebSocket-Protocol`, `X-OCPP-Version`)
- URL query parameters (`?version=2.0.1`)
- URL path patterns (`/charger/v2.0.1`)

### WebSocket Endpoints

- **`/charger`**: EV charger connection (CSMS role) with auto-detection
- **`/backend?id=backend_id`**: Backend service connections with custom control protocol

### Testing Requirements

- Minimum 85% test coverage (enforced in `pyproject.toml`)
- Test markers: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.e2e`
- Custom test runner at `run_tests.py` supports targeted test execution
- Use `pytest-asyncio` for async test support

### Code Quality Tools

- **Ruff**: Linting and formatting (configured in `pyproject.toml`)
- **MyPy**: Static type checking with strict settings
- **Pre-commit**: Configured for code quality enforcement
- Line length: 100 characters
- Python version: >=3.11

### Configuration

Configuration loaded from YAML files with schema validation. Key sections:
- OCPP protocol settings and version preferences
- Backend management (allowlists, rate limiting)
- Home Assistant integration settings
- Outbound OCPP service definitions with authentication

### Home Assistant Integration

Integrates with Home Assistant for:
- Presence-based charging control
- Manual overrides via input booleans
- Real-time status monitoring
- Configuration management through add-on UI