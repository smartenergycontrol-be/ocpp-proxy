import asyncio
import logging
from typing import Dict, Optional, Any
from aiohttp import ClientSession, WSMsgType
from ocpp.v16 import ChargePoint as OCPPChargePoint, call, call_result
from ocpp.v16.enums import RegistrationStatus, AuthorizationStatus
from ocpp.routing import on
import datetime
import websockets
import json

_LOGGER = logging.getLogger(__name__)


class OCPPServiceClient(OCPPChargePoint):
    """
    OCPP 1.6 client that connects to external OCPP services.
    Acts as a charge point connecting to a Central System (CSMS).
    """

    def __init__(self, service_id: str, connection, manager=None):
        super().__init__(service_id, connection)
        self.service_id = service_id
        self.manager = manager
        self.connected = False
        self.authenticated = False

    async def start(self):
        """Start the OCPP client connection and perform boot notification."""
        try:
            # Send BootNotification to establish connection
            response = await self.call_boot_notification(
                charge_point_model='EVProxy', 
                charge_point_vendor='OCPPProxy'
            )
            
            if response.status == RegistrationStatus.accepted:
                self.connected = True
                self.authenticated = True
                _LOGGER.info(f'OCPP service {self.service_id} connected successfully')
                
                # Start heartbeat
                asyncio.create_task(self._heartbeat_loop())
                
                # Listen for incoming messages
                await self.start_listening()
            else:
                _LOGGER.error(f'OCPP service {self.service_id} registration rejected: {response.status}')
                
        except Exception as e:
            _LOGGER.error(f'Failed to start OCPP service {self.service_id}: {e}')
            self.connected = False
            self.authenticated = False

    async def _heartbeat_loop(self):
        """Send periodic heartbeat messages to maintain connection."""
        while self.connected:
            try:
                await asyncio.sleep(30)  # Send heartbeat every 30 seconds
                await self.call_heartbeat()
            except Exception as e:
                _LOGGER.error(f'Heartbeat failed for service {self.service_id}: {e}')
                self.connected = False
                break

    async def start_listening(self):
        """Listen for incoming messages from the OCPP service."""
        try:
            await self.start()
        except Exception as e:
            _LOGGER.error(f'Error listening to OCPP service {self.service_id}: {e}')
            self.connected = False

    # Handle incoming OCPP commands from the service
    @on('RemoteStartTransaction')
    async def on_remote_start_transaction(self, connector_id, id_tag, **kwargs):
        """Handle RemoteStartTransaction request from OCPP service."""
        _LOGGER.info(f'Service {self.service_id} requesting remote start: connector={connector_id}, id_tag={id_tag}')
        
        if self.manager:
            # Request control through the manager
            success = await self.manager.request_control_from_service(
                self.service_id, 'RemoteStartTransaction', {
                    'connector_id': connector_id,
                    'id_tag': id_tag,
                    **kwargs
                }
            )
            
            if success:
                return call_result.RemoteStartTransaction(
                    status='Accepted'
                )
            else:
                return call_result.RemoteStartTransaction(
                    status='Rejected'
                )
        
        return call_result.RemoteStartTransaction(status='Rejected')

    @on('RemoteStopTransaction')
    async def on_remote_stop_transaction(self, transaction_id, **kwargs):
        """Handle RemoteStopTransaction request from OCPP service."""
        _LOGGER.info(f'Service {self.service_id} requesting remote stop: transaction_id={transaction_id}')
        
        if self.manager:
            success = await self.manager.request_control_from_service(
                self.service_id, 'RemoteStopTransaction', {
                    'transaction_id': transaction_id,
                    **kwargs
                }
            )
            
            if success:
                return call_result.RemoteStopTransaction(
                    status='Accepted'
                )
            else:
                return call_result.RemoteStopTransaction(
                    status='Rejected'
                )
        
        return call_result.RemoteStopTransaction(status='Rejected')

    async def send_status_notification(self, connector_id, status, error_code='NoError'):
        """Send status notification to the OCPP service."""
        try:
            await self.call_status_notification(
                connector_id=connector_id,
                status=status,
                error_code=error_code
            )
        except Exception as e:
            _LOGGER.error(f'Failed to send status notification to {self.service_id}: {e}')

    async def send_meter_values(self, connector_id, meter_values):
        """Send meter values to the OCPP service."""
        try:
            await self.call_meter_values(
                connector_id=connector_id,
                meter_value=meter_values
            )
        except Exception as e:
            _LOGGER.error(f'Failed to send meter values to {self.service_id}: {e}')

    async def send_start_transaction(self, connector_id, id_tag, meter_start, timestamp):
        """Send start transaction to the OCPP service."""
        try:
            response = await self.call_start_transaction(
                connector_id=connector_id,
                id_tag=id_tag,
                meter_start=meter_start,
                timestamp=timestamp
            )
            return response
        except Exception as e:
            _LOGGER.error(f'Failed to send start transaction to {self.service_id}: {e}')
            return None

    async def send_stop_transaction(self, transaction_id, meter_stop, timestamp):
        """Send stop transaction to the OCPP service."""
        try:
            response = await self.call_stop_transaction(
                transaction_id=transaction_id,
                meter_stop=meter_stop,
                timestamp=timestamp
            )
            return response
        except Exception as e:
            _LOGGER.error(f'Failed to send stop transaction to {self.service_id}: {e}')
            return None


