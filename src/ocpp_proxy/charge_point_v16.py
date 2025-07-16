import asyncio
import datetime

from ocpp.routing import on
from ocpp.v16 import ChargePoint as OCPPChargePoint
from ocpp.v16 import call, call_result
from ocpp.v16.enums import AuthorizationStatus, RegistrationStatus

from .charge_point_base import ChargePointBase


class ChargePointV16(ChargePointBase, OCPPChargePoint):
    """
    Manage OCPP 1.6 JSON WebSocket interactions with the EV charger.
    """

    def __init__(self, cp_id, connection, manager=None, ha_bridge=None, event_logger=None):
        ChargePointBase.__init__(self, cp_id, connection, manager, ha_bridge, event_logger)
        OCPPChargePoint.__init__(self, cp_id, connection)

    @property
    def ocpp_version(self) -> str:
        """Return the OCPP version this implementation supports."""
        return "1.6"

    async def start(self):
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
            return True
        except Exception:
            return False

    async def send_remote_stop_transaction(self, transaction_id: int) -> bool:
        """Send RemoteStopTransaction command to charger."""
        try:
            await self.call(call.RemoteStopTransactionPayload(transaction_id=transaction_id))
            return True
        except Exception:
            return False

    @on("BootNotification")
    async def on_boot_notification(self, charge_point_vendor, charge_point_model, **kwargs):
        """Handle BootNotification request from charger."""
        event = {
            "type": "boot",
            "vendor": charge_point_vendor,
            "model": charge_point_model,
        }
        self._broadcast_event(event)
        # Respond to charger
        return call_result.BootNotification(
            current_time=datetime.datetime.utcnow().isoformat(),
            interval=10,
            status=RegistrationStatus.accepted,
        )

    @on("Heartbeat")
    async def on_heartbeat(self):
        """Respond to Heartbeat request and notify subscribers."""
        now = datetime.datetime.utcnow().isoformat()
        event = {"type": "heartbeat", "current_time": now}
        self._broadcast_event(event)
        return call_result.Heartbeat(current_time=now)

    @on("StatusNotification")
    async def on_status_notification(self, connector_id, error_code, status, **kwargs):
        """Handle StatusNotification, broadcast and enforce safety on faults."""
        event = {
            "type": "status",
            "connector_id": connector_id,
            "error_code": error_code,
            "status": status,
        }
        self._broadcast_event(event)

        # If charger faults or is unavailable, revoke control and alert
        self._handle_charger_fault(status, error_code)
        if status.lower() in ("faulted", "unavailable"):
            await self._send_notification("Charger Fault", f"Status={status}, Error={error_code}")
        return call_result.StatusNotification()

    @on("MeterValues")
    async def on_meter_values(self, connector_id, meter_value, **kwargs):
        """Handle MeterValues and broadcast meter readings."""
        event = {
            "type": "meter",
            "connector_id": connector_id,
            "values": meter_value,
        }
        self._broadcast_event(event)
        return call_result.MeterValues()

    @on("StartTransaction")
    async def on_start_transaction(self, connector_id, id_tag, meter_start, timestamp, **kwargs):
        """Handle transaction start: record session and broadcast."""
        # Assign a new transaction ID
        tx_id = self._get_next_transaction_id()
        # Store session start info
        self._store_session(tx_id, connector_id, id_tag, timestamp, meter_start)
        # Notify subscribers
        self._broadcast_event(
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

    @on("StopTransaction")
    async def on_stop_transaction(self, transaction_id, meter_stop, timestamp, **kwargs):
        """Handle transaction stop: finalize session, log usage, and broadcast."""
        # Broadcast stop event
        self._broadcast_event(
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
