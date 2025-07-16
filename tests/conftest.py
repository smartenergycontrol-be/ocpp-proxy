"""
Pytest configuration and shared fixtures.
"""

import os
import sqlite3
import tempfile
from unittest.mock import AsyncMock, Mock

import pytest

from src.ocpp_proxy.backend_manager import BackendManager
from src.ocpp_proxy.config import Config
from src.ocpp_proxy.ha_bridge import HABridge
from src.ocpp_proxy.logger import EventLogger


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def temp_config_file():
    """Create a temporary configuration file."""
    config_data = {
        "allow_shared_charging": True,
        "preferred_provider": "test_provider",
        "rate_limit_seconds": 10,
        "ocpp_services": [],
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        import yaml

        yaml.dump(config_data, f)
        config_path = f.name

    yield config_path
    os.unlink(config_path)


@pytest.fixture
def mock_config():
    """Create a mock configuration object."""
    config = Mock(spec=Config)
    config.allow_shared_charging = True
    config.preferred_provider = "preferred_provider"
    config.blocked_providers = ["blocked_provider"]
    config.allowed_providers = []
    config.presence_sensor = ""
    config.override_input_boolean = ""
    config.rate_limit_seconds = 10
    config.ocpp_services = []
    return config


@pytest.fixture
def mock_ha_bridge():
    """Create a mock Home Assistant bridge."""
    ha_bridge = Mock(spec=HABridge)
    ha_bridge.get_state = AsyncMock(return_value={"state": "off"})
    ha_bridge.send_notification = AsyncMock()
    ha_bridge.close = AsyncMock()
    return ha_bridge


@pytest.fixture
def mock_event_logger():
    """Create a mock event logger."""
    logger = Mock(spec=EventLogger)
    logger.log_session = Mock()
    logger.get_sessions = Mock(return_value=[])
    logger.export_db = Mock(return_value="test.db")
    return logger


@pytest.fixture
def mock_backend_manager():
    """Create a mock backend manager."""
    manager = Mock(spec=BackendManager)
    manager.subscribe = Mock()
    manager.unsubscribe = Mock()
    manager.broadcast_event = Mock()
    manager.request_control = AsyncMock(return_value=True)
    manager.release_control = Mock()
    manager.get_backend_status = Mock(
        return_value={"websocket_backends": [], "lock_owner": None, "ocpp_services": {}}
    )
    manager._lock_owner = None
    return manager


@pytest.fixture
def event_logger(temp_db):
    """Create a real EventLogger instance for testing."""
    return EventLogger(temp_db)


@pytest.fixture
def sample_sessions_data():
    """Sample session data for testing."""
    return [
        {
            "timestamp": "2023-01-01T12:00:00Z",
            "backend_id": "backend1",
            "duration_s": 3600.0,
            "energy_kwh": 25.0,
            "revenue": 5.0,
        },
        {
            "timestamp": "2023-01-01T13:30:00Z",
            "backend_id": "backend2",
            "duration_s": 1800.0,
            "energy_kwh": 12.5,
            "revenue": 2.5,
        },
        {
            "timestamp": "2023-01-01T15:00:00Z",
            "backend_id": "backend3",
            "duration_s": 7200.0,
            "energy_kwh": 50.0,
            "revenue": 10.0,
        },
    ]


@pytest.fixture
def sample_ocpp_services_config():
    """Sample OCPP services configuration."""
    return [
        {
            "id": "service1",
            "url": "wss://service1.com/ocpp",
            "auth_type": "token",
            "token": "token123",
            "enabled": True,
        },
        {
            "id": "service2",
            "url": "wss://service2.com/ocpp",
            "auth_type": "basic",
            "username": "user",
            "password": "pass",
            "enabled": True,
        },
        {"id": "service3", "url": "wss://service3.com/ocpp", "auth_type": "none", "enabled": False},
    ]


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket connection."""
    ws = Mock()
    ws.send_json = AsyncMock()
    ws.receive_json = AsyncMock()
    ws.send = AsyncMock()
    ws.recv = AsyncMock()
    ws.close = AsyncMock()
    ws.closed = False
    return ws


@pytest.fixture
def mock_charge_point():
    """Create a mock charge point."""
    cp = Mock()
    cp.call_remote_start_transaction = AsyncMock()
    cp.call_remote_stop_transaction = AsyncMock()
    cp.call_boot_notification = AsyncMock()
    cp.call_heartbeat = AsyncMock()
    cp.call_status_notification = AsyncMock()
    cp.call_meter_values = AsyncMock()
    cp.call_start_transaction = AsyncMock()
    cp.call_stop_transaction = AsyncMock()
    return cp


@pytest.fixture(autouse=True)
def clean_environment():
    """Clean environment variables before each test."""
    # Store original values
    original_env = {}
    env_vars = ["HA_URL", "HA_TOKEN", "PORT", "LOG_DB_PATH", "ADDON_CONFIG_FILE"]

    for var in env_vars:
        if var in os.environ:
            original_env[var] = os.environ[var]
            del os.environ[var]

    yield

    # Restore original values
    for var, value in original_env.items():
        os.environ[var] = value


@pytest.fixture
def mock_ocpp_service_manager():
    """Create a mock OCPP service manager."""
    manager = Mock()
    manager.start_services = AsyncMock()
    manager.stop_all_services = AsyncMock()
    manager.connect_service = AsyncMock()
    manager.disconnect_service = AsyncMock()
    manager.broadcast_event_to_services = Mock()
    manager.get_service_status = Mock(return_value={})
    manager.services = {}
    return manager


# Markers for different test types
def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "unit: marks tests as unit tests")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "e2e: marks tests as end-to-end tests")
    config.addinivalue_line("markers", "slow: marks tests as slow running")


# Async test configuration
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    import asyncio

    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Database fixtures for testing
@pytest.fixture
def in_memory_db():
    """Create an in-memory SQLite database for testing."""
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def populated_db(temp_db, sample_sessions_data):
    """Create a database populated with sample data."""
    logger = EventLogger(temp_db)

    # Add sample sessions
    for session in sample_sessions_data:
        logger.log_session(
            session["backend_id"], session["duration_s"], session["energy_kwh"], session["revenue"]
        )

    return logger
