import pytest
import asyncio
import datetime
from unittest.mock import Mock, AsyncMock, patch
from aiohttp import web

from src.ocpp_proxy.backend_manager import BackendManager
from src.ocpp_proxy.config import Config


class TestBackendManager:
    """Unit tests for BackendManager class."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock config object."""
        config = Mock(spec=Config)
        config.allow_shared_charging = True
        config.preferred_provider = 'preferred_provider'
        config.disallowed_providers = ['blocked_provider']
        config.allowed_providers = []
        config.presence_sensor = ''
        config.override_input_boolean = ''
        config.rate_limit_seconds = 10
        return config

    @pytest.fixture
    def mock_ha_bridge(self):
        """Create a mock Home Assistant bridge."""
        ha_bridge = Mock()
        ha_bridge.get_state = AsyncMock(return_value={'state': 'off'})
        return ha_bridge

    @pytest.fixture
    def mock_ocpp_service_manager(self):
        """Create a mock OCPP service manager."""
        manager = Mock()
        manager.broadcast_event_to_services = Mock()
        manager.get_service_status = Mock(return_value={'service1': {'connected': True}})
        return manager

    @pytest.fixture
    def backend_manager(self, mock_config, mock_ha_bridge, mock_ocpp_service_manager):
        """Create a BackendManager instance for testing."""
        return BackendManager(mock_config, mock_ha_bridge, mock_ocpp_service_manager)

    @pytest.mark.unit
    def test_initialization(self, backend_manager, mock_config, mock_ha_bridge, mock_ocpp_service_manager):
        """Test BackendManager initialization."""
        assert backend_manager.config == mock_config
        assert backend_manager.ha == mock_ha_bridge
        assert backend_manager.ocpp_service_manager == mock_ocpp_service_manager
        assert backend_manager.subscribers == {}
        assert backend_manager._lock_owner is None
        assert backend_manager._lock_timer is None
        assert backend_manager._last_request_time == {}
        assert backend_manager._app is None

    @pytest.mark.unit
    def test_subscribe_and_unsubscribe(self, backend_manager):
        """Test subscribing and unsubscribing backends."""
        mock_ws = Mock(spec=web.WebSocketResponse)
        
        # Test subscribe
        backend_manager.subscribe('test_backend', mock_ws)
        assert 'test_backend' in backend_manager.subscribers
        assert backend_manager.subscribers['test_backend'] == mock_ws
        
        # Test unsubscribe
        backend_manager.unsubscribe('test_backend')
        assert 'test_backend' not in backend_manager.subscribers

    @pytest.mark.unit
    def test_unsubscribe_with_lock_owner(self, backend_manager):
        """Test unsubscribing backend that owns the lock."""
        mock_ws = Mock(spec=web.WebSocketResponse)
        backend_manager.subscribe('test_backend', mock_ws)
        backend_manager._lock_owner = 'test_backend'
        
        backend_manager.unsubscribe('test_backend')
        
        assert 'test_backend' not in backend_manager.subscribers
        assert backend_manager._lock_owner is None

    @pytest.mark.unit
    def test_broadcast_event_websocket_only(self, backend_manager):
        """Test broadcasting events to WebSocket subscribers only."""
        mock_ws1 = Mock(spec=web.WebSocketResponse)
        mock_ws2 = Mock(spec=web.WebSocketResponse)
        mock_ws1.send_json = Mock()
        mock_ws2.send_json = Mock()
        
        backend_manager.subscribe('backend1', mock_ws1)
        backend_manager.subscribe('backend2', mock_ws2)
        
        event = {'type': 'test_event', 'data': 'test_data'}
        backend_manager.broadcast_event(event)
        
        mock_ws1.send_json.assert_called_once_with({'type': 'event', 'type': 'test_event', 'data': 'test_data'})
        mock_ws2.send_json.assert_called_once_with({'type': 'event', 'type': 'test_event', 'data': 'test_data'})

    @pytest.mark.unit
    def test_broadcast_event_with_ocpp_services(self, backend_manager):
        """Test broadcasting events to both WebSocket and OCPP services."""
        mock_ws = Mock(spec=web.WebSocketResponse)
        mock_ws.send_json = Mock()
        backend_manager.subscribe('backend1', mock_ws)
        
        event = {'type': 'test_event', 'data': 'test_data'}
        backend_manager.broadcast_event(event)
        
        mock_ws.send_json.assert_called_once()
        backend_manager.ocpp_service_manager.broadcast_event_to_services.assert_called_once_with(event)

    @pytest.mark.unit
    def test_broadcast_event_websocket_failure(self, backend_manager):
        """Test broadcasting events when WebSocket fails."""
        mock_ws = Mock(spec=web.WebSocketResponse)
        mock_ws.send_json = Mock(side_effect=Exception("WebSocket error"))
        backend_manager.subscribe('backend1', mock_ws)
        
        event = {'type': 'test_event'}
        # Should not raise exception
        backend_manager.broadcast_event(event)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_request_control_success(self, backend_manager):
        """Test successful control request."""
        result = await backend_manager.request_control('test_backend')
        
        assert result == True
        assert backend_manager._lock_owner == 'test_backend'
        assert backend_manager._lock_timer is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_request_control_rate_limited(self, backend_manager):
        """Test control request with rate limiting."""
        # First request should succeed
        result1 = await backend_manager.request_control('test_backend')
        assert result1 == True
        
        # Immediately subsequent request should be rate limited
        result2 = await backend_manager.request_control('test_backend')
        assert result2 == False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_request_control_shared_charging_disabled(self, backend_manager):
        """Test control request when shared charging is disabled."""
        backend_manager.config.allow_shared_charging = False
        
        result = await backend_manager.request_control('test_backend')
        assert result == False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_request_control_disallowed_provider(self, backend_manager):
        """Test control request with disallowed provider."""
        result = await backend_manager.request_control('blocked_provider')
        assert result == False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_request_control_allowed_providers_list(self, backend_manager):
        """Test control request with allowed providers list."""
        backend_manager.config.allowed_providers = ['allowed_provider']
        
        # Should succeed for allowed provider
        result1 = await backend_manager.request_control('allowed_provider')
        assert result1 == True
        
        backend_manager.release_control()
        
        # Should fail for non-allowed provider
        result2 = await backend_manager.request_control('not_allowed_provider')
        assert result2 == False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_request_control_ocpp_service_bypass(self, backend_manager):
        """Test that OCPP services bypass provider filtering."""
        backend_manager.config.disallowed_providers = ['ocpp_service_test']
        backend_manager.config.allowed_providers = ['some_other_provider']
        
        # OCPP service should bypass filtering
        result = await backend_manager.request_control('ocpp_service_test')
        assert result == True

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_request_control_ha_override_boolean(self, backend_manager):
        """Test control request with HA override boolean."""
        backend_manager.config.override_input_boolean = 'input_boolean.override'
        
        # Mock HA returning 'off' state
        backend_manager.ha.get_state.return_value = {'state': 'off'}
        result = await backend_manager.request_control('test_backend')
        assert result == False
        
        # Mock HA returning 'on' state
        backend_manager.ha.get_state.return_value = {'state': 'on'}
        result = await backend_manager.request_control('test_backend')
        assert result == True

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_request_control_presence_sensor(self, backend_manager):
        """Test control request with presence sensor."""
        backend_manager.config.presence_sensor = 'binary_sensor.presence'
        
        # Mock presence sensor returning 'home'
        backend_manager.ha.get_state.return_value = {'state': 'home'}
        result = await backend_manager.request_control('test_backend')
        assert result == False
        
        # Mock presence sensor returning 'away'
        backend_manager.ha.get_state.return_value = {'state': 'away'}
        result = await backend_manager.request_control('test_backend')
        assert result == True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_request_control_preferred_provider_preemption(self, backend_manager):
        """Test preferred provider preemption."""
        # First backend gets control
        result1 = await backend_manager.request_control('regular_backend')
        assert result1 == True
        assert backend_manager._lock_owner == 'regular_backend'
        
        # Preferred provider should preempt
        result2 = await backend_manager.request_control('preferred_provider')
        assert result2 == True
        assert backend_manager._lock_owner == 'preferred_provider'

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_request_control_already_owned(self, backend_manager):
        """Test control request when already owned by another backend."""
        # First backend gets control
        result1 = await backend_manager.request_control('backend1')
        assert result1 == True
        
        # Second backend should fail
        result2 = await backend_manager.request_control('backend2')
        assert result2 == False

    @pytest.mark.unit
    def test_release_control(self, backend_manager):
        """Test releasing control."""
        backend_manager._lock_owner = 'test_backend'
        mock_timer = Mock()
        backend_manager._lock_timer = mock_timer
        
        backend_manager.release_control()
        
        assert backend_manager._lock_owner is None
        mock_timer.cancel.assert_called_once()
        assert backend_manager._lock_timer is None

    @pytest.mark.unit
    def test_release_control_no_timer(self, backend_manager):
        """Test releasing control when no timer is set."""
        backend_manager._lock_owner = 'test_backend'
        backend_manager._lock_timer = None
        
        # Should not raise exception
        backend_manager.release_control()
        assert backend_manager._lock_owner is None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_lock_timeout(self, backend_manager):
        """Test lock timeout mechanism."""
        backend_manager._lock_owner = 'test_backend'
        
        # Create a real task for testing
        backend_manager._start_lock_timer(0.1)  # 100ms timeout
        
        # Wait for timeout
        await asyncio.sleep(0.2)
        
        # Lock should be released
        assert backend_manager._lock_owner is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_start_lock_timer(self, backend_manager):
        """Test starting lock timer."""
        backend_manager._start_lock_timer(60)
        assert backend_manager._lock_timer is not None
        
        # Starting again should cancel previous timer
        old_timer = backend_manager._lock_timer
        backend_manager._start_lock_timer(30)
        
        # Allow a small delay for the cancellation to take effect
        await asyncio.sleep(0.01)
        assert old_timer.cancelled()
        assert backend_manager._lock_timer is not None

    @pytest.mark.unit
    def test_set_app_reference(self, backend_manager):
        """Test setting app reference."""
        mock_app = Mock()
        backend_manager.set_app_reference(mock_app)
        assert backend_manager._app == mock_app

    @pytest.mark.unit
    def test_get_backend_status(self, backend_manager):
        """Test getting backend status."""
        mock_ws = Mock(spec=web.WebSocketResponse)
        backend_manager.subscribe('test_backend', mock_ws)
        backend_manager._lock_owner = 'test_backend'
        
        status = backend_manager.get_backend_status()
        
        assert status['websocket_backends'] == ['test_backend']
        assert status['lock_owner'] == 'test_backend'
        assert status['ocpp_services'] == {'service1': {'connected': True}}

    @pytest.mark.unit
    def test_get_backend_status_no_ocpp_manager(self, mock_config):
        """Test getting backend status without OCPP service manager."""
        backend_manager = BackendManager(mock_config)
        
        status = backend_manager.get_backend_status()
        
        assert status['websocket_backends'] == []
        assert status['lock_owner'] is None
        assert status['ocpp_services'] == {}

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_request_control_rate_limit_timing(self, backend_manager):
        """Test rate limiting timing accuracy."""
        backend_manager.config.rate_limit_seconds = 1
        
        # First request
        result1 = await backend_manager.request_control('test_backend')
        assert result1 == True
        
        backend_manager.release_control()
        
        # Immediate second request should be blocked
        result2 = await backend_manager.request_control('test_backend')
        assert result2 == False
        
        # Wait for rate limit to expire
        await asyncio.sleep(1.1)
        
        # Third request should succeed
        result3 = await backend_manager.request_control('test_backend')
        assert result3 == True

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_request_control_ha_bridge_exceptions(self, backend_manager):
        """Test handling of HA bridge exceptions."""
        backend_manager.config.override_input_boolean = 'input_boolean.override'
        backend_manager.ha.get_state.side_effect = Exception("HA connection error")
        
        # Should continue processing despite HA error
        result = await backend_manager.request_control('test_backend')
        assert result == True

    @pytest.mark.unit
    def test_multiple_subscribers(self, backend_manager):
        """Test managing multiple subscribers."""
        mock_ws1 = Mock(spec=web.WebSocketResponse)
        mock_ws2 = Mock(spec=web.WebSocketResponse)
        mock_ws3 = Mock(spec=web.WebSocketResponse)
        
        backend_manager.subscribe('backend1', mock_ws1)
        backend_manager.subscribe('backend2', mock_ws2)
        backend_manager.subscribe('backend3', mock_ws3)
        
        assert len(backend_manager.subscribers) == 3
        assert 'backend1' in backend_manager.subscribers
        assert 'backend2' in backend_manager.subscribers
        assert 'backend3' in backend_manager.subscribers

    @pytest.mark.unit
    def test_subscribe_replace_existing(self, backend_manager):
        """Test subscribing with same backend ID replaces existing."""
        mock_ws1 = Mock(spec=web.WebSocketResponse)
        mock_ws2 = Mock(spec=web.WebSocketResponse)
        
        backend_manager.subscribe('backend1', mock_ws1)
        backend_manager.subscribe('backend1', mock_ws2)
        
        assert len(backend_manager.subscribers) == 1
        assert backend_manager.subscribers['backend1'] == mock_ws2

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_concurrent_control_requests(self, backend_manager):
        """Test concurrent control requests."""
        # Create multiple concurrent requests
        tasks = []
        for i in range(5):
            task = asyncio.create_task(backend_manager.request_control(f'backend{i}'))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        # Only one should succeed
        successful_requests = sum(1 for result in results if result)
        assert successful_requests == 1
        
        # One backend should own the lock
        assert backend_manager._lock_owner is not None
        assert backend_manager._lock_owner.startswith('backend')

    @pytest.mark.unit
    def test_broadcast_event_no_ocpp_manager(self, mock_config):
        """Test broadcasting events without OCPP service manager."""
        backend_manager = BackendManager(mock_config)
        mock_ws = Mock(spec=web.WebSocketResponse)
        mock_ws.send_json = Mock()
        backend_manager.subscribe('backend1', mock_ws)
        
        event = {'type': 'test_event'}
        backend_manager.broadcast_event(event)
        
        mock_ws.send_json.assert_called_once()
        # Should not raise exception even without OCPP manager