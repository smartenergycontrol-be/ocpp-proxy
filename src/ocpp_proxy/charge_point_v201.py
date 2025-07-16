import asyncio
import datetime

from ocpp.routing import on
from ocpp.v201 import ChargePoint as OCPPChargePoint
from ocpp.v201 import call, call_result
from ocpp.v201.enums import AuthorizationStatusEnumType, RegistrationStatusEnumType

from .charge_point_base import ChargePointBase


class ChargePointV201(ChargePointBase, OCPPChargePoint):
    """
    Manage OCPP 2.0.1 JSON WebSocket interactions with the EV charger.
    """

    def __init__(self, cp_id, connection, manager=None, ha_bridge=None, event_logger=None):
        ChargePointBase.__init__(self, cp_id, connection, manager, ha_bridge, event_logger)
        OCPPChargePoint.__init__(self, cp_id, connection)

    @property
    def ocpp_version(self) -> str:
        """Return the OCPP version this implementation supports."""
        return "2.0.1"

    async def start(self):
        """Initiate the BootNotification sequence and handle incoming messages."""
        # Send BootNotification to charger (as charge point)
        await self.call_boot_notification(
            charging_station={"model": "EVProxy", "vendor_name": "OCPPProxy"}, reason="PowerUp"
        )
        # Keep the listener alive
        while True:
            await asyncio.sleep(1)

    async def send_remote_start_transaction(self, connector_id: int, id_tag: str) -> bool:
        """Send RequestStartTransaction command to charger."""
        try:
            await self.call(call.RequestStartTransaction(evse_id=connector_id))
            return True
        except Exception:
            return False

    async def send_remote_stop_transaction(self, transaction_id: int) -> bool:
        """Send RequestStopTransaction command to charger."""
        try:
            await self.call(call.RequestStopTransaction())
            return True
        except Exception:
            return False

    @on("BootNotification")
    async def on_boot_notification(self, charging_station, reason, **kwargs):
        """Handle BootNotification request from charger."""
        event = {
            "type": "boot",
            "vendor": charging_station.get("vendor_name", ""),
            "model": charging_station.get("model", ""),
            "reason": reason,
        }
        self._broadcast_event(event)
        # Respond to charger
        return call_result.BootNotification(
            current_time=datetime.datetime.utcnow().isoformat(),
            interval=10,
            status=RegistrationStatusEnumType.accepted,
        )

    @on("Heartbeat")
    async def on_heartbeat(self, **kwargs):
        """Respond to Heartbeat request and notify subscribers."""
        now = datetime.datetime.utcnow().isoformat()
        event = {"type": "heartbeat", "current_time": now}
        self._broadcast_event(event)
        return call_result.Heartbeat(current_time=now)

    @on("StatusNotification")
    async def on_status_notification(
        self, timestamp, connector_status, evse_id, connector_id, **kwargs
    ):
        """Handle StatusNotification, broadcast and enforce safety on faults."""
        event = {
            "type": "status",
            "connector_id": connector_id,
            "evse_id": evse_id,
            "status": connector_status,
            "timestamp": timestamp,
        }
        self._broadcast_event(event)

        # If charger faults or is unavailable, revoke control and alert
        self._handle_charger_fault(connector_status, "N/A")
        if connector_status.lower() in ("faulted", "unavailable"):
            await self._send_notification(
                "Charger Fault",
                f"Status={connector_status}, EVSE={evse_id}, Connector={connector_id}",
            )
        return call_result.StatusNotification()

    @on("MeterValues")
    async def on_meter_values(self, evse_id, meter_value, **kwargs):
        """Handle MeterValues and broadcast meter readings."""
        event = {
            "type": "meter",
            "evse_id": evse_id,
            "values": meter_value,
        }
        self._broadcast_event(event)
        return call_result.MeterValues()

    @on("TransactionEvent")
    async def on_transaction_event(
        self, event_type, timestamp, trigger_reason, seq_no, transaction_info, **kwargs
    ):
        """Handle TransactionEvent for both start and stop transactions."""
        tx_id = transaction_info.get("transaction_id")

        if event_type == "Started":
            # Handle transaction start
            evse_id = kwargs.get("evse", {}).get("id", 1)
            id_token = kwargs.get("id_token", {}).get("id_token", "")
            meter_start = (
                kwargs.get("meter_value", [{}])[0].get("sampled_value", [{}])[0].get("value", 0)
            )

            # Store session start info
            self._store_session(tx_id, evse_id, id_token, timestamp, int(meter_start))

            # Notify subscribers
            self._broadcast_event(
                {
                    "type": "transaction_started",
                    "transaction_id": tx_id,
                    "connector_id": evse_id,
                    "id_tag": id_token,
                    "meter_start": meter_start,
                    "timestamp": timestamp,
                }
            )

            # Accept start request
            return call_result.TransactionEvent(
                id_token_info={"status": AuthorizationStatusEnumType.accepted}
            )

        if event_type == "Ended":
            # Handle transaction stop
            meter_stop = (
                kwargs.get("meter_value", [{}])[0].get("sampled_value", [{}])[0].get("value", 0)
            )

            # Broadcast stop event
            self._broadcast_event(
                {
                    "type": "transaction_stopped",
                    "transaction_id": tx_id,
                    "meter_stop": meter_stop,
                    "timestamp": timestamp,
                }
            )

            # Compute and log session if we have start info
            info = self._finalize_session(tx_id, int(meter_stop), timestamp)
            if info:
                # Parse timestamps
                try:
                    t0 = datetime.datetime.fromisoformat(info["start_time"])
                    t1 = datetime.datetime.fromisoformat(timestamp)
                    duration = (t1 - t0).total_seconds()
                except Exception:
                    duration = 0.0
                # Energy in kWh (meter values are Wh)
                energy = (int(meter_stop) - info.get("start_meter", 0)) / 1000.0
                # Determine backend owner
                backend_id = self.manager._lock_owner if self.manager else ""
                await self._send_notification(
                    "Charging session ended",
                    f"Provider={backend_id}, kWh={energy:.2f}, duration={duration:.0f}s",
                )

            # Accept stop request
            return call_result.TransactionEvent(
                id_token_info={"status": AuthorizationStatusEnumType.accepted}
            )

        # For other event types (Updated, etc.), just acknowledge
        return call_result.TransactionEvent()