class OCPPServiceManager:
    """
    Manages outbound connections to OCPP services.
    Handles authentication, connection lifecycle, and message routing.
    """

    def __init__(self, config, backend_manager=None):
        self.config = config
        self.backend_manager = backend_manager
        self.services: Dict[str, OCPPServiceClient] = {}
        self._connection_tasks: Dict[str, asyncio.Task] = {}

    async def start_services(self):
        """Start connections to all configured OCPP services."""
        if not hasattr(self.config, 'ocpp_services'):
            _LOGGER.info('No OCPP services configured')
            return

        for service_config in self.config.ocpp_services:
            service_id = service_config.get('id')
            if service_id:
                await self.connect_service(service_id, service_config)

    async def connect_service(self, service_id: str, service_config: dict):
        """Connect to a specific OCPP service."""
        try:
            url = service_config.get('url')
            if not url:
                _LOGGER.error(f'No URL configured for OCPP service {service_id}')
                return

            # Handle authentication
            auth_headers = {}
            if service_config.get('auth_type') == 'basic':
                username = service_config.get('username')
                password = service_config.get('password')
                if username and password:
                    import base64
                    credentials = base64.b64encode(f'{username}:{password}'.encode()).decode()
                    auth_headers['Authorization'] = f'Basic {credentials}'
            elif service_config.get('auth_type') == 'token':
                token = service_config.get('token')
                if token:
                    auth_headers['Authorization'] = f'Bearer {token}'

            # Create WebSocket connection
            connection = await websockets.connect(
                url,
                extra_headers=auth_headers,
                ping_interval=30,
                ping_timeout=10
            )

            # Create OCPP client
            client = OCPPServiceClient(service_id, connection, manager=self)
            self.services[service_id] = client

            # Start the client in a background task
            task = asyncio.create_task(client.start())
            self._connection_tasks[service_id] = task

            _LOGGER.info(f'Connecting to OCPP service {service_id} at {url}')

        except Exception as e:
            _LOGGER.error(f'Failed to connect to OCPP service {service_id}: {e}')

    async def disconnect_service(self, service_id: str):
        """Disconnect from a specific OCPP service."""
        if service_id in self.services:
            client = self.services[service_id]
            client.connected = False
            
            # Cancel connection task
            if service_id in self._connection_tasks:
                self._connection_tasks[service_id].cancel()
                del self._connection_tasks[service_id]
            
            # Close WebSocket connection
            if hasattr(client, '_connection'):
                await client._connection.close()
            
            del self.services[service_id]
            _LOGGER.info(f'Disconnected from OCPP service {service_id}')

    async def request_control_from_service(self, service_id: str, action: str, params: dict) -> bool:
        """Handle control request from an OCPP service."""
        if not self.backend_manager:
            return False

        # Treat OCPP services as special backend clients
        success = await self.backend_manager.request_control(f'ocpp_service_{service_id}')
        
        if success and hasattr(self.backend_manager, '_app'):
            # Forward the request to the charge point
            cp = self.backend_manager._app.get('charge_point')
            if cp:
                try:
                    if action == 'RemoteStartTransaction':
                        result = await cp.call_remote_start_transaction(
                            connector_id=params.get('connector_id', 1),
                            id_tag=params.get('id_tag')
                        )
                        return result.status == 'Accepted'
                    elif action == 'RemoteStopTransaction':
                        result = await cp.call_remote_stop_transaction(
                            transaction_id=params.get('transaction_id')
                        )
                        return result.status == 'Accepted'
                except Exception as e:
                    _LOGGER.error(f'Error forwarding {action} from service {service_id}: {e}')
        
        return False

    def broadcast_event_to_services(self, event: dict):
        """Broadcast charger events to all connected OCPP services."""
        for service_id, client in self.services.items():
            if client.connected:
                asyncio.create_task(self._send_event_to_service(client, event))

    async def _send_event_to_service(self, client: OCPPServiceClient, event: dict):
        """Send a specific event to an OCPP service."""
        try:
            event_type = event.get('type')
            
            if event_type == 'status':
                await client.send_status_notification(
                    connector_id=event.get('connector_id', 1),
                    status=event.get('status'),
                    error_code=event.get('error_code', 'NoError')
                )
            elif event_type == 'meter':
                await client.send_meter_values(
                    connector_id=event.get('connector_id', 1),
                    meter_values=event.get('values', [])
                )
            elif event_type == 'transaction_started':
                await client.send_start_transaction(
                    connector_id=event.get('connector_id', 1),
                    id_tag=event.get('id_tag'),
                    meter_start=event.get('meter_start', 0),
                    timestamp=event.get('timestamp')
                )
            elif event_type == 'transaction_stopped':
                await client.send_stop_transaction(
                    transaction_id=event.get('transaction_id'),
                    meter_stop=event.get('meter_stop', 0),
                    timestamp=event.get('timestamp')
                )
                
        except Exception as e:
            _LOGGER.error(f'Error sending event to service {client.service_id}: {e}')

    async def stop_all_services(self):
        """Stop all OCPP service connections."""
        for service_id in list(self.services.keys()):
            await self.disconnect_service(service_id)

    def get_service_status(self) -> dict:
        """Get status of all OCPP services."""
        status = {}
        for service_id, client in self.services.items():
            status[service_id] = {
                'connected': client.connected,
                'authenticated': client.authenticated
            }
        return status