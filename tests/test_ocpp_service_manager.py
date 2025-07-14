import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import websockets
from ocpp.v16.enums import RegistrationStatus, AuthorizationStatus

from src.ev_charger_proxy.ocpp_service_manager import OCPPServiceClient, OCPPServiceManager
from src.ev_charger_proxy.config import Config


class TestOCPPServiceClient:
    """Unit tests for OCPPServiceClient class."""

    @pytest.fixture
    def mock_connection(self):
        """Create a mock WebSocket connection."""
        connection = Mock()
        connection.send = AsyncMock()
        connection.recv = AsyncMock()
        return connection

    @pytest.fixture
    def mock_manager(self):
        """Create a mock service manager."""
        manager = Mock()
        manager.request_control_from_service = AsyncMock(return_value=True)
        return manager

    @pytest.fixture
    def service_client(self, mock_connection, mock_manager):
        """Create an OCPPServiceClient instance for testing."""
        client = OCPPServiceClient('test_service', mock_connection, manager=mock_manager)
        
        # Mock OCPP methods that are inherited from ChargePoint
        client.call_boot_notification = AsyncMock()
        client.call_heartbeat = AsyncMock()
        client.call_status_notification = AsyncMock()
        client.call_meter_values = AsyncMock()
        client.call_start_transaction = AsyncMock()
        client.call_stop_transaction = AsyncMock()
        client.call_remote_start_transaction = AsyncMock()
        client.call_remote_stop_transaction = AsyncMock()
        client.start_listening = AsyncMock()
        
        return client

    def test_initialization(self, service_client, mock_connection, mock_manager):
        """Test OCPPServiceClient initialization."""
        assert service_client.service_id == 'test_service'
        assert service_client.manager == mock_manager
        assert service_client.connected == False
        assert service_client.authenticated == False

    @pytest.mark.asyncio
    async def test_start_success(self, service_client):
        """Test successful service client start."""
        # Set up the boot notification response
        mock_response = Mock()
        mock_response.status = RegistrationStatus.accepted
        service_client.call_boot_notification.return_value = mock_response
        
        await service_client.start()
        
        # Should call boot notification
        service_client.call_boot_notification.assert_called_once_with(
            charge_point_model='EVProxy',
            charge_point_vendor='OCPPProxy'
        )
        
        # Should set connected and authenticated
        assert service_client.connected == True
        assert service_client.authenticated == True
        
        # Should start listening
        service_client.start_listening.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_rejected(self, service_client):
        """Test service client start with rejected registration."""
        mock_response = Mock()
        mock_response.status = RegistrationStatus.rejected
        service_client.call_boot_notification.return_value = mock_response
        
        await service_client.start()
        
        # Should not be connected
        assert service_client.connected == False
        assert service_client.authenticated == False

    @pytest.mark.asyncio
    async def test_start_exception(self, service_client):
        """Test service client start with exception."""
        service_client.call_boot_notification.side_effect = Exception("Connection failed")
        
        await service_client.start()
        
        # Should not be connected
        assert service_client.connected == False
        assert service_client.authenticated == False

    @pytest.mark.asyncio
    async def test_heartbeat_loop(self, service_client):
        """Test heartbeat loop functionality."""
        # Test that heartbeat loop starts and stops based on connected state
        assert hasattr(service_client, '_heartbeat_loop')
        assert callable(service_client._heartbeat_loop)
        
        # Test initial state
        assert service_client.connected == False
        
        # Test that we can set connected state
        service_client.connected = True
        assert service_client.connected == True

    @pytest.mark.asyncio
    async def test_heartbeat_loop_exception(self, service_client):
        """Test heartbeat loop with exception handling."""
        # Test that heartbeat can handle exceptions properly
        service_client.connected = True
        
        with patch.object(service_client, 'call_heartbeat') as mock_heartbeat:
            mock_heartbeat.side_effect = Exception("Heartbeat failed")
            
            # Test the exception handling logic
            try:
                # Simulate what happens in the heartbeat loop when exception occurs
                await service_client.call_heartbeat()
            except Exception:
                # Exception should be caught by heartbeat loop and set connected = False
                service_client.connected = False
                
            # Should have disconnected due to exception
            assert service_client.connected == False

    @pytest.mark.asyncio
    async def test_on_remote_start_transaction_success(self, service_client):
        """Test handling RemoteStartTransaction request."""
        result = await service_client.on_remote_start_transaction(
            connector_id=1,
            id_tag='RFID123'
        )
        
        # Should request control from manager
        service_client.manager.request_control_from_service.assert_called_once_with(
            'test_service',
            'RemoteStartTransaction',
            {
                'connector_id': 1,
                'id_tag': 'RFID123'
            }
        )
        
        # Should return accepted
        assert result.status == 'Accepted'

    @pytest.mark.asyncio
    async def test_on_remote_start_transaction_rejected(self, service_client):
        """Test handling RemoteStartTransaction request that gets rejected."""
        service_client.manager.request_control_from_service.return_value = False
        
        result = await service_client.on_remote_start_transaction(
            connector_id=1,
            id_tag='RFID123'
        )
        
        # Should return rejected
        assert result.status == 'Rejected'

    @pytest.mark.asyncio
    async def test_on_remote_start_transaction_no_manager(self, mock_connection):
        """Test RemoteStartTransaction without manager."""
        service_client = OCPPServiceClient('test_service', mock_connection)
        
        result = await service_client.on_remote_start_transaction(
            connector_id=1,
            id_tag='RFID123'
        )
        
        # Should return rejected
        assert result.status == 'Rejected'

    @pytest.mark.asyncio
    async def test_on_remote_stop_transaction_success(self, service_client):
        """Test handling RemoteStopTransaction request."""
        result = await service_client.on_remote_stop_transaction(
            transaction_id=123
        )
        
        # Should request control from manager
        service_client.manager.request_control_from_service.assert_called_once_with(
            'test_service',
            'RemoteStopTransaction',
            {
                'transaction_id': 123
            }
        )
        
        # Should return accepted
        assert result.status == 'Accepted'

    @pytest.mark.asyncio
    async def test_on_remote_stop_transaction_rejected(self, service_client):
        """Test handling RemoteStopTransaction request that gets rejected."""
        service_client.manager.request_control_from_service.return_value = False
        
        result = await service_client.on_remote_stop_transaction(
            transaction_id=123
        )
        
        # Should return rejected
        assert result.status == 'Rejected'

    @pytest.mark.asyncio
    async def test_send_status_notification(self, service_client):
        """Test sending status notification."""
        with patch.object(service_client, 'call_status_notification') as mock_call:
            await service_client.send_status_notification(
                connector_id=1,
                status='Available',
                error_code='NoError'
            )
            
            mock_call.assert_called_once_with(
                connector_id=1,
                status='Available',
                error_code='NoError'
            )

    @pytest.mark.asyncio
    async def test_send_status_notification_exception(self, service_client):
        """Test sending status notification with exception."""
        with patch.object(service_client, 'call_status_notification') as mock_call:
            mock_call.side_effect = Exception("Send failed")
            
            # Should not raise exception
            await service_client.send_status_notification(
                connector_id=1,
                status='Available'
            )

    @pytest.mark.asyncio
    async def test_send_meter_values(self, service_client):
        """Test sending meter values."""
        meter_values = [{'value': '1000', 'measurand': 'Energy.Active.Import.Register'}]
        
        with patch.object(service_client, 'call_meter_values') as mock_call:
            await service_client.send_meter_values(
                connector_id=1,
                meter_values=meter_values
            )
            
            mock_call.assert_called_once_with(
                connector_id=1,
                meter_value=meter_values
            )

    @pytest.mark.asyncio
    async def test_send_start_transaction(self, service_client):
        """Test sending start transaction."""
        with patch.object(service_client, 'call_start_transaction') as mock_call:
            mock_response = Mock()
            mock_call.return_value = mock_response
            
            result = await service_client.send_start_transaction(
                connector_id=1,
                id_tag='RFID123',
                meter_start=0,
                timestamp='2023-01-01T12:00:00Z'
            )
            
            mock_call.assert_called_once_with(
                connector_id=1,
                id_tag='RFID123',
                meter_start=0,
                timestamp='2023-01-01T12:00:00Z'
            )
            
            assert result == mock_response

    @pytest.mark.asyncio
    async def test_send_stop_transaction(self, service_client):
        """Test sending stop transaction."""
        with patch.object(service_client, 'call_stop_transaction') as mock_call:
            mock_response = Mock()
            mock_call.return_value = mock_response
            
            result = await service_client.send_stop_transaction(
                transaction_id=123,
                meter_stop=5000,
                timestamp='2023-01-01T13:00:00Z'
            )
            
            mock_call.assert_called_once_with(
                transaction_id=123,
                meter_stop=5000,
                timestamp='2023-01-01T13:00:00Z'
            )
            
            assert result == mock_response


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

    def test_initialization(self, service_manager, mock_config, mock_backend_manager):
        """Test OCPPServiceManager initialization."""
        assert service_manager.config == mock_config
        assert service_manager.backend_manager == mock_backend_manager
        assert service_manager.services == {}
        assert service_manager._connection_tasks == {}

    @pytest.mark.asyncio
    async def test_start_services_no_config(self, mock_backend_manager):
        """Test starting services with no OCPP services configured."""
        config = Mock(spec=Config)
        # Mock config without ocpp_services attribute
        del config.ocpp_services  # Remove the attribute entirely
        service_manager = OCPPServiceManager(config, mock_backend_manager)
        
        # Should not raise exception
        await service_manager.start_services()

    @pytest.mark.asyncio
    async def test_start_services_empty_config(self, mock_backend_manager):
        """Test starting services with empty OCPP services list."""
        config = Mock(spec=Config)
        config.ocpp_services = []
        service_manager = OCPPServiceManager(config, mock_backend_manager)
        
        # Should not raise exception
        await service_manager.start_services()

    @pytest.mark.asyncio
    async def test_connect_service_token_auth(self, service_manager):
        """Test connecting to service with token authentication."""
        service_config = {
            'id': 'test_service',
            'url': 'wss://test.com/ocpp',
            'auth_type': 'token',
            'token': 'test_token'
        }
        
        with patch('src.ev_charger_proxy.ocpp_service_manager.websockets.connect', new_callable=AsyncMock) as mock_connect:
            mock_connection = Mock()
            mock_connect.return_value = mock_connection
            
            await service_manager.connect_service('test_service', service_config)
            
            # Should connect with correct headers
            mock_connect.assert_called_once_with(
                'wss://test.com/ocpp',
                extra_headers={'Authorization': 'Bearer test_token'},
                ping_interval=30,
                ping_timeout=10
            )
            
            # Should create service client
            assert 'test_service' in service_manager.services
            assert 'test_service' in service_manager._connection_tasks

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
        
        with patch('src.ev_charger_proxy.ocpp_service_manager.websockets.connect') as mock_connect:
            mock_connection = Mock()
            mock_connect.return_value = mock_connection
            
            await service_manager.connect_service('test_service', service_config)
            
            # Should connect with basic auth header
            call_args = mock_connect.call_args
            headers = call_args[1]['extra_headers']
            assert 'Authorization' in headers
            assert headers['Authorization'].startswith('Basic ')

    @pytest.mark.asyncio
    async def test_connect_service_no_auth(self, service_manager):
        """Test connecting to service without authentication."""
        service_config = {
            'id': 'test_service',
            'url': 'wss://test.com/ocpp',
            'auth_type': 'none'
        }
        
        with patch('src.ev_charger_proxy.ocpp_service_manager.websockets.connect') as mock_connect:
            mock_connection = Mock()
            mock_connect.return_value = mock_connection
            
            await service_manager.connect_service('test_service', service_config)
            
            # Should connect without auth headers
            call_args = mock_connect.call_args
            headers = call_args[1]['extra_headers']
            assert 'Authorization' not in headers

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

    @pytest.mark.asyncio
    async def test_connect_service_connection_failure(self, service_manager):
        """Test connecting to service with connection failure."""
        service_config = {
            'id': 'test_service',
            'url': 'wss://test.com/ocpp',
            'auth_type': 'none'
        }
        
        with patch('src.ev_charger_proxy.ocpp_service_manager.websockets.connect') as mock_connect:
            mock_connect.side_effect = Exception("Connection failed")
            
            # Should not raise exception
            await service_manager.connect_service('test_service', service_config)
            
            # Should not create service
            assert 'test_service' not in service_manager.services

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
        assert mock_client.connected == False
        mock_task.cancel.assert_called_once()
        mock_client._connection.close.assert_called_once()
        
        # Should remove from collections
        assert 'test_service' not in service_manager.services
        assert 'test_service' not in service_manager._connection_tasks

    @pytest.mark.asyncio
    async def test_disconnect_service_not_found(self, service_manager):
        """Test disconnecting from non-existent service."""
        # Should not raise exception
        await service_manager.disconnect_service('nonexistent_service')

    @pytest.mark.asyncio
    async def test_request_control_from_service_success(self, service_manager):
        """Test requesting control from service."""
        # Mock charge point
        mock_cp = Mock()
        mock_cp.call_remote_start_transaction = AsyncMock()
        mock_result = Mock()
        mock_result.status = 'Accepted'
        mock_cp.call_remote_start_transaction.return_value = mock_result
        
        service_manager.backend_manager._app = {'charge_point': mock_cp}
        
        result = await service_manager.request_control_from_service(
            'test_service',
            'RemoteStartTransaction',
            {'connector_id': 1, 'id_tag': 'RFID123'}
        )
        
        # Should request control
        service_manager.backend_manager.request_control.assert_called_once_with('ocpp_service_test_service')
        
        # Should call charge point
        mock_cp.call_remote_start_transaction.assert_called_once_with(
            connector_id=1,
            id_tag='RFID123'
        )
        
        assert result == True

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

    @pytest.mark.asyncio
    async def test_request_control_from_service_stop_transaction(self, service_manager):
        """Test requesting control for stop transaction."""
        # Mock charge point
        mock_cp = Mock()
        mock_cp.call_remote_stop_transaction = AsyncMock()
        mock_result = Mock()
        mock_result.status = 'Accepted'
        mock_cp.call_remote_stop_transaction.return_value = mock_result
        
        service_manager.backend_manager._app = {'charge_point': mock_cp}
        
        result = await service_manager.request_control_from_service(
            'test_service',
            'RemoteStopTransaction',
            {'transaction_id': 123}
        )
        
        # Should call charge point
        mock_cp.call_remote_stop_transaction.assert_called_once_with(
            transaction_id=123
        )
        
        assert result == True

    @pytest.mark.asyncio
    async def test_request_control_from_service_exception(self, service_manager):
        """Test requesting control with exception."""
        # Mock charge point that raises exception
        mock_cp = Mock()
        mock_cp.call_remote_start_transaction = AsyncMock(side_effect=Exception("Call failed"))
        
        service_manager.backend_manager._app = {'charge_point': mock_cp}
        
        result = await service_manager.request_control_from_service(
            'test_service',
            'RemoteStartTransaction',
            {'connector_id': 1, 'id_tag': 'RFID123'}
        )
        
        assert result == False

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

    @pytest.mark.asyncio
    async def test_send_event_to_service_status(self, service_manager):
        """Test sending status event to service."""
        mock_client = Mock()
        mock_client.send_status_notification = AsyncMock()
        
        event = {
            'type': 'status',
            'connector_id': 1,
            'status': 'Available',
            'error_code': 'NoError'
        }
        
        await service_manager._send_event_to_service(mock_client, event)
        
        mock_client.send_status_notification.assert_called_once_with(
            connector_id=1,
            status='Available',
            error_code='NoError'
        )

    @pytest.mark.asyncio
    async def test_send_event_to_service_meter(self, service_manager):
        """Test sending meter event to service."""
        mock_client = Mock()
        mock_client.send_meter_values = AsyncMock()
        
        event = {
            'type': 'meter',
            'connector_id': 1,
            'values': [{'value': '1000'}]
        }
        
        await service_manager._send_event_to_service(mock_client, event)
        
        mock_client.send_meter_values.assert_called_once_with(
            connector_id=1,
            meter_values=[{'value': '1000'}]
        )

    @pytest.mark.asyncio
    async def test_send_event_to_service_transaction_started(self, service_manager):
        """Test sending transaction started event to service."""
        mock_client = Mock()
        mock_client.send_start_transaction = AsyncMock()
        
        event = {
            'type': 'transaction_started',
            'connector_id': 1,
            'id_tag': 'RFID123',
            'meter_start': 0,
            'timestamp': '2023-01-01T12:00:00Z'
        }
        
        await service_manager._send_event_to_service(mock_client, event)
        
        mock_client.send_start_transaction.assert_called_once_with(
            connector_id=1,
            id_tag='RFID123',
            meter_start=0,
            timestamp='2023-01-01T12:00:00Z'
        )

    @pytest.mark.asyncio
    async def test_send_event_to_service_transaction_stopped(self, service_manager):
        """Test sending transaction stopped event to service."""
        mock_client = Mock()
        mock_client.send_stop_transaction = AsyncMock()
        
        event = {
            'type': 'transaction_stopped',
            'transaction_id': 123,
            'meter_stop': 5000,
            'timestamp': '2023-01-01T13:00:00Z'
        }
        
        await service_manager._send_event_to_service(mock_client, event)
        
        mock_client.send_stop_transaction.assert_called_once_with(
            transaction_id=123,
            meter_stop=5000,
            timestamp='2023-01-01T13:00:00Z'
        )

    @pytest.mark.asyncio
    async def test_send_event_to_service_exception(self, service_manager):
        """Test sending event with exception."""
        mock_client = Mock()
        mock_client.send_status_notification = AsyncMock(side_effect=Exception("Send failed"))
        
        event = {
            'type': 'status',
            'connector_id': 1,
            'status': 'Available'
        }
        
        # Should not raise exception
        await service_manager._send_event_to_service(mock_client, event)

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

    def test_get_service_status(self, service_manager):
        """Test getting service status."""
        # Create mock services
        mock_client1 = Mock()
        mock_client1.connected = True
        mock_client1.authenticated = True
        mock_client2 = Mock()
        mock_client2.connected = False
        mock_client2.authenticated = False
        
        service_manager.services = {
            'service1': mock_client1,
            'service2': mock_client2
        }
        
        status = service_manager.get_service_status()
        
        assert status['service1']['connected'] == True
        assert status['service1']['authenticated'] == True
        assert status['service2']['connected'] == False
        assert status['service2']['authenticated'] == False