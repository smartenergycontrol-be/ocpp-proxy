import pytest
import json
from unittest.mock import Mock, AsyncMock, patch
from aiohttp import ClientSession, ClientWebSocketResponse
from aioresponses import aioresponses

from src.ev_charger_proxy.ha_bridge import HABridge


class TestHABridge:
    """Unit tests for HABridge class."""

    @pytest.fixture
    def ha_bridge(self):
        """Create an HABridge instance for testing."""
        return HABridge('http://homeassistant.local:8123', 'test_token')

    @pytest.fixture
    def ha_bridge_with_session(self):
        """Create an HABridge instance with initialized session for testing."""
        bridge = HABridge('http://homeassistant.local:8123', 'test_token')
        # Force session creation for testing
        bridge._session = ClientSession()
        return bridge

    @pytest.mark.asyncio
    async def test_initialization(self, ha_bridge):
        """Test HABridge initialization."""
        assert ha_bridge._url == 'http://homeassistant.local:8123'
        assert ha_bridge._token == 'test_token'
        assert ha_bridge._session is None  # Session is created lazily
        assert ha_bridge._ws is None
        
        # Test lazy session creation
        session = await ha_bridge._ensure_session()
        assert session is not None
        assert ha_bridge._session is session

    def test_initialization_url_strip(self):
        """Test HABridge initialization with trailing slash in URL."""
        ha_bridge = HABridge('http://homeassistant.local:8123/', 'test_token')
        assert ha_bridge._url == 'http://homeassistant.local:8123'

    @pytest.mark.asyncio
    async def test_connect_success(self, ha_bridge_with_session):
        """Test successful WebSocket connection to Home Assistant."""
        # Mock WebSocket connection
        mock_ws = Mock(spec=ClientWebSocketResponse)
        mock_ws.receive_json = AsyncMock()
        mock_ws.send_json = AsyncMock()
        
        # Mock the connection sequence
        mock_ws.receive_json.side_effect = [
            {'type': 'auth_required'},  # First response
            {'type': 'auth_ok'}         # Second response after auth
        ]
        
        with patch.object(ha_bridge_with_session, '_ensure_session', return_value=ha_bridge_with_session._session):
            with patch.object(ha_bridge_with_session._session, 'ws_connect', new_callable=AsyncMock, return_value=mock_ws):
                await ha_bridge_with_session.connect()
            
            # Should set WebSocket
            assert ha_bridge_with_session._ws == mock_ws
            
            # Should send auth message
            mock_ws.send_json.assert_called_once_with({
                'type': 'auth',
                'access_token': 'test_token'
            })

    @pytest.mark.asyncio
    async def test_connect_auth_failed(self, ha_bridge_with_session):
        """Test WebSocket connection with authentication failure."""
        # Mock WebSocket connection
        mock_ws = Mock(spec=ClientWebSocketResponse)
        mock_ws.receive_json = AsyncMock()
        mock_ws.send_json = AsyncMock()
        
        # Mock failed auth sequence
        mock_ws.receive_json.side_effect = [
            {'type': 'auth_required'},
            {'type': 'auth_invalid', 'message': 'Invalid access token'}
        ]
        
        with patch.object(ha_bridge_with_session, '_ensure_session', return_value=ha_bridge_with_session._session):
            with patch.object(ha_bridge_with_session._session, 'ws_connect', new_callable=AsyncMock, return_value=mock_ws):
                with pytest.raises(RuntimeError, match='Home Assistant authentication failed'):
                    await ha_bridge_with_session.connect()

    @pytest.mark.asyncio
    async def test_connect_with_correct_headers(self, ha_bridge_with_session):
        """Test WebSocket connection includes correct headers."""
        mock_ws = Mock(spec=ClientWebSocketResponse)
        mock_ws.receive_json = AsyncMock()
        mock_ws.send_json = AsyncMock()
        
        mock_ws.receive_json.side_effect = [
            {'type': 'auth_required'},
            {'type': 'auth_ok'}
        ]
        
        with patch.object(ha_bridge_with_session, '_ensure_session', return_value=ha_bridge_with_session._session):
            with patch.object(ha_bridge_with_session._session, 'ws_connect', new_callable=AsyncMock, return_value=mock_ws) as mock_connect:
                await ha_bridge_with_session.connect()
                
                # Should connect with correct URL and headers
                mock_connect.assert_called_once_with(
                    'http://homeassistant.local:8123/api/websocket',
                    headers={'Authorization': 'Bearer test_token'}
                )

    @pytest.mark.asyncio
    async def test_send_notification_success(self, ha_bridge):
        """Test sending notification to Home Assistant."""
        with aioresponses() as m:
            # Mock the API response
            m.post(
                'http://homeassistant.local:8123/api/services/persistent_notification/create',
                payload={'success': True}
            )
            
            result = await ha_bridge.send_notification('Test Title', 'Test Message')
            
            assert result == {'success': True}
            
            # Check the request was made with correct data
            request = m.requests[('POST', 'http://homeassistant.local:8123/api/services/persistent_notification/create')][0]
            assert request.kwargs['json'] == {
                'title': 'Test Title',
                'message': 'Test Message'
            }
            assert request.kwargs['headers']['Authorization'] == 'Bearer test_token'

    @pytest.mark.asyncio
    async def test_send_notification_with_special_characters(self, ha_bridge):
        """Test sending notification with special characters."""
        with aioresponses() as m:
            m.post(
                'http://homeassistant.local:8123/api/services/persistent_notification/create',
                payload={'success': True}
            )
            
            title = 'Test Title with émojis 🚗⚡'
            message = 'Test Message with\nnewlines and "quotes"'
            
            result = await ha_bridge.send_notification(title, message)
            
            assert result == {'success': True}
            
            # Check the request was made with correct data
            request = m.requests[('POST', 'http://homeassistant.local:8123/api/services/persistent_notification/create')][0]
            assert request.kwargs['json'] == {
                'title': title,
                'message': message
            }

    @pytest.mark.asyncio
    async def test_send_notification_empty_strings(self, ha_bridge):
        """Test sending notification with empty strings."""
        with aioresponses() as m:
            m.post(
                'http://homeassistant.local:8123/api/services/persistent_notification/create',
                payload={'success': True}
            )
            
            result = await ha_bridge.send_notification('', '')
            
            assert result == {'success': True}
            
            # Check the request was made with correct data
            request = m.requests[('POST', 'http://homeassistant.local:8123/api/services/persistent_notification/create')][0]
            assert request.kwargs['json'] == {
                'title': '',
                'message': ''
            }

    @pytest.mark.asyncio
    async def test_get_state_success(self, ha_bridge):
        """Test getting entity state from Home Assistant."""
        with aioresponses() as m:
            # Mock the API response
            m.get(
                'http://homeassistant.local:8123/api/states/sensor.test_sensor',
                payload={
                    'entity_id': 'sensor.test_sensor',
                    'state': 'on',
                    'attributes': {
                        'friendly_name': 'Test Sensor'
                    }
                }
            )
            
            result = await ha_bridge.get_state('sensor.test_sensor')
            
            assert result == {
                'entity_id': 'sensor.test_sensor',
                'state': 'on',
                'attributes': {
                    'friendly_name': 'Test Sensor'
                }
            }
            
            # Check the request was made with correct headers
            request = m.requests[('GET', 'http://homeassistant.local:8123/api/states/sensor.test_sensor')][0]
            assert request.kwargs['headers']['Authorization'] == 'Bearer test_token'

    @pytest.mark.asyncio
    async def test_get_state_not_found(self, ha_bridge):
        """Test getting state for non-existent entity."""
        with aioresponses() as m:
            # Mock 404 response
            m.get(
                'http://homeassistant.local:8123/api/states/sensor.nonexistent',
                status=404,
                payload={'message': 'Entity not found'}
            )
            
            result = await ha_bridge.get_state('sensor.nonexistent')
            
            assert result == {'message': 'Entity not found'}

    @pytest.mark.asyncio
    async def test_get_state_various_entity_types(self, ha_bridge):
        """Test getting state for various entity types."""
        entity_states = [
            ('binary_sensor.presence', {'state': 'on'}),
            ('input_boolean.test', {'state': 'off'}),
            ('switch.test_switch', {'state': 'on'}),
            ('sensor.temperature', {'state': '20.5'}),
            ('device_tracker.phone', {'state': 'home'})
        ]
        
        with aioresponses() as m:
            for entity_id, expected_state in entity_states:
                m.get(
                    f'http://homeassistant.local:8123/api/states/{entity_id}',
                    payload=expected_state
                )
                
                result = await ha_bridge.get_state(entity_id)
                assert result == expected_state

    @pytest.mark.asyncio
    async def test_get_state_with_attributes(self, ha_bridge):
        """Test getting state with complex attributes."""
        with aioresponses() as m:
            m.get(
                'http://homeassistant.local:8123/api/states/sensor.weather',
                payload={
                    'entity_id': 'sensor.weather',
                    'state': 'sunny',
                    'attributes': {
                        'temperature': 25.5,
                        'humidity': 60,
                        'pressure': 1013.25,
                        'wind_speed': 10.5,
                        'forecast': [
                            {'day': 'today', 'temp': 25},
                            {'day': 'tomorrow', 'temp': 23}
                        ]
                    },
                    'last_changed': '2023-01-01T12:00:00+00:00',
                    'last_updated': '2023-01-01T12:00:00+00:00'
                }
            )
            
            result = await ha_bridge.get_state('sensor.weather')
            
            assert result['state'] == 'sunny'
            assert result['attributes']['temperature'] == 25.5
            assert len(result['attributes']['forecast']) == 2

    @pytest.mark.asyncio
    async def test_close_with_websocket(self, ha_bridge):
        """Test closing HABridge with active WebSocket."""
        # Mock WebSocket
        mock_ws = Mock(spec=ClientWebSocketResponse)
        mock_ws.close = AsyncMock()
        ha_bridge._ws = mock_ws
        
        # Mock session
        ha_bridge._session.close = AsyncMock()
        
        await ha_bridge.close()
        
        # Should close WebSocket and session
        mock_ws.close.assert_called_once()
        ha_bridge._session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_without_websocket(self, ha_bridge):
        """Test closing HABridge without WebSocket."""
        # Mock session
        ha_bridge._session.close = AsyncMock()
        
        await ha_bridge.close()
        
        # Should close session only
        ha_bridge._session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_notification_error_handling(self, ha_bridge):
        """Test error handling in send_notification."""
        with aioresponses() as m:
            # Mock server error
            m.post(
                'http://homeassistant.local:8123/api/services/persistent_notification/create',
                status=500,
                payload={'error': 'Internal server error'}
            )
            
            result = await ha_bridge.send_notification('Test Title', 'Test Message')
            
            assert result == {'error': 'Internal server error'}

    @pytest.mark.asyncio
    async def test_get_state_error_handling(self, ha_bridge):
        """Test error handling in get_state."""
        with aioresponses() as m:
            # Mock server error
            m.get(
                'http://homeassistant.local:8123/api/states/sensor.test',
                status=500,
                payload={'error': 'Internal server error'}
            )
            
            result = await ha_bridge.get_state('sensor.test')
            
            assert result == {'error': 'Internal server error'}

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, ha_bridge):
        """Test handling concurrent requests."""
        with aioresponses() as m:
            # Mock multiple endpoints
            m.get(
                'http://homeassistant.local:8123/api/states/sensor.test1',
                payload={'state': 'on'}
            )
            m.get(
                'http://homeassistant.local:8123/api/states/sensor.test2',
                payload={'state': 'off'}
            )
            m.post(
                'http://homeassistant.local:8123/api/services/persistent_notification/create',
                payload={'success': True}
            )
            
            # Make concurrent requests
            import asyncio
            results = await asyncio.gather(
                ha_bridge.get_state('sensor.test1'),
                ha_bridge.get_state('sensor.test2'),
                ha_bridge.send_notification('Test', 'Message')
            )
            
            assert results[0]['state'] == 'on'
            assert results[1]['state'] == 'off'
            assert results[2]['success'] == True

    @pytest.mark.asyncio
    async def test_session_reuse(self, ha_bridge):
        """Test that the same session is reused for multiple requests."""
        original_session = ha_bridge._session
        
        with aioresponses() as m:
            m.get(
                'http://homeassistant.local:8123/api/states/sensor.test',
                payload={'state': 'on'}
            )
            m.post(
                'http://homeassistant.local:8123/api/services/persistent_notification/create',
                payload={'success': True}
            )
            
            # Make multiple requests
            await ha_bridge.get_state('sensor.test')
            await ha_bridge.send_notification('Test', 'Message')
            
            # Should use same session
            assert ha_bridge._session is original_session

    @pytest.mark.asyncio
    async def test_websocket_connection_url_construction(self, ha_bridge):
        """Test WebSocket URL construction."""
        mock_ws = Mock(spec=ClientWebSocketResponse)
        mock_ws.receive_json = AsyncMock()
        mock_ws.send_json = AsyncMock()
        
        mock_ws.receive_json.side_effect = [
            {'type': 'auth_required'},
            {'type': 'auth_ok'}
        ]
        
        with patch.object(ha_bridge._session, 'ws_connect', return_value=mock_ws) as mock_connect:
            await ha_bridge.connect()
            
            # Should construct correct WebSocket URL
            expected_url = 'http://homeassistant.local:8123/api/websocket'
            mock_connect.assert_called_once_with(
                expected_url,
                headers={'Authorization': 'Bearer test_token'}
            )

    def test_url_construction_with_different_schemes(self):
        """Test URL construction with different schemes."""
        # Test HTTPS
        ha_bridge_https = HABridge('https://homeassistant.local:8123', 'token')
        assert ha_bridge_https._url == 'https://homeassistant.local:8123'
        
        # Test with path
        ha_bridge_path = HABridge('http://homeassistant.local:8123/path', 'token')
        assert ha_bridge_path._url == 'http://homeassistant.local:8123/path'

    @pytest.mark.asyncio
    async def test_auth_token_in_requests(self, ha_bridge):
        """Test that auth token is included in all requests."""
        with aioresponses() as m:
            # Mock endpoints
            m.get(
                'http://homeassistant.local:8123/api/states/sensor.test',
                payload={'state': 'on'}
            )
            m.post(
                'http://homeassistant.local:8123/api/services/persistent_notification/create',
                payload={'success': True}
            )
            
            # Make requests
            await ha_bridge.get_state('sensor.test')
            await ha_bridge.send_notification('Test', 'Message')
            
            # Check all requests have auth header
            for request in m.requests.values():
                assert len(request) > 0
                assert request[0].kwargs['headers']['Authorization'] == 'Bearer test_token'