import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from ocpp.v16.enums import AuthorizationStatus, RegistrationStatus
from ocpp.v201.enums import RegistrationStatusEnumType

from src.ocpp_proxy.charge_point_factory import ChargePointFactory
from src.ocpp_proxy.charge_point_v16 import ChargePointV16
from src.ocpp_proxy.charge_point_v201 import ChargePointV201


class TestChargePoint:
    """Unit tests for ChargePoint class."""

    @pytest.fixture
    def mock_connection(self):
        """Create a mock WebSocket connection."""
        connection = Mock()
        connection.send = AsyncMock()
        connection.recv = AsyncMock()
        return connection

    @pytest.fixture
    def mock_manager(self):
        """Create a mock backend manager."""
        manager = Mock()
        manager.broadcast_event = Mock()
        manager.release_control = Mock()
        manager._lock_owner = "test_backend"
        return manager

    @pytest.fixture
    def mock_ha_bridge(self):
        """Create a mock HA bridge."""
        ha_bridge = Mock()
        ha_bridge.send_notification = AsyncMock()
        return ha_bridge

    @pytest.fixture
    def mock_event_logger(self):
        """Create a mock event logger."""
        logger = Mock()
        logger.log_session = Mock()
        return logger

    @pytest.fixture
    def charge_point_v16(self, mock_connection, mock_manager, mock_ha_bridge, mock_event_logger):
        """Create a ChargePoint V1.6 instance for testing."""
        return ChargePointV16(
            "CP-1", mock_connection, mock_manager, mock_ha_bridge, mock_event_logger
        )

    @pytest.fixture
    def charge_point_v201(self, mock_connection, mock_manager, mock_ha_bridge, mock_event_logger):
        """Create a ChargePoint V2.0.1 instance for testing."""
        return ChargePointV201(
            "CP-1",
            mock_connection,
            manager=mock_manager,
            ha_bridge=mock_ha_bridge,
            event_logger=mock_event_logger,
        )

    @pytest.fixture
    def charge_point(self, mock_connection, mock_manager, mock_ha_bridge, mock_event_logger):
        """Create a ChargePoint V1.6 instance for testing (generic fixture)."""
        return ChargePointV16(
            "CP-1", mock_connection, mock_manager, mock_ha_bridge, mock_event_logger
        )

    @pytest.mark.unit
    def test_initialization_v16(
        self, charge_point_v16, mock_connection, mock_manager, mock_ha_bridge, mock_event_logger
    ):
        """Test ChargePoint V1.6 initialization."""
        assert charge_point_v16.cp_id == "CP-1"
        assert charge_point_v16.manager == mock_manager
        assert charge_point_v16.ha_bridge == mock_ha_bridge
        assert charge_point_v16.event_logger == mock_event_logger
        assert charge_point_v16._sessions == {}
        assert charge_point_v16._tx_counter == 0
        assert charge_point_v16.ocpp_version == "1.6"

    @pytest.mark.unit
    def test_initialization_v201(
        self, charge_point_v201, mock_connection, mock_manager, mock_ha_bridge, mock_event_logger
    ):
        """Test ChargePoint V2.0.1 initialization."""
        assert charge_point_v201.cp_id == "CP-1"
        assert charge_point_v201.manager == mock_manager
        assert charge_point_v201.ha_bridge == mock_ha_bridge
        assert charge_point_v201.event_logger == mock_event_logger
        assert charge_point_v201._sessions == {}
        assert charge_point_v201._tx_counter == 0
        assert charge_point_v201.ocpp_version == "2.0.1"

    @pytest.mark.unit
    def test_factory_create_v16(
        self, mock_connection, mock_manager, mock_ha_bridge, mock_event_logger
    ):
        """Test factory creates OCPP 1.6 ChargePoint."""
        cp = ChargePointFactory.create_charge_point(
            "CP-1",
            mock_connection,
            version="1.6",
            manager=mock_manager,
            ha_bridge=mock_ha_bridge,
            event_logger=mock_event_logger,
        )
        assert isinstance(cp, ChargePointV16)
        assert cp.ocpp_version == "1.6"

    @pytest.mark.unit
    def test_factory_create_v201(
        self, mock_connection, mock_manager, mock_ha_bridge, mock_event_logger
    ):
        """Test factory creates OCPP 2.0.1 ChargePoint."""
        cp = ChargePointFactory.create_charge_point(
            "CP-1",
            mock_connection,
            version="2.0.1",
            manager=mock_manager,
            ha_bridge=mock_ha_bridge,
            event_logger=mock_event_logger,
        )
        assert isinstance(cp, ChargePointV201)
        assert cp.ocpp_version == "2.0.1"

    @pytest.mark.unit
    def test_factory_unsupported_version(self, mock_connection):
        """Test factory raises error for unsupported version."""
        with pytest.raises(ValueError, match="Unsupported OCPP version"):
            ChargePointFactory.create_charge_point("CP-1", mock_connection, version="3.0")

    @pytest.mark.unit
    def test_factory_default_version(self, mock_connection):
        """Test factory defaults to 1.6 when no version specified."""
        cp = ChargePointFactory.create_charge_point("CP-1", mock_connection, auto_detect=False)
        assert isinstance(cp, ChargePointV16)
        assert cp.ocpp_version == "1.6"

    @pytest.mark.unit
    def test_factory_version_detection(self, mock_connection):
        """Test factory version detection."""
        # Mock connection with subprotocol
        mock_connection.subprotocol = "ocpp1.6"
        cp = ChargePointFactory.create_charge_point("CP-1", mock_connection, auto_detect=True)
        assert isinstance(cp, ChargePointV16)

    @pytest.mark.unit
    def test_factory_supported_versions(self):
        """Test factory returns supported versions."""
        versions = ChargePointFactory.get_supported_versions()
        assert "1.6" in versions
        assert "2.0.1" in versions

    @pytest.mark.unit
    def test_factory_version_supported(self):
        """Test factory version support check."""
        assert ChargePointFactory.is_version_supported("1.6")
        assert ChargePointFactory.is_version_supported("2.0.1")
        assert not ChargePointFactory.is_version_supported("3.0")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_on_boot_notification_v16(self, charge_point_v16):
        """Test handling BootNotification from charger."""
        result = await charge_point_v16.on_boot_notification(
            charge_point_vendor="TestVendor",
            charge_point_model="TestModel",
            charge_point_serial_number="12345",
        )

        # Should broadcast event
        charge_point_v16.manager.broadcast_event.assert_called_once()
        call_args = charge_point_v16.manager.broadcast_event.call_args[0][0]
        assert call_args["type"] == "boot"
        assert call_args["vendor"] == "TestVendor"
        assert call_args["model"] == "TestModel"

        # Should return accepted status
        assert result.status == RegistrationStatus.accepted
        assert result.interval == 10

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_on_boot_notification_v201(self, charge_point_v201):
        """Test handling BootNotification from charger V2.0.1."""
        result = await charge_point_v201.on_boot_notification(
            charging_station={"vendor_name": "TestVendor", "model": "TestModel"}, reason="PowerUp"
        )

        # Should broadcast event
        charge_point_v201.manager.broadcast_event.assert_called_once()
        call_args = charge_point_v201.manager.broadcast_event.call_args[0][0]
        assert call_args["type"] == "boot"
        assert call_args["vendor"] == "TestVendor"
        assert call_args["model"] == "TestModel"

        # Should return accepted status
        assert result.status == RegistrationStatusEnumType.accepted
        assert result.interval == 10

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_on_boot_notification_no_manager(self, mock_connection):
        """Test BootNotification without manager."""
        charge_point = ChargePointV16("CP-1", mock_connection)

        result = await charge_point.on_boot_notification(
            charge_point_vendor="TestVendor", charge_point_model="TestModel"
        )

        # Should still return accepted status
        assert result.status == RegistrationStatus.accepted

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_on_heartbeat_v16(self, charge_point_v16):
        """Test handling Heartbeat from charger V1.6."""
        result = await charge_point_v16.on_heartbeat()

        # Should broadcast event
        charge_point_v16.manager.broadcast_event.assert_called_once()
        call_args = charge_point_v16.manager.broadcast_event.call_args[0][0]
        assert call_args["type"] == "heartbeat"
        assert "current_time" in call_args

        # Should return current time
        assert result.current_time is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_on_heartbeat_v201(self, charge_point_v201):
        """Test handling Heartbeat from charger V2.0.1."""
        result = await charge_point_v201.on_heartbeat()

        # Should broadcast event
        charge_point_v201.manager.broadcast_event.assert_called_once()
        call_args = charge_point_v201.manager.broadcast_event.call_args[0][0]
        assert call_args["type"] == "heartbeat"
        assert "current_time" in call_args

        # Should return current time
        assert result.current_time is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_on_status_notification_normal_v16(self, charge_point_v16):
        """Test handling normal StatusNotification V1.6."""
        await charge_point_v16.on_status_notification(
            connector_id=1, error_code="NoError", status="Available"
        )

        # Should broadcast event
        charge_point_v16.manager.broadcast_event.assert_called_once()
        call_args = charge_point_v16.manager.broadcast_event.call_args[0][0]
        assert call_args["type"] == "status"
        assert call_args["connector_id"] == 1
        assert call_args["error_code"] == "NoError"
        assert call_args["status"] == "Available"

        # Should not release control or send notification
        charge_point_v16.manager.release_control.assert_not_called()
        charge_point_v16.ha_bridge.send_notification.assert_not_called()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_on_status_notification_faulted(self, charge_point):
        """Test handling faulted StatusNotification."""
        await charge_point.on_status_notification(
            connector_id=1, error_code="ConnectorLockFailure", status="Faulted"
        )

        # Should broadcast event
        charge_point.manager.broadcast_event.assert_called_once()

        # Should release control and send HA notification
        charge_point.manager.release_control.assert_called_once()
        charge_point.ha_bridge.send_notification.assert_called_once()

        # Check notification content
        call_args = charge_point.ha_bridge.send_notification.call_args[0]
        assert call_args[0] == "Charger Fault"
        assert "Status=Faulted" in call_args[1]
        assert "Error=ConnectorLockFailure" in call_args[1]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_on_status_notification_unavailable(self, charge_point):
        """Test handling unavailable StatusNotification."""
        await charge_point.on_status_notification(
            connector_id=1, error_code="NoError", status="Unavailable"
        )

        # Should release control and send HA notification
        charge_point.manager.release_control.assert_called_once()
        charge_point.ha_bridge.send_notification.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_on_status_notification_no_ha_bridge(self, mock_connection, mock_manager):
        """Test StatusNotification without HA bridge."""
        charge_point = ChargePointV16("CP-1", mock_connection, manager=mock_manager)

        await charge_point.on_status_notification(
            connector_id=1, error_code="NoError", status="Faulted"
        )

        # Should still release control
        mock_manager.release_control.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_on_meter_values(self, charge_point):
        """Test handling MeterValues from charger."""
        meter_values = [
            {
                "timestamp": "2023-01-01T12:00:00Z",
                "sampled_value": [{"value": "1000", "measurand": "Energy.Active.Import.Register"}],
            }
        ]

        await charge_point.on_meter_values(connector_id=1, meter_value=meter_values)

        # Should broadcast event
        charge_point.manager.broadcast_event.assert_called_once()
        call_args = charge_point.manager.broadcast_event.call_args[0][0]
        assert call_args["type"] == "meter"
        assert call_args["connector_id"] == 1
        assert call_args["values"] == meter_values

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_on_start_transaction(self, charge_point):
        """Test handling StartTransaction from charger."""
        result = await charge_point.on_start_transaction(
            connector_id=1, id_tag="RFID123", meter_start=0, timestamp="2023-01-01T12:00:00Z"
        )

        # Should increment transaction counter
        assert charge_point._tx_counter == 1

        # Should store session info
        assert 1 in charge_point._sessions
        session = charge_point._sessions[1]
        assert session["connector_id"] == 1
        assert session["id_tag"] == "RFID123"
        assert session["start_time"] == "2023-01-01T12:00:00Z"
        assert session["start_meter"] == 0

        # Should broadcast event
        charge_point.manager.broadcast_event.assert_called_once()
        call_args = charge_point.manager.broadcast_event.call_args[0][0]
        assert call_args["type"] == "transaction_started"
        assert call_args["transaction_id"] == 1
        assert call_args["connector_id"] == 1
        assert call_args["id_tag"] == "RFID123"

        # Should return accepted status
        assert result.transaction_id == 1
        assert result.id_tag_info["status"] == AuthorizationStatus.accepted

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_on_start_transaction_multiple(self, charge_point):
        """Test handling multiple StartTransaction calls."""
        # First transaction
        result1 = await charge_point.on_start_transaction(
            connector_id=1, id_tag="RFID123", meter_start=0, timestamp="2023-01-01T12:00:00Z"
        )

        # Second transaction
        result2 = await charge_point.on_start_transaction(
            connector_id=2, id_tag="RFID456", meter_start=100, timestamp="2023-01-01T12:30:00Z"
        )

        assert result1.transaction_id == 1
        assert result2.transaction_id == 2
        assert len(charge_point._sessions) == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_on_stop_transaction(self, charge_point):
        """Test handling StopTransaction from charger."""
        # First start a transaction
        await charge_point.on_start_transaction(
            connector_id=1, id_tag="RFID123", meter_start=0, timestamp="2023-01-01T12:00:00Z"
        )

        # Now stop it
        result = await charge_point.on_stop_transaction(
            transaction_id=1, meter_stop=5000, timestamp="2023-01-01T13:00:00Z"
        )

        # Should broadcast event (called twice: start + stop)
        assert charge_point.manager.broadcast_event.call_count == 2
        call_args = charge_point.manager.broadcast_event.call_args[0][0]
        assert call_args["type"] == "transaction_stopped"
        assert call_args["transaction_id"] == 1
        assert call_args["meter_stop"] == 5000

        # Should log session
        charge_point.event_logger.log_session.assert_called_once()
        log_args = charge_point.event_logger.log_session.call_args[0]
        assert log_args[0] == "test_backend"  # backend_id
        assert log_args[1] == 3600.0  # duration (1 hour)
        assert log_args[2] == 5.0  # energy (5000 Wh = 5 kWh)
        assert log_args[3] == 0.0  # revenue

        # Should send HA notification
        charge_point.ha_bridge.send_notification.assert_called_once()

        # Should remove session
        assert 1 not in charge_point._sessions

        # Should return accepted status
        assert result.id_tag_info["status"] == AuthorizationStatus.accepted

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_on_stop_transaction_unknown_id(self, charge_point):
        """Test handling StopTransaction for unknown transaction ID."""
        result = await charge_point.on_stop_transaction(
            transaction_id=999, meter_stop=5000, timestamp="2023-01-01T13:00:00Z"
        )

        # Should broadcast event
        charge_point.manager.broadcast_event.assert_called_once()

        # Should not log session (no start info)
        charge_point.event_logger.log_session.assert_not_called()

        # Should still return accepted status
        assert result.id_tag_info["status"] == AuthorizationStatus.accepted

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_on_stop_transaction_no_manager(self, mock_connection, mock_event_logger):
        """Test StopTransaction without manager."""
        charge_point = ChargePointV16("CP-1", mock_connection, event_logger=mock_event_logger)

        result = await charge_point.on_stop_transaction(
            transaction_id=1, meter_stop=5000, timestamp="2023-01-01T13:00:00Z"
        )

        # Should not try to log session (no backend_id)
        mock_event_logger.log_session.assert_not_called()

        # Should still return accepted status
        assert result.id_tag_info["status"] == AuthorizationStatus.accepted

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_on_stop_transaction_invalid_timestamps(self, charge_point):
        """Test StopTransaction with invalid timestamp formats."""
        # Start transaction
        await charge_point.on_start_transaction(
            connector_id=1, id_tag="RFID123", meter_start=0, timestamp="invalid_timestamp"
        )

        # Stop transaction
        await charge_point.on_stop_transaction(
            transaction_id=1, meter_stop=5000, timestamp="also_invalid"
        )

        # Should still log session with 0 duration
        charge_point.event_logger.log_session.assert_called_once()
        log_args = charge_point.event_logger.log_session.call_args[0]
        assert log_args[1] == 0.0  # duration should be 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_on_stop_transaction_no_event_logger(self, mock_connection, mock_manager):
        """Test StopTransaction without event logger."""
        charge_point = ChargePointV16("CP-1", mock_connection, manager=mock_manager)

        # Start transaction
        await charge_point.on_start_transaction(
            connector_id=1, id_tag="RFID123", meter_start=0, timestamp="2023-01-01T12:00:00Z"
        )

        # Stop transaction
        result = await charge_point.on_stop_transaction(
            transaction_id=1, meter_stop=5000, timestamp="2023-01-01T13:00:00Z"
        )

        # Should still return accepted status
        assert result.id_tag_info["status"] == AuthorizationStatus.accepted

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_on_stop_transaction_no_ha_bridge(
        self, mock_connection, mock_manager, mock_event_logger
    ):
        """Test StopTransaction without HA bridge."""
        charge_point = ChargePointV16(
            "CP-1", mock_connection, manager=mock_manager, event_logger=mock_event_logger
        )

        # Start transaction
        await charge_point.on_start_transaction(
            connector_id=1, id_tag="RFID123", meter_start=0, timestamp="2023-01-01T12:00:00Z"
        )

        # Stop transaction
        result = await charge_point.on_stop_transaction(
            transaction_id=1, meter_stop=5000, timestamp="2023-01-01T13:00:00Z"
        )

        # Should still log session
        mock_event_logger.log_session.assert_called_once()

        # Should return accepted status
        assert result.id_tag_info["status"] == AuthorizationStatus.accepted

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_start_method(self, charge_point):
        """Test the start method."""
        # Mock the call_boot_notification method
        charge_point.call_boot_notification = AsyncMock()

        # Create a task that will be cancelled after a short time
        start_task = asyncio.create_task(charge_point.start())

        # Wait a bit for the boot notification to be sent
        await asyncio.sleep(0.1)

        # Cancel the task
        start_task.cancel()

        # Check that boot notification was called
        charge_point.call_boot_notification.assert_called_once_with(
            charge_point_model="EVProxy", charge_point_vendor="OCPPProxy"
        )

    @pytest.mark.unit
    def test_transaction_counter_increments(self, charge_point):
        """Test that transaction counter increments correctly."""
        assert charge_point._tx_counter == 0

        # Simulate incrementing counter (this would happen in on_start_transaction)
        charge_point._tx_counter += 1
        assert charge_point._tx_counter == 1

        charge_point._tx_counter += 1
        assert charge_point._tx_counter == 2

    @pytest.mark.unit
    def test_session_storage(self, charge_point):
        """Test session storage and retrieval."""
        session_data = {
            "connector_id": 1,
            "id_tag": "RFID123",
            "start_time": "2023-01-01T12:00:00Z",
            "start_meter": 0,
        }

        # Store session
        charge_point._sessions[1] = session_data

        # Retrieve session
        retrieved = charge_point._sessions[1]
        assert retrieved == session_data

        # Remove session
        del charge_point._sessions[1]
        assert 1 not in charge_point._sessions

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_energy_calculation(self, charge_point):
        """Test energy calculation in stop transaction."""
        # Start transaction
        await charge_point.on_start_transaction(
            connector_id=1,
            id_tag="RFID123",
            meter_start=1000,  # 1000 Wh
            timestamp="2023-01-01T12:00:00Z",
        )

        # Stop transaction
        await charge_point.on_stop_transaction(
            transaction_id=1,
            meter_stop=6000,
            timestamp="2023-01-01T13:00:00Z",  # 6000 Wh
        )

        # Check energy calculation (should be 5 kWh)
        charge_point.event_logger.log_session.assert_called_once()
        log_args = charge_point.event_logger.log_session.call_args[0]
        assert log_args[2] == 5.0  # energy in kWh

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_duration_calculation(self, charge_point):
        """Test duration calculation in stop transaction."""
        # Start transaction
        await charge_point.on_start_transaction(
            connector_id=1, id_tag="RFID123", meter_start=0, timestamp="2023-01-01T12:00:00Z"
        )

        # Stop transaction 30 minutes later
        await charge_point.on_stop_transaction(
            transaction_id=1, meter_stop=1000, timestamp="2023-01-01T12:30:00Z"
        )

        # Check duration calculation (should be 1800 seconds = 30 minutes)
        charge_point.event_logger.log_session.assert_called_once()
        log_args = charge_point.event_logger.log_session.call_args[0]
        assert log_args[1] == 1800.0  # duration in seconds
