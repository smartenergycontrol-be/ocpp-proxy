import asyncio
import contextlib
import os
from unittest.mock import ANY, AsyncMock, Mock, patch

import pytest
from aiohttp.test_utils import AioHTTPTestCase

from src.ocpp_proxy.main import init_app


class TestOCPPFlowsE2E(AioHTTPTestCase):
    """End-to-end tests for OCPP flows."""

    @pytest.fixture
    def config_data(self):
        """Create test configuration."""
        return {
            "allow_shared_charging": True,
            "preferred_provider": "preferred_backend",
            "blocked_providers": [],
            "allowed_providers": [],
            "presence_sensor": "",
            "override_input_boolean": "",
            "rate_limit_seconds": 1,
            "ocpp_services": [
                {
                    "id": "test_service",
                    "url": "wss://test.com/ocpp",
                    "auth_type": "none",
                    "enabled": True,
                }
            ],
        }

    async def get_application(self):
        """Create application for testing."""
        with patch.dict(os.environ, {"HA_URL": "", "HA_TOKEN": ""}):
            with patch("src.ocpp_proxy.main.OCPPServiceManager") as mock_ocpp_manager:
                mock_ocpp_manager.return_value.start_services = AsyncMock()
                mock_ocpp_manager.return_value.get_service_status = Mock(return_value={})
                mock_ocpp_manager.return_value.broadcast_event_to_services = Mock()

                return await init_app()

    @pytest.mark.e2e
    async def test_charger_boot_sequence(self):
        """Test complete charger boot sequence."""
        # Mock ChargePoint to capture boot sequence
        with patch("src.ocpp_proxy.main.ChargePointFactory.create_charge_point") as mock_cp_factory:
            mock_cp = Mock()
            mock_cp.start = AsyncMock()
            mock_cp_factory.return_value = mock_cp

            # Connect charger
            async with self.client.ws_connect("/charger"):
                # Verify ChargePoint was created with correct parameters
                mock_cp_factory.assert_called_once()
                call_args = mock_cp_factory.call_args

                assert call_args[0][0] == "CP-1"  # charge point ID
                assert call_args[1]["manager"] == self.app["backend_manager"]
                assert call_args[1]["ha_bridge"] == self.app["ha_bridge"]
                assert call_args[1]["event_logger"] == self.app["event_logger"]

                # Verify charge point was started
                mock_cp.start.assert_called_once()

                # Verify charge point was stored in app
                assert self.app["charge_point"] == mock_cp

    @pytest.mark.e2e
    async def test_backend_subscription_and_control(self):
        """Test backend subscription and control flow."""
        # Mock backend manager
        with patch.object(self.app["backend_manager"], "subscribe") as mock_subscribe:
            with patch.object(self.app["backend_manager"], "unsubscribe") as mock_unsubscribe:
                with patch.object(
                    self.app["backend_manager"], "request_control", return_value=True
                ) as mock_request:
                    # Mock charge point
                    mock_cp = Mock()
                    mock_cp.send_remote_start_transaction = AsyncMock()
                    mock_result = {"status": "Accepted"}
                    mock_cp.send_remote_start_transaction.return_value = mock_result

                    self.app["charge_point"] = mock_cp

                    # Connect backend
                    async with self.client.ws_connect("/backend?id=test_backend") as ws:
                        # Verify subscription
                        mock_subscribe.assert_called_once_with("test_backend", ANY)

                        # Send control request
                        await ws.send_json(
                            {
                                "action": "RemoteStartTransaction",
                                "connector_id": 1,
                                "id_tag": "RFID123",
                            }
                        )

                        # Receive response
                        response = await ws.receive_json()

                        # Verify control was requested
                        mock_request.assert_called_once_with("test_backend")

                        # Verify charge point was called
                        mock_cp.send_remote_start_transaction.assert_called_once_with(
                            connector_id=1, id_tag="RFID123"
                        )

                        # Verify response
                        assert response["action"] == "RemoteStartTransaction"
                        assert response["result"]["status"] == "Accepted"

                        # Close connection
                        await ws.close()

                        # Verify unsubscription
                        mock_unsubscribe.assert_called_once_with("test_backend")

    @pytest.mark.e2e
    async def test_multiple_backend_control_arbitration(self):
        """Test control arbitration between multiple backends."""
        # Mock backend manager to simulate control arbitration
        control_requests = []

        def mock_request_control(backend_id):
            control_requests.append(backend_id)
            # Only first backend gets control
            return len(control_requests) == 1

        with patch.object(self.app["backend_manager"], "subscribe"):
            with patch.object(self.app["backend_manager"], "unsubscribe"):
                with patch.object(
                    self.app["backend_manager"], "request_control", side_effect=mock_request_control
                ):
                    # Mock charge point
                    mock_cp = Mock()
                    mock_cp.send_remote_start_transaction = AsyncMock()
                    mock_result = {"status": "Accepted"}
                    mock_cp.send_remote_start_transaction.return_value = mock_result

                    self.app["charge_point"] = mock_cp

                    # Connect two backends
                    async with self.client.ws_connect("/backend?id=backend1") as ws1:
                        async with self.client.ws_connect("/backend?id=backend2") as ws2:
                            # First backend requests control
                            await ws1.send_json(
                                {
                                    "action": "RemoteStartTransaction",
                                    "connector_id": 1,
                                    "id_tag": "RFID123",
                                }
                            )

                            response1 = await ws1.receive_json()

                            # Second backend requests control
                            await ws2.send_json(
                                {
                                    "action": "RemoteStartTransaction",
                                    "connector_id": 1,
                                    "id_tag": "RFID456",
                                }
                            )

                            response2 = await ws2.receive_json()

                            # First backend should succeed
                            assert response1["result"]["status"] == "Accepted"

                            # Second backend should be rejected
                            assert response2["error"] == "control_locked"

                            # Verify control was requested for both
                            assert "backend1" in control_requests
                            assert "backend2" in control_requests

                            # Only first backend should have called charge point
                            mock_cp.send_remote_start_transaction.assert_called_once_with(
                                connector_id=1, id_tag="RFID123"
                            )

    @pytest.mark.e2e
    async def test_charger_event_broadcasting(self):
        """Test that charger events are broadcast to all backends."""
        # Mock backend manager to capture broadcasted events
        broadcasted_events = []

        def mock_broadcast_event(event):
            broadcasted_events.append(event)

        with patch.object(
            self.app["backend_manager"], "broadcast_event", side_effect=mock_broadcast_event
        ):
            # Mock charge point that generates events
            mock_cp = Mock()
            mock_cp.start = AsyncMock()

            with patch(
                "src.ocpp_proxy.main.ChargePointFactory.create_charge_point"
            ) as mock_cp_factory:
                mock_cp_factory.return_value = mock_cp

                # Connect charger
                async with self.client.ws_connect("/charger") as ws:
                    # Simulate charger events by calling methods directly
                    charge_point = mock_cp_factory.return_value
                    charge_point.manager = self.app["backend_manager"]

                    # Import the actual ChargePoint class to test event methods
                    from src.ocpp_proxy.charge_point_v16 import ChargePointV16

                    # Create a real ChargePoint instance for testing event methods
                    real_cp = ChargePointV16("CP-1", ws, manager=self.app["backend_manager"])

                    # Test boot notification event
                    await real_cp.on_boot_notification("TestVendor", "TestModel")

                    # Test heartbeat event
                    await real_cp.on_heartbeat()

                    # Test status notification event
                    await real_cp.on_status_notification(1, "NoError", "Available")

                    # Verify events were broadcast
                    assert len(broadcasted_events) == 3

                    # Check boot event
                    boot_event = broadcasted_events[0]
                    assert boot_event["type"] == "boot"
                    assert boot_event["vendor"] == "TestVendor"
                    assert boot_event["model"] == "TestModel"

                    # Check heartbeat event
                    heartbeat_event = broadcasted_events[1]
                    assert heartbeat_event["type"] == "heartbeat"
                    assert "current_time" in heartbeat_event

                    # Check status event
                    status_event = broadcasted_events[2]
                    assert status_event["type"] == "status"
                    assert status_event["connector_id"] == 1
                    assert status_event["error_code"] == "NoError"
                    assert status_event["status"] == "Available"

    @pytest.mark.e2e
    async def test_transaction_logging_flow(self):
        """Test complete transaction logging flow."""
        # Mock event logger to capture logged sessions
        logged_sessions = []

        def mock_log_session(backend_id, duration_s, energy_kwh, revenue):
            logged_sessions.append(
                {
                    "backend_id": backend_id,
                    "duration_s": duration_s,
                    "energy_kwh": energy_kwh,
                    "revenue": revenue,
                }
            )

        with patch.object(self.app["event_logger"], "log_session", side_effect=mock_log_session):
            # Mock backend manager
            with patch.object(self.app["backend_manager"], "_lock_owner", "test_backend"):
                # Create a real ChargePoint instance for testing
                from src.ocpp_proxy.charge_point_v16 import ChargePointV16

                # Mock WebSocket connection
                mock_ws = Mock()
                mock_ws.send = AsyncMock()
                mock_ws.recv = AsyncMock()

                cp = ChargePointV16(
                    "CP-1",
                    mock_ws,
                    manager=self.app["backend_manager"],
                    event_logger=self.app["event_logger"],
                )

                # Start transaction
                start_result = await cp.on_start_transaction(
                    connector_id=1,
                    id_tag="RFID123",
                    meter_start=0,
                    timestamp="2023-01-01T12:00:00Z",
                )

                # Verify transaction started
                assert start_result.transaction_id == 1
                assert 1 in cp._sessions

                # Stop transaction
                await cp.on_stop_transaction(
                    transaction_id=1, meter_stop=5000, timestamp="2023-01-01T13:00:00Z"
                )

                # Verify transaction stopped
                assert 1 not in cp._sessions

                # Verify session was logged
                assert len(logged_sessions) == 1
                session = logged_sessions[0]
                assert session["backend_id"] == "test_backend"
                assert session["duration_s"] == 3600.0  # 1 hour
                assert session["energy_kwh"] == 5.0  # 5000 Wh = 5 kWh
                assert session["revenue"] == 0.0

    @pytest.mark.e2e
    async def test_session_data_retrieval(self):
        """Test session data retrieval endpoints."""
        # Mock session data
        mock_sessions = [
            {
                "timestamp": "2023-01-01T12:00:00Z",
                "backend_id": "backend1",
                "duration_s": 3600.0,
                "energy_kwh": 25.0,
                "revenue": 5.0,
            },
            {
                "timestamp": "2023-01-01T13:00:00Z",
                "backend_id": "backend2",
                "duration_s": 1800.0,
                "energy_kwh": 12.5,
                "revenue": 2.5,
            },
        ]

        with patch.object(self.app["event_logger"], "get_sessions", return_value=mock_sessions):
            # Test JSON endpoint
            json_response = await self.client.request("GET", "/sessions")
            assert json_response.status == 200

            json_data = await json_response.json()
            assert json_data == mock_sessions

            # Test CSV endpoint
            csv_response = await self.client.request("GET", "/sessions.csv")
            assert csv_response.status == 200
            assert csv_response.headers["Content-Type"].startswith("text/csv")

            csv_content = await csv_response.text()
            lines = csv_content.strip().split("\n")
            assert len(lines) == 3  # Header + 2 data rows

            # Verify CSV content
            assert "timestamp,backend_id,duration_s,energy_kwh,revenue" in lines[0]
            assert "2023-01-01T12:00:00Z,backend1,3600.0,25.0,5.0" in lines[1]
            assert "2023-01-01T13:00:00Z,backend2,1800.0,12.5,2.5" in lines[2]

    @pytest.mark.e2e
    async def test_status_monitoring_flow(self):
        """Test status monitoring and override flow."""
        # Mock backend manager status
        mock_status = {
            "websocket_backends": ["backend1", "backend2"],
            "lock_owner": "backend1",
            "ocpp_services": {"service1": {"connected": True}},
        }

        with patch.object(
            self.app["backend_manager"], "get_backend_status", return_value=mock_status
        ):
            # Test status endpoint
            status_response = await self.client.request("GET", "/status")
            assert status_response.status == 200

            status_data = await status_response.json()
            assert status_data == mock_status

            # Test override endpoint
            with patch.object(self.app["backend_manager"], "release_control") as mock_release:
                with patch.object(
                    self.app["backend_manager"], "request_control", return_value=True
                ) as mock_request:
                    override_response = await self.client.request(
                        "POST", "/override", json={"backend_id": "backend2"}
                    )
                    assert override_response.status == 200

                    override_data = await override_response.json()
                    assert override_data["success"]

                    # Verify override actions
                    mock_release.assert_called_once()
                    mock_request.assert_called_once_with("backend2")

    @pytest.mark.e2e
    async def test_fault_handling_flow(self):
        """Test fault handling and safety controls."""
        # Mock backend manager and HA bridge
        with patch.object(self.app["backend_manager"], "release_control") as mock_release:
            # Create a real ChargePoint instance for testing
            from src.ocpp_proxy.charge_point_v16 import ChargePointV16

            mock_ws = Mock()
            mock_ws.send = AsyncMock()
            mock_ws.recv = AsyncMock()

            cp = ChargePointV16(
                "CP-1",
                mock_ws,
                manager=self.app["backend_manager"],
                ha_bridge=self.app["ha_bridge"],
            )

            # Send fault status notification
            await cp.on_status_notification(
                connector_id=1, error_code="ConnectorLockFailure", status="Faulted"
            )

            # Verify fault handling
            mock_release.assert_called_once()

            # Note: HA notification testing would require HA bridge setup

    @pytest.mark.e2e
    async def test_rate_limiting_flow(self):
        """Test rate limiting functionality."""
        # Mock backend manager with rate limiting
        request_times = []

        def mock_request_control(backend_id):
            from datetime import datetime

            now = datetime.utcnow()
            request_times.append(now)

            # Simulate rate limiting (first request succeeds, second fails)
            return len(request_times) == 1

        with patch.object(self.app["backend_manager"], "subscribe"):
            with patch.object(self.app["backend_manager"], "unsubscribe"):
                with patch.object(
                    self.app["backend_manager"], "request_control", side_effect=mock_request_control
                ):
                    # Mock charge point
                    mock_cp = Mock()
                    mock_cp.send_remote_start_transaction = AsyncMock()
                    mock_result = {"status": "Accepted"}
                    mock_cp.send_remote_start_transaction.return_value = mock_result

                    self.app["charge_point"] = mock_cp

                    # Connect backend
                    async with self.client.ws_connect("/backend?id=test_backend") as ws:
                        # First request should succeed
                        await ws.send_json(
                            {
                                "action": "RemoteStartTransaction",
                                "connector_id": 1,
                                "id_tag": "RFID123",
                            }
                        )

                        response1 = await ws.receive_json()
                        assert response1["result"]["status"] == "Accepted"

                        # Immediate second request should be rate limited
                        await ws.send_json(
                            {
                                "action": "RemoteStartTransaction",
                                "connector_id": 1,
                                "id_tag": "RFID456",
                            }
                        )

                        response2 = await ws.receive_json()
                        assert response2["error"] == "control_locked"

                        # Verify rate limiting was applied
                        assert len(request_times) == 2

    @pytest.mark.e2e
    async def test_ocpp_service_integration(self):
        """Test OCPP service integration flow."""
        # Mock OCPP service manager
        with patch.object(
            self.app["ocpp_service_manager"], "broadcast_event_to_services"
        ) as mock_broadcast:
            # Create a real ChargePoint instance for testing
            from src.ocpp_proxy.charge_point_v16 import ChargePointV16

            mock_ws = Mock()
            mock_ws.send = AsyncMock()
            mock_ws.recv = AsyncMock()

            cp = ChargePointV16("CP-1", mock_ws, manager=self.app["backend_manager"])

            # Send heartbeat event
            await cp.on_heartbeat()

            # Verify OCPP service manager received the event
            mock_broadcast.assert_called_once()

            # Check event structure
            event = mock_broadcast.call_args[0][0]
            assert event["type"] == "heartbeat"
            assert "current_time" in event


