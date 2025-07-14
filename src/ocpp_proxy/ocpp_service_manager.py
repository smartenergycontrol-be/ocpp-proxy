import asyncio
import logging
from typing import Dict, Optional, Any
from aiohttp import ClientSession, WSMsgType
import datetime
import websockets
import json
from .charge_point_factory import OCPPServiceFactory

_LOGGER = logging.getLogger(__name__)


class OCPPServiceManager:
    """
    Manages outbound connections to OCPP services.
    Handles authentication, connection lifecycle, and message routing.
    Supports both OCPP 1.6 and 2.0.1 versions.
    """

    def __init__(self, config, backend_manager=None):
        self.config = config
        self.backend_manager = backend_manager
        self.services: Dict[str, Any] = {}
        self._connection_tasks: Dict[str, asyncio.Task] = {}

    async def start_services(self):
        """Start connections to all configured OCPP services."""
        if not hasattr(self.config, 'ocpp_services'):
            _LOGGER.info('No OCPP services configured')
            return

        for service_config in self.config.ocpp_services:
            service_id = service_config.get('id')
            if service_id and service_config.get('enabled', True):
                await self.connect_service(service_id, service_config)

    async def connect_service(self, service_id: str, service_config: dict):
        """Connect to a specific OCPP service."""
        try:
            url = service_config.get('url')
            if not url:
                _LOGGER.error(f'No URL configured for OCPP service {service_id}')
                return

            # Determine OCPP version (default to 1.6 if not specified)
            version = service_config.get('version', '1.6')
            
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

            # Set WebSocket subprotocol based on version
            subprotocols = []
            if version == '1.6':
                subprotocols = ['ocpp1.6']
            elif version == '2.0.1':
                subprotocols = ['ocpp2.0.1']

            # Create WebSocket connection
            connection = await websockets.connect(
                url,
                extra_headers=auth_headers,
                subprotocols=subprotocols,
                ping_interval=30,
                ping_timeout=10
            )

            # Create OCPP client using factory
            client = OCPPServiceFactory.create_service_client(
                service_id, connection, version, manager=self
            )
            self.services[service_id] = client

            # Start the client in a background task
            task = asyncio.create_task(client.start())
            self._connection_tasks[service_id] = task

            _LOGGER.info(f'Connecting to OCPP {version} service {service_id} at {url}')

        except Exception as e:
            _LOGGER.error(f'Failed to connect to OCPP service {service_id}: {e}')

    async def disconnect_service(self, service_id: str):
        """Disconnect from a specific OCPP service."""
        if service_id in self.services:
            client = self.services[service_id]
            
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
                        result = await cp.send_remote_start_transaction(
                            connector_id=params.get('connector_id', 1),
                            id_tag=params.get('id_tag')
                        )
                        return result
                    elif action == 'RemoteStopTransaction':
                        result = await cp.send_remote_stop_transaction(
                            transaction_id=params.get('transaction_id')
                        )
                        return result
                except Exception as e:
                    _LOGGER.error(f'Error forwarding {action} from service {service_id}: {e}')
        
        return False

    def broadcast_event_to_services(self, event: dict):
        """Broadcast charger events to all connected OCPP services."""
        for service_id, client in self.services.items():
            if hasattr(client, 'connected') and client.connected:
                asyncio.create_task(self._send_event_to_service(client, event))

    async def _send_event_to_service(self, client: Any, event: dict):
        """Send a specific event to an OCPP service."""
        try:
            event_type = event.get('type')
            
            # The ChargePoint implementations handle the actual message sending
            # We just need to forward the events to the service clients
            if event_type == 'status':
                # Services receive status updates passively
                pass
            elif event_type == 'meter':
                # Services receive meter values passively
                pass
            elif event_type == 'transaction_started':
                # Services receive transaction events passively
                pass
            elif event_type == 'transaction_stopped':
                # Services receive transaction events passively
                pass
            elif event_type == 'heartbeat':
                # Services receive heartbeat events passively
                pass
            elif event_type == 'boot':
                # Services receive boot notifications passively
                pass
                
        except Exception as e:
            _LOGGER.error(f'Error sending event to service {getattr(client, "service_id", "unknown")}: {e}')

    async def stop_all_services(self):
        """Stop all OCPP service connections."""
        for service_id in list(self.services.keys()):
            await self.disconnect_service(service_id)

    def get_service_status(self) -> dict:
        """Get status of all OCPP services."""
        status = {}
        for service_id, client in self.services.items():
            status[service_id] = {
                'connected': getattr(client, 'connected', False),
                'authenticated': getattr(client, 'authenticated', False),
                'version': getattr(client, 'ocpp_version', 'unknown')
            }
        return status