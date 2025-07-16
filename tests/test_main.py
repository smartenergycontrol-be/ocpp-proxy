import pytest
import json
import tempfile
import os
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, make_mocked_request
import aiohttp

from src.ocpp_proxy.main import (
    init_app, charger_handler, backend_handler, sessions_json, sessions_csv,
    override_handler, status_handler, welcome_handler, cleanup_app
)


class TestMainApplication(AioHTTPTestCase):
    """Integration tests for the main application."""

    @pytest.fixture
    def temp_config_file(self):
        """Create a temporary configuration file."""
        config_data = {
            'allow_shared_charging': True,
            'preferred_provider': 'preferred_backend',
            'rate_limit_seconds': 5,
            'ocpp_services': []
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            import yaml
            yaml.dump(config_data, f)
            config_path = f.name
        
        yield config_path
        os.unlink(config_path)

    async def get_application(self):
        """Create application for testing."""
        with patch.dict(os.environ, {'HA_URL': '', 'HA_TOKEN': ''}):
            with patch('src.ocpp_proxy.main.OCPPServiceManager') as mock_ocpp_manager:
                mock_ocpp_manager.return_value.start_services = AsyncMock()
                mock_ocpp_manager.return_value.get_service_status = Mock(return_value={})
                app = await init_app()
                return app

    @pytest.mark.integration
    async def test_welcome_handler(self):
        """Test the welcome page handler."""
        request = await self.client.request('GET', '/')
        assert request.status == 200
        
        content = await request.text()
        assert 'EV Charger Proxy' in content
        assert '/charger' in content
        assert '/backend' in content
        assert '/sessions' in content
        assert '/status' in content

    @pytest.mark.integration
    async def test_sessions_json_empty(self):
        """Test sessions JSON endpoint with no sessions."""
        with patch.object(self.app['event_logger'], 'get_sessions', return_value=[]):
            request = await self.client.request('GET', '/sessions')
            assert request.status == 200
            
            data = await request.json()
            assert data == []

    @pytest.mark.integration
    async def test_sessions_json_with_data(self):
        """Test sessions JSON endpoint with session data."""
        mock_sessions = [
            {
                'timestamp': '2023-01-01T12:00:00Z',
                'backend_id': 'test_backend',
                'duration_s': 3600.0,
                'energy_kwh': 25.0,
                'revenue': 5.0
            }
        ]
        
        with patch.object(self.app['event_logger'], 'get_sessions', return_value=mock_sessions):
            request = await self.client.request('GET', '/sessions')
            assert request.status == 200
            
            data = await request.json()
            assert data == mock_sessions

    @pytest.mark.integration
    async def test_sessions_csv_empty(self):
        """Test sessions CSV endpoint with no sessions."""
        with patch.object(self.app['event_logger'], 'get_sessions', return_value=[]):
            request = await self.client.request('GET', '/sessions.csv')
            assert request.status == 200
            assert request.headers['Content-Type'].startswith('text/csv')
            
            content = await request.text()
            lines = content.strip().split('\n')
            assert len(lines) == 1  # Just header
            # Handle potential Windows line endings
            header = lines[0].rstrip('\r')
            assert header == 'timestamp,backend_id,duration_s,energy_kwh,revenue'

    @pytest.mark.integration
    async def test_sessions_csv_with_data(self):
        """Test sessions CSV endpoint with session data."""
        mock_sessions = [
            {
                'timestamp': '2023-01-01T12:00:00Z',
                'backend_id': 'test_backend',
                'duration_s': 3600.0,
                'energy_kwh': 25.0,
                'revenue': 5.0
            }
        ]
        
        with patch.object(self.app['event_logger'], 'get_sessions', return_value=mock_sessions):
            request = await self.client.request('GET', '/sessions.csv')
            assert request.status == 200
            
            content = await request.text()
            lines = content.strip().split('\n')
            assert len(lines) == 2  # Header + data
            # Handle potential Windows line endings
            header = lines[0].rstrip('\r')
            data_line = lines[1].rstrip('\r')
            assert header == 'timestamp,backend_id,duration_s,energy_kwh,revenue'
            assert data_line == '2023-01-01T12:00:00Z,test_backend,3600.0,25.0,5.0'

    @pytest.mark.integration
    async def test_status_handler(self):
        """Test the status handler."""
        # Mock backend manager status
        mock_status = {
            'websocket_backends': ['backend1', 'backend2'],
            'lock_owner': 'backend1',
            'ocpp_services': {'service1': {'connected': True}}
        }
        
        with patch.object(self.app['backend_manager'], 'get_backend_status', return_value=mock_status):
            request = await self.client.request('GET', '/status')
            assert request.status == 200
            
            data = await request.json()
            assert data == mock_status

    @pytest.mark.integration
    async def test_override_handler_success(self):
        """Test the override handler with successful override."""
        with patch.object(self.app['backend_manager'], 'release_control') as mock_release:
            with patch.object(self.app['backend_manager'], 'request_control', return_value=True) as mock_request:
                request = await self.client.request('POST', '/override', json={'backend_id': 'test_backend'})
                assert request.status == 200
                
                data = await request.json()
                assert data['success'] == True
                
                mock_release.assert_called_once()
                mock_request.assert_called_once_with('test_backend')

    @pytest.mark.integration
    async def test_override_handler_failure(self):
        """Test the override handler with failed override."""
        with patch.object(self.app['backend_manager'], 'release_control') as mock_release:
            with patch.object(self.app['backend_manager'], 'request_control', return_value=False) as mock_request:
                request = await self.client.request('POST', '/override', json={'backend_id': 'test_backend'})
                assert request.status == 200
                
                data = await request.json()
                assert data['success'] == False
                
                mock_release.assert_called_once()
                mock_request.assert_called_once_with('test_backend')

    @pytest.mark.integration
    async def test_override_handler_invalid_json(self):
        """Test the override handler with invalid JSON."""
        request = await self.client.request('POST', '/override', data='invalid json')
        assert request.status == 400

    @pytest.mark.integration
    async def test_charger_handler_websocket(self):
        """Test the charger WebSocket handler."""
        # This is a complex test as it involves WebSocket connections
        # We'll mock the WebSocket and ChargePoint
        with patch('src.ocpp_proxy.main.ChargePoint') as mock_cp_class:
            mock_cp = Mock()
            mock_cp.start = AsyncMock()
            mock_cp_class.return_value = mock_cp
            
            # Create a mock WebSocket connection
            async with self.client.ws_connect('/charger') as ws:
                # The connection should be established
                assert ws.closed == False
                
                # Close the connection
                await ws.close()

    @pytest.mark.integration
    async def test_backend_handler_websocket(self):
        """Test the backend WebSocket handler."""
        with patch.object(self.app['backend_manager'], 'subscribe') as mock_subscribe:
            with patch.object(self.app['backend_manager'], 'unsubscribe') as mock_unsubscribe:
                with patch.object(self.app['backend_manager'], 'request_control', return_value=True) as mock_request:
                    # Create a mock charge point
                    mock_cp = Mock()
                    mock_cp.call_remote_start_transaction = AsyncMock()
                    # Create a JSON-serializable mock result
                    mock_result = {'status': 'Accepted'}
                    mock_cp.call_remote_start_transaction.return_value = mock_result
                    
                    self.app['charge_point'] = mock_cp
                    
                    # Connect to backend endpoint
                    async with self.client.ws_connect('/backend?id=test_backend') as ws:
                        # Send a remote start transaction request
                        await ws.send_json({
                            'action': 'RemoteStartTransaction',
                            'connector_id': 1,
                            'id_tag': 'RFID123'
                        })
                        
                        # Receive response
                        response = await ws.receive_json()
                        
                        assert response['action'] == 'RemoteStartTransaction'
                        assert response['result']['status'] == 'Accepted'
                        
                        # Check that subscribe was called with the correct backend ID
                        # (WebSocket object type differs between client and server)
                        mock_subscribe.assert_called_once()
                        assert mock_subscribe.call_args[0][0] == 'test_backend'
                        mock_request.assert_called_once_with('test_backend')

    @pytest.mark.integration
    async def test_backend_handler_remote_stop_transaction(self):
        """Test backend handler remote stop transaction."""
        with patch.object(self.app['backend_manager'], 'subscribe'):
            with patch.object(self.app['backend_manager'], 'unsubscribe'):
                # Create a mock charge point
                mock_cp = Mock()
                mock_cp.call_remote_stop_transaction = AsyncMock()
                # Create a JSON-serializable mock result
                mock_result = {'status': 'Accepted'}
                mock_cp.call_remote_stop_transaction.return_value = mock_result
                
                self.app['charge_point'] = mock_cp
                
                # Connect to backend endpoint
                async with self.client.ws_connect('/backend?id=test_backend') as ws:
                    # Send a remote stop transaction request
                    await ws.send_json({
                        'action': 'RemoteStopTransaction',
                        'transaction_id': 123
                    })
                    
                    # Receive response
                    response = await ws.receive_json()
                    
                    assert response['action'] == 'RemoteStopTransaction'
                    assert response['result']['status'] == 'Accepted'

    @pytest.mark.integration
    async def test_backend_handler_control_denied(self):
        """Test backend handler when control is denied."""
        with patch.object(self.app['backend_manager'], 'subscribe'):
            with patch.object(self.app['backend_manager'], 'unsubscribe'):
                with patch.object(self.app['backend_manager'], 'request_control', return_value=False):
                    # Create a mock charge point
                    mock_cp = Mock()
                    self.app['charge_point'] = mock_cp
                    
                    # Connect to backend endpoint
                    async with self.client.ws_connect('/backend?id=test_backend') as ws:
                        # Send a remote start transaction request
                        await ws.send_json({
                            'action': 'RemoteStartTransaction',
                            'connector_id': 1,
                            'id_tag': 'RFID123'
                        })
                        
                        # Receive response
                        response = await ws.receive_json()
                        
                        assert response['error'] == 'control_locked'

    @pytest.mark.integration
    async def test_backend_handler_unknown_action(self):
        """Test backend handler with unknown action."""
        with patch.object(self.app['backend_manager'], 'subscribe'):
            with patch.object(self.app['backend_manager'], 'unsubscribe'):
                # Connect to backend endpoint
                async with self.client.ws_connect('/backend?id=test_backend') as ws:
                    # Send unknown action
                    await ws.send_json({
                        'action': 'UnknownAction',
                        'some_param': 'value'
                    })
                    
                    # Receive response
                    response = await ws.receive_json()
                    
                    assert response['error'] == 'unknown_action'

    @pytest.mark.integration
    async def test_backend_handler_no_charge_point(self):
        """Test backend handler when no charge point is connected."""
        with patch.object(self.app['backend_manager'], 'subscribe'):
            with patch.object(self.app['backend_manager'], 'unsubscribe'):
                with patch.object(self.app['backend_manager'], 'request_control', return_value=True):
                    # No charge point in app
                    self.app.pop('charge_point', None)
                    
                    # Connect to backend endpoint
                    async with self.client.ws_connect('/backend?id=test_backend') as ws:
                        # Send a remote start transaction request
                        await ws.send_json({
                            'action': 'RemoteStartTransaction',
                            'connector_id': 1,
                            'id_tag': 'RFID123'
                        })
                        
                        # Receive response
                        response = await ws.receive_json()
                        
                        assert response['error'] == 'unknown_action'

    @pytest.mark.integration
    async def test_backend_handler_default_id(self):
        """Test backend handler with default backend ID."""
        with patch.object(self.app['backend_manager'], 'subscribe') as mock_subscribe:
            with patch.object(self.app['backend_manager'], 'unsubscribe') as mock_unsubscribe:
                # Connect without ID parameter
                async with self.client.ws_connect('/backend') as ws:
                    # Should use 'unknown' as default ID
                    # (WebSocket object type differs between client and server)
                    mock_subscribe.assert_called_once()
                    assert mock_subscribe.call_args[0][0] == 'unknown'


class TestMainApplicationHandlers:
    """Unit tests for individual handlers."""

    @pytest.fixture
    def mock_request(self):
        """Create a mock request object."""
        request = Mock()
        request.app = {}
        return request

    @pytest.fixture
    def mock_app_components(self):
        """Create mock app components."""
        components = {
            'backend_manager': Mock(),
            'ha_bridge': Mock(),
            'event_logger': Mock(),
            'ocpp_service_manager': Mock(),
            'charge_point': Mock()
        }
        return components

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_welcome_handler_unit(self, mock_request):
        """Unit test for welcome handler."""
        response = await welcome_handler(mock_request)
        
        assert response.status == 200
        assert response.content_type == 'text/html'
        
        # Check that HTML content contains expected elements
        html_content = response.text
        assert 'EV Charger Proxy' in html_content
        assert '/charger' in html_content
        assert '/backend' in html_content
        assert '/sessions' in html_content
        assert '/status' in html_content

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_sessions_json_unit(self, mock_request, mock_app_components):
        """Unit test for sessions JSON handler."""
        mock_request.app = mock_app_components
        mock_sessions = [{'timestamp': '2023-01-01T12:00:00Z', 'backend_id': 'test'}]
        mock_app_components['event_logger'].get_sessions.return_value = mock_sessions
        
        response = await sessions_json(mock_request)
        
        assert response.status == 200
        assert response.content_type == 'application/json'

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_sessions_csv_unit(self, mock_request, mock_app_components):
        """Unit test for sessions CSV handler."""
        mock_request.app = mock_app_components
        mock_sessions = [
            {
                'timestamp': '2023-01-01T12:00:00Z',
                'backend_id': 'test_backend',
                'duration_s': 3600.0,
                'energy_kwh': 25.0,
                'revenue': 5.0
            }
        ]
        mock_app_components['event_logger'].get_sessions.return_value = mock_sessions
        
        response = await sessions_csv(mock_request)
        
        assert response.status == 200
        assert response.content_type == 'text/csv'
        
        # Check CSV content
        content = response.text
        lines = content.strip().split('\n')
        assert len(lines) == 2  # Header + data
        assert 'timestamp,backend_id,duration_s,energy_kwh,revenue' in lines[0]
        assert '2023-01-01T12:00:00Z,test_backend,3600.0,25.0,5.0' in lines[1]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_status_handler_unit(self, mock_request, mock_app_components):
        """Unit test for status handler."""
        mock_request.app = mock_app_components
        mock_status = {
            'websocket_backends': ['backend1'],
            'lock_owner': 'backend1',
            'ocpp_services': {}
        }
        mock_app_components['backend_manager'].get_backend_status.return_value = mock_status
        
        response = await status_handler(mock_request)
        
        assert response.status == 200
        assert response.content_type == 'application/json'

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_override_handler_unit(self, mock_request, mock_app_components):
        """Unit test for override handler."""
        mock_request.app = mock_app_components
        mock_request.json = AsyncMock(return_value={'backend_id': 'test_backend'})
        
        mock_manager = mock_app_components['backend_manager']
        mock_manager.request_control = AsyncMock(return_value=True)
        mock_manager._lock_owner = 'test_backend'
        
        response = await override_handler(mock_request)
        
        assert response.status == 200
        assert response.content_type == 'application/json'
        
        mock_manager.release_control.assert_called_once()
        mock_manager.request_control.assert_called_once_with('test_backend')

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cleanup_app_unit(self, mock_app_components):
        """Unit test for cleanup_app function."""
        app = mock_app_components
        mock_app_components['ocpp_service_manager'].stop_all_services = AsyncMock()
        
        await cleanup_app(app)
        
        mock_app_components['ocpp_service_manager'].stop_all_services.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cleanup_app_no_ocpp_manager(self):
        """Unit test for cleanup_app without OCPP service manager."""
        app = {}
        
        # Should not raise exception
        await cleanup_app(app)


class TestMainApplicationInitialization:
    """Tests for application initialization."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_init_app_with_ha_environment(self):
        """Test app initialization with HA environment variables."""
        with patch.dict(os.environ, {'HA_URL': 'http://ha.local', 'HA_TOKEN': 'token123'}):
            with patch('src.ocpp_proxy.main.OCPPServiceManager') as mock_ocpp_manager:
                mock_ocpp_manager.return_value.start_services = AsyncMock()
                
                app = await init_app()
                
                assert app['ha_bridge'] is not None
                assert app['backend_manager'] is not None
                assert app['event_logger'] is not None
                assert app['ocpp_service_manager'] is not None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_init_app_without_ha_environment(self):
        """Test app initialization without HA environment variables."""
        with patch.dict(os.environ, {'HA_URL': '', 'HA_TOKEN': ''}, clear=True):
            with patch('src.ocpp_proxy.main.OCPPServiceManager') as mock_ocpp_manager:
                mock_ocpp_manager.return_value.start_services = AsyncMock()
                
                app = await init_app()
                
                assert app['ha_bridge'] is None
                assert app['backend_manager'] is not None
                assert app['event_logger'] is not None
                assert app['ocpp_service_manager'] is not None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_init_app_custom_db_path(self):
        """Test app initialization with custom database path."""
        with patch.dict(os.environ, {'LOG_DB_PATH': '/custom/path/log.db'}):
            with patch('src.ocpp_proxy.main.OCPPServiceManager') as mock_ocpp_manager:
                mock_ocpp_manager.return_value.start_services = AsyncMock()
                
                with patch('src.ocpp_proxy.main.EventLogger') as mock_logger:
                    app = await init_app()
                    
                    mock_logger.assert_called_once_with(db_path='/custom/path/log.db')

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_init_app_route_registration(self):
        """Test that all routes are registered correctly."""
        with patch('src.ocpp_proxy.main.OCPPServiceManager') as mock_ocpp_manager:
            mock_ocpp_manager.return_value.start_services = AsyncMock()
            
            app = await init_app()
            
            # Check that routes are registered
            route_paths = [route.resource.canonical for route in app.router.routes()]
            
            assert '/' in route_paths
            assert '/charger' in route_paths
            assert '/backend' in route_paths
            assert '/sessions' in route_paths
            assert '/sessions.csv' in route_paths
            assert '/status' in route_paths
            assert '/override' in route_paths

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_init_app_ocpp_service_startup(self):
        """Test that OCPP services are started during initialization."""
        with patch('src.ocpp_proxy.main.OCPPServiceManager') as mock_ocpp_manager:
            mock_manager_instance = Mock()
            mock_manager_instance.start_services = AsyncMock()
            mock_ocpp_manager.return_value = mock_manager_instance
            
            app = await init_app()
            
            # Should start OCPP services
            mock_manager_instance.start_services.assert_called_once()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_init_app_backend_manager_app_reference(self):
        """Test that backend manager gets app reference."""
        with patch('src.ocpp_proxy.main.OCPPServiceManager') as mock_ocpp_manager:
            mock_ocpp_manager.return_value.start_services = AsyncMock()
            
            with patch('src.ocpp_proxy.main.BackendManager') as mock_backend_manager:
                mock_manager_instance = Mock()
                mock_manager_instance.set_app_reference = Mock()
                mock_backend_manager.return_value = mock_manager_instance
                
                app = await init_app()
                
                # Should set app reference
                mock_manager_instance.set_app_reference.assert_called_once_with(app)