import asyncio
import datetime
from typing import Any

from ocpp.routing import on
from ocpp.v16 import ChargePoint as OCPPChargePoint
from ocpp.v16 import call, call_result
from ocpp.v16.enums import AuthorizationStatus, RegistrationStatus

from .charge_point_base import ChargePointBase


class ChargePointV16(ChargePointBase, OCPPChargePoint):
    """
    Manage OCPP 1.6 JSON WebSocket interactions with the EV charger.
    """

    def __init__(
        self,
        cp_id: str,
        connection: Any,
        manager: Any = None,
        ha_bridge: Any = None,
        event_logger: Any = None,
    ) -> None:
        ChargePointBase.__init__(self, cp_id, connection, manager, ha_bridge, event_logger)
        OCPPChargePoint.__init__(self, cp_id, connection)

    @property
    def ocpp_version(self) -> str:
        """Return the OCPP version this implementation supports."""
        return "1.6"

    async def start(self) -> None:
        """Initiate the BootNotification sequence and handle incoming messages."""
        # Send BootNotification to charger (as charge point)
        await self.call_boot_notification(
            charge_point_model="EVProxy", charge_point_vendor="OCPPProxy"
        )
        # Keep the listener alive
        while True:
            await asyncio.sleep(1)

    async def send_remote_start_transaction(self, connector_id: int, id_tag: str) -> bool:
        """Send RemoteStartTransaction command to charger."""
        try:
            await self.call(
                call.RemoteStartTransactionPayload(connector_id=connector_id, id_tag=id_tag)
            )
        except Exception:
            return False
        return True

    async def send_remote_stop_transaction(self, transaction_id: int) -> bool:
        """Send RemoteStopTransaction command to charger."""
        try:
            await self.call(call.RemoteStopTransactionPayload(transaction_id=transaction_id))
        except Exception:
            return False
        return True

    @on("BootNotification")  # type: ignore[misc]
    async def on_boot_notification(
        self,
        charge_point_vendor: str,
        charge_point_model: str,
        **kwargs: Any,
    ) -> call_result.BootNotification:
        """Handle BootNotification request from charger."""
        event = {
            "type": "boot",
            "vendor": charge_point_vendor,
            "model": charge_point_model,
        }
        await self._broadcast_event(event)
        # Respond to charger
        return call_result.BootNotification(
            current_time=datetime.datetime.now(datetime.UTC).isoformat(),
            interval=10,
            status=RegistrationStatus.accepted,
        )

    @on("Heartbeat")  # type: ignore[misc]
    async def on_heartbeat(self) -> call_result.Heartbeat:
        """Respond to Heartbeat request and notify subscribers."""
        now = datetime.datetime.now(datetime.UTC).isoformat()
        event = {"type": "heartbeat", "current_time": now}
        await self._broadcast_event(event)
        return call_result.Heartbeat(current_time=now)

    @on("StatusNotification")  # type: ignore[misc]
    async def on_status_notification(
        self, connector_id: int, error_code: str, status: str, **kwargs: Any
    ) -> call_result.StatusNotification:
        """Handle StatusNotification, broadcast and enforce safety on faults."""
        event = {
            "type": "status",
            "connector_id": connector_id,
            "error_code": error_code,
            "status": status,
        }
        await self._broadcast_event(event)

        # If charger faults or is unavailable, revoke control and alert
        self._handle_charger_fault(status, error_code)
        if status.lower() in ("faulted", "unavailable"):
            await self._send_notification("Charger Fault", f"Status={status}, Error={error_code}")
        return call_result.StatusNotification()

    @on("MeterValues")  # type: ignore[misc]
    async def on_meter_values(
        self, connector_id: int, meter_value: list[Any], **kwargs: Any
    ) -> call_result.MeterValues:
        """Handle MeterValues and broadcast meter readings."""
        event = {
            "type": "meter",
            "connector_id": connector_id,
            "values": meter_value,
        }
        await self._broadcast_event(event)
        return call_result.MeterValues()

    @on("StartTransaction")  # type: ignore[misc]
    async def on_start_transaction(
        self,
        connector_id: int,
        id_tag: str,
        meter_start: int,
        timestamp: str,
        **kwargs: Any,
    ) -> call_result.StartTransaction:
        """Handle transaction start: record session and broadcast."""
        # Assign a new transaction ID
        tx_id = self._get_next_transaction_id()
        # Store session start info
        self._store_session(tx_id, connector_id, id_tag, timestamp, meter_start)
        # Notify subscribers
        await self._broadcast_event(
            {
                "type": "transaction_started",
                "transaction_id": tx_id,
                "connector_id": connector_id,
                "id_tag": id_tag,
                "meter_start": meter_start,
                "timestamp": timestamp,
            }
        )
        # Accept start request
        return call_result.StartTransaction(
            transaction_id=tx_id, id_tag_info={"status": AuthorizationStatus.accepted}
        )

    @on("StopTransaction")  # type: ignore[misc]
    async def on_stop_transaction(
        self,
        transaction_id: int,
        meter_stop: int,
        timestamp: str,
        **kwargs: Any,
    ) -> call_result.StopTransaction:
        """Handle transaction stop: finalize session, log usage, and broadcast."""
        # Broadcast stop event
        await self._broadcast_event(
            {
                "type": "transaction_stopped",
                "transaction_id": transaction_id,
                "meter_stop": meter_stop,
                "timestamp": timestamp,
            }
        )
        # Compute and log session if we have start info
        info = self._finalize_session(transaction_id, meter_stop, timestamp)
        if info:
            # Parse timestamps
            try:
                t0 = datetime.datetime.fromisoformat(info["start_time"])
                t1 = datetime.datetime.fromisoformat(timestamp)
                duration = (t1 - t0).total_seconds()
            except Exception:
                duration = 0.0
            # Energy in kWh (meter values are Wh)
            energy = (meter_stop - info.get("start_meter", 0)) / 1000.0
            # Determine backend owner
            backend_id = self.manager._lock_owner if self.manager else ""
            await self._send_notification(
                "Charging session ended",
                f"Provider={backend_id}, kWh={energy:.2f}, duration={duration:.0f}s",
            )
        # Accept stop request
        return call_result.StopTransaction(id_tag_info={"status": AuthorizationStatus.accepted})
