import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import websockets
from ocpp.v16.enums import RegistrationStatus, AuthorizationStatus

from src.ocpp_proxy.ocpp_service_manager import OCPPServiceManager
from src.ocpp_proxy.config import Config



class TestOCPPServiceManager:
    """Unit tests for OCPPServiceManager class."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock config object."""
        config = Mock(spec=Config)
        config.ocpp_services = [
            {
                'id': 'service1',
                'url': 'wss://service1.com/ocpp',
                'auth_type': 'token',
                'token': 'token123',
                'enabled': True
            },
            {
                'id': 'service2',
                'url': 'wss://service2.com/ocpp',
                'auth_type': 'basic',
                'username': 'user',
                'password': 'pass',
                'enabled': True
            },
            {
                'id': 'service3',
                'url': 'wss://service3.com/ocpp',
                'auth_type': 'none',
                'enabled': False
            }
        ]
        return config

    @pytest.fixture
    def mock_backend_manager(self):
        """Create a mock backend manager."""
        manager = Mock()
        manager.request_control = AsyncMock(return_value=True)
        manager._app = {'charge_point': Mock()}
        return manager

    @pytest.fixture
    def service_manager(self, mock_config, mock_backend_manager):
        """Create an OCPPServiceManager instance for testing."""
        return OCPPServiceManager(mock_config, mock_backend_manager)

    @pytest.mark.unit
    def test_initialization(self, service_manager, mock_config, mock_backend_manager):
        """Test OCPPServiceManager initialization."""
        assert service_manager.config == mock_config
        assert service_manager.backend_manager == mock_backend_manager
        assert service_manager.services == {}
        assert service_manager._connection_tasks == {}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_start_services_no_config(self, mock_backend_manager):
        """Test starting services with no OCPP services configured."""
        config = Mock(spec=Config)
        # Mock config without ocpp_services attribute
        del config.ocpp_services  # Remove the attribute entirely
        service_manager = OCPPServiceManager(config, mock_backend_manager)
        
        # Should not raise exception
        await service_manager.start_services()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_start_services_empty_config(self, mock_backend_manager):
        """Test starting services with empty OCPP services list."""
        config = Mock(spec=Config)
        config.ocpp_services = []
        service_manager = OCPPServiceManager(config, mock_backend_manager)
        
        # Should not raise exception
        await service_manager.start_services()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_connect_service_token_auth(self, service_manager):
        """Test connecting to service with token authentication."""
        service_config = {
            'id': 'test_service',
            'url': 'wss://test.com/ocpp',
            'auth_type': 'token',
            'token': 'test_token'
        }
        
        with patch('src.ocpp_proxy.ocpp_service_manager.websockets.connect', new_callable=AsyncMock) as mock_connect, \
             patch('src.ocpp_proxy.ocpp_service_manager.OCPPServiceFactory.create_service_client') as mock_factory:
            mock_connection = Mock()
            mock_connect.return_value = mock_connection
            mock_client = Mock()
            mock_client.start = AsyncMock()
            mock_factory.return_value = mock_client
            
            await service_manager.connect_service('test_service', service_config)
            
            # Should connect with correct headers
            mock_connect.assert_called_once_with(
                'wss://test.com/ocpp',
                extra_headers={'Authorization': 'Bearer test_token'},
                subprotocols=['ocpp1.6'],
                ping_interval=30,
                ping_timeout=10
            )
            
            # Should create service client
            assert 'test_service' in service_manager.services
            assert 'test_service' in service_manager._connection_tasks

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_connect_service_basic_auth(self, service_manager):
        """Test connecting to service with basic authentication."""
        service_config = {
            'id': 'test_service',
            'url': 'wss://test.com/ocpp',
            'auth_type': 'basic',
            'username': 'testuser',
            'password': 'testpass'
        }
        
        with patch('src.ocpp_proxy.ocpp_service_manager.websockets.connect', new_callable=AsyncMock) as mock_connect, \
             patch('src.ocpp_proxy.ocpp_service_manager.OCPPServiceFactory.create_service_client') as mock_factory:
            mock_connection = Mock()
            mock_connect.return_value = mock_connection
            mock_client = Mock()
            mock_client.start = AsyncMock()
            mock_factory.return_value = mock_client
            
            await service_manager.connect_service('test_service', service_config)
            
            # Should connect with basic auth header
            call_args = mock_connect.call_args
            headers = call_args[1]['extra_headers']
            assert 'Authorization' in headers
            assert headers['Authorization'].startswith('Basic ')

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_connect_service_no_auth(self, service_manager):
        """Test connecting to service without authentication."""
        service_config = {
            'id': 'test_service',
            'url': 'wss://test.com/ocpp',
            'auth_type': 'none'
        }
        
        with patch('src.ocpp_proxy.ocpp_service_manager.websockets.connect', new_callable=AsyncMock) as mock_connect, \
             patch('src.ocpp_proxy.ocpp_service_manager.OCPPServiceFactory.create_service_client') as mock_factory:
            mock_connection = Mock()
            mock_connect.return_value = mock_connection
            mock_client = Mock()
            mock_client.start = AsyncMock()
            mock_factory.return_value = mock_client
            
            await service_manager.connect_service('test_service', service_config)
            
            # Should connect without auth headers
            call_args = mock_connect.call_args
            headers = call_args[1]['extra_headers']
            assert 'Authorization' not in headers

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_connect_service_no_url(self, service_manager):
        """Test connecting to service without URL."""
        service_config = {
            'id': 'test_service',
            'auth_type': 'none'
        }
        
        # Should not raise exception
        await service_manager.connect_service('test_service', service_config)
        
        # Should not create service
        assert 'test_service' not in service_manager.services

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_connect_service_connection_failure(self, service_manager):
        """Test connecting to service with connection failure."""
        service_config = {
            'id': 'test_service',
            'url': 'wss://test.com/ocpp',
            'auth_type': 'none'
        }
        
        with patch('src.ocpp_proxy.ocpp_service_manager.websockets.connect', new_callable=AsyncMock) as mock_connect:
            mock_connect.side_effect = Exception("Connection failed")
            
            # Should not raise exception
            await service_manager.connect_service('test_service', service_config)
            
            # Should not create service
            assert 'test_service' not in service_manager.services

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_disconnect_service(self, service_manager):
        """Test disconnecting from service."""
        # Create mock service
        mock_client = Mock()
        mock_client.connected = True
        mock_client._connection = Mock()
        mock_client._connection.close = AsyncMock()
        
        mock_task = Mock()
        mock_task.cancel = Mock()
        
        service_manager.services['test_service'] = mock_client
        service_manager._connection_tasks['test_service'] = mock_task
        
        await service_manager.disconnect_service('test_service')
        
        # Should disconnect client
        mock_task.cancel.assert_called_once()
        mock_client._connection.close.assert_called_once()
        
        # Should remove from collections
        assert 'test_service' not in service_manager.services
        assert 'test_service' not in service_manager._connection_tasks

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_disconnect_service_not_found(self, service_manager):
        """Test disconnecting from non-existent service."""
        # Should not raise exception
        await service_manager.disconnect_service('nonexistent_service')

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_request_control_from_service_success(self, service_manager):
        """Test requesting control from service."""
        # Mock charge point
        mock_cp = Mock()
        mock_cp.send_remote_start_transaction = AsyncMock(return_value=True)
        
        service_manager.backend_manager._app = {'charge_point': mock_cp}
        
        result = await service_manager.request_control_from_service(
            'test_service',
            'RemoteStartTransaction',
            {'connector_id': 1, 'id_tag': 'RFID123'}
        )
        
        # Should request control
        service_manager.backend_manager.request_control.assert_called_once_with('ocpp_service_test_service')
        
        # Should call charge point
        mock_cp.send_remote_start_transaction.assert_called_once_with(
            connector_id=1,
            id_tag='RFID123'
        )
        
        assert result == True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_request_control_from_service_rejected(self, service_manager):
        """Test requesting control from service that gets rejected."""
        service_manager.backend_manager.request_control.return_value = False
        
        result = await service_manager.request_control_from_service(
            'test_service',
            'RemoteStartTransaction',
            {'connector_id': 1, 'id_tag': 'RFID123'}
        )
        
        assert result == False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_request_control_from_service_no_backend_manager(self, mock_config):
        """Test requesting control without backend manager."""
        service_manager = OCPPServiceManager(mock_config)
        
        result = await service_manager.request_control_from_service(
            'test_service',
            'RemoteStartTransaction',
            {'connector_id': 1, 'id_tag': 'RFID123'}
        )
        
        assert result == False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_request_control_from_service_stop_transaction(self, service_manager):
        """Test requesting control for stop transaction."""
        # Mock charge point
        mock_cp = Mock()
        mock_cp.send_remote_stop_transaction = AsyncMock(return_value=True)
        
        service_manager.backend_manager._app = {'charge_point': mock_cp}
        
        result = await service_manager.request_control_from_service(
            'test_service',
            'RemoteStopTransaction',
            {'transaction_id': 123}
        )
        
        # Should call charge point
        mock_cp.send_remote_stop_transaction.assert_called_once_with(
            transaction_id=123
        )
        
        assert result == True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_request_control_from_service_exception(self, service_manager):
        """Test requesting control with exception."""
        # Mock charge point that raises exception
        mock_cp = Mock()
        mock_cp.send_remote_start_transaction = AsyncMock(side_effect=Exception("Call failed"))
        
        service_manager.backend_manager._app = {'charge_point': mock_cp}
        
        result = await service_manager.request_control_from_service(
            'test_service',
            'RemoteStartTransaction',
            {'connector_id': 1, 'id_tag': 'RFID123'}
        )
        
        assert result == False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_broadcast_event_to_services(self, service_manager):
        """Test broadcasting events to services."""
        # Create mock services
        mock_client1 = Mock()
        mock_client1.connected = True
        mock_client2 = Mock()
        mock_client2.connected = True
        mock_client3 = Mock()
        mock_client3.connected = False
        
        service_manager.services = {
            'service1': mock_client1,
            'service2': mock_client2,
            'service3': mock_client3
        }
        
        event = {'type': 'test_event', 'data': 'test_data'}
        
        with patch.object(service_manager, '_send_event_to_service') as mock_send:
            service_manager.broadcast_event_to_services(event)
            
            # Should send to connected services only
            assert mock_send.call_count == 2
            mock_send.assert_any_call(mock_client1, event)
            mock_send.assert_any_call(mock_client2, event)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_event_to_service_status(self, service_manager):
        """Test sending status event to service."""
        mock_client = Mock()
        mock_client.service_id = 'test_service'
        
        event = {
            'type': 'status',
            'connector_id': 1,
            'status': 'Available',
            'error_code': 'NoError'
        }
        
        # Should not raise exception (event is processed but not forwarded to service)
        await service_manager._send_event_to_service(mock_client, event)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_event_to_service_meter(self, service_manager):
        """Test sending meter event to service."""
        mock_client = Mock()
        mock_client.service_id = 'test_service'
        
        event = {
            'type': 'meter',
            'connector_id': 1,
            'values': [{'value': '1000'}]
        }
        
        # Should not raise exception (event is processed but not forwarded to service)
        await service_manager._send_event_to_service(mock_client, event)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_event_to_service_transaction_started(self, service_manager):
        """Test sending transaction started event to service."""
        mock_client = Mock()
        mock_client.service_id = 'test_service'
        
        event = {
            'type': 'transaction_started',
            'connector_id': 1,
            'id_tag': 'RFID123',
            'meter_start': 0,
            'timestamp': '2023-01-01T12:00:00Z'
        }
        
        # Should not raise exception (event is processed but not forwarded to service)
        await service_manager._send_event_to_service(mock_client, event)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_event_to_service_transaction_stopped(self, service_manager):
        """Test sending transaction stopped event to service."""
        mock_client = Mock()
        mock_client.service_id = 'test_service'
        
        event = {
            'type': 'transaction_stopped',
            'transaction_id': 123,
            'meter_stop': 5000,
            'timestamp': '2023-01-01T13:00:00Z'
        }
        
        # Should not raise exception (event is processed but not forwarded to service)
        await service_manager._send_event_to_service(mock_client, event)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_event_to_service_exception(self, service_manager):
        """Test sending event with exception."""
        mock_client = Mock()
        mock_client.service_id = 'test_service'
        
        event = {
            'type': 'status',
            'connector_id': 1,
            'status': 'Available'
        }
        
        # Should not raise exception
        await service_manager._send_event_to_service(mock_client, event)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_stop_all_services(self, service_manager):
        """Test stopping all services."""
        # Create mock services
        service_manager.services = {
            'service1': Mock(),
            'service2': Mock(),
            'service3': Mock()
        }
        
        with patch.object(service_manager, 'disconnect_service') as mock_disconnect:
            await service_manager.stop_all_services()
            
            # Should disconnect all services
            assert mock_disconnect.call_count == 3
            mock_disconnect.assert_any_call('service1')
            mock_disconnect.assert_any_call('service2')
            mock_disconnect.assert_any_call('service3')

    @pytest.mark.unit
    def test_get_service_status(self, service_manager):
        """Test getting service status."""
        # Create mock services
        mock_client1 = Mock()
        mock_client1.connected = True
        mock_client1.authenticated = True
        mock_client1.ocpp_version = '1.6'
        mock_client2 = Mock()
        mock_client2.connected = False
        mock_client2.authenticated = False
        mock_client2.ocpp_version = '2.0.1'
        
        service_manager.services = {
            'service1': mock_client1,
            'service2': mock_client2
        }
        
        status = service_manager.get_service_status()
        
        assert status['service1']['connected'] == True
        assert status['service1']['authenticated'] == True
        assert status['service1']['version'] == '1.6'
        assert status['service2']['connected'] == False
        assert status['service2']['authenticated'] == False
        assert status['service2']['version'] == '2.0.1'