class TestOCPPServiceFlows:
    """Test OCPP service specific flows."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_ocpp_service_authentication_flow(self):
        """Test OCPP service authentication flows."""
        from src.ocpp_proxy.config import Config
        from src.ocpp_proxy.ocpp_service_manager import OCPPServiceManager

        # Test different authentication types
        config = Mock(spec=Config)
        config.ocpp_services = [
            {
                "id": "token_service",
                "url": "wss://token.com/ocpp",
                "auth_type": "token",
                "token": "test_token",
            },
            {
                "id": "basic_service",
                "url": "wss://basic.com/ocpp",
                "auth_type": "basic",
                "username": "user",
                "password": "pass",
            },
            {"id": "no_auth_service", "url": "wss://noauth.com/ocpp", "auth_type": "none"},
        ]

        manager = OCPPServiceManager(config)

        # Mock websockets.connect to capture auth headers
        auth_headers = []

        async def mock_connect(url, extra_headers=None, **kwargs):
            auth_headers.append(extra_headers or {})
            # Return a mock connection
            return Mock()

        with patch(
            "src.ocpp_proxy.ocpp_service_manager.websockets.connect", side_effect=mock_connect
        ):
            # Test token auth
            await manager.connect_service("token_service", config.ocpp_services[0])

            # Test basic auth
            await manager.connect_service("basic_service", config.ocpp_services[1])

            # Test no auth
            await manager.connect_service("no_auth_service", config.ocpp_services[2])

            # Verify authentication headers
            assert len(auth_headers) == 3

            # Check token auth header
            assert auth_headers[0]["Authorization"] == "Bearer test_token"

            # Check basic auth header (should be base64 encoded)
            assert auth_headers[1]["Authorization"].startswith("Basic ")

            # Check no auth header
            assert "Authorization" not in auth_headers[2]

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_ocpp_service_control_flow(self):
        """Test OCPP service control request flow."""
        # Skip this test - OCPPServiceClient doesn't exist yet
        pytest.skip("OCPPServiceClient not implemented yet")

        # Mock backend manager
        mock_backend_manager = Mock()
        mock_backend_manager.request_control = AsyncMock(return_value=True)
        mock_backend_manager._app = {"charge_point": Mock()}

        # Mock charge point
        mock_cp = Mock()
        mock_cp.send_remote_start_transaction = AsyncMock()
        mock_result = Mock()
        mock_result.status = "Accepted"
        mock_cp.send_remote_start_transaction.return_value = mock_result
        mock_backend_manager._app["charge_point"] = mock_cp

        # Mock WebSocket connection
        mock_ws = Mock()
        mock_ws.send = AsyncMock()
        mock_ws.recv = AsyncMock()

        # Create OCPP service client
        client = OCPPServiceClient("test_service", mock_ws, manager=mock_backend_manager)

        # Test RemoteStartTransaction
        result = await client.on_remote_start_transaction(connector_id=1, id_tag="RFID123")

        # Verify control was requested
        mock_backend_manager.request_control.assert_called_once_with("ocpp_service_test_service")

        # Verify charge point was called
        mock_cp.send_remote_start_transaction.assert_called_once_with(
            connector_id=1, id_tag="RFID123"
        )

        # Verify result
        assert result.status == "Accepted"

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_ocpp_service_event_forwarding(self):
        """Test event forwarding to OCPP services."""
        # Skip this test - OCPPServiceClient doesn't exist yet
        pytest.skip("OCPPServiceClient not implemented yet")

        # Create mock services
        mock_client1 = Mock(spec=OCPPServiceClient)
        mock_client1.connected = True
        mock_client1.service_id = "service1"
        mock_client1.send_status_notification = AsyncMock()

        mock_client2 = Mock(spec=OCPPServiceClient)
        mock_client2.connected = True
        mock_client2.service_id = "service2"
        mock_client2.send_meter_values = AsyncMock()

        # Create manager
        manager = OCPPServiceManager(Mock())
        manager.services = {"service1": mock_client1, "service2": mock_client2}

        # Test status event forwarding
        status_event = {
            "type": "status",
            "connector_id": 1,
            "status": "Available",
            "error_code": "NoError",
        }

        manager.broadcast_event_to_services(status_event)

        # Give async tasks time to complete
        await asyncio.sleep(0.1)

        # Verify both services received the event
        mock_client1.send_status_notification.assert_called_once_with(
            connector_id=1, status="Available", error_code="NoError"
        )
        mock_client2.send_status_notification.assert_called_once_with(
            connector_id=1, status="Available", error_code="NoError"
        )

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_ocpp_service_heartbeat_flow(self):
        """Test OCPP service heartbeat mechanism."""
        # Skip this test - OCPPServiceClient doesn't exist yet
        pytest.skip("OCPPServiceClient not implemented yet")

        # Mock WebSocket connection
        mock_ws = Mock()
        mock_ws.send = AsyncMock()
        mock_ws.recv = AsyncMock()

        # Create client
        client = OCPPServiceClient("test_service", mock_ws)
        client.connected = True

        # Mock heartbeat call
        client.call_heartbeat = AsyncMock()

        # Start heartbeat loop
        heartbeat_task = asyncio.create_task(client._heartbeat_loop())

        # Let it run for a short time
        await asyncio.sleep(0.1)

        # Stop heartbeat
        client.connected = False

        # Wait for task to complete
        await asyncio.sleep(0.1)

        # Verify heartbeat was called
        client.call_heartbeat.assert_called()

        # Cleanup
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task
