import asyncio
from ocpp.routing import on
from ocpp.v16 import ChargePoint as OCPPChargePoint, call_result
from ocpp.v16.enums import RegistrationStatus, AuthorizationStatus
from typing import Any, Dict
import datetime


class ChargePoint(OCPPChargePoint):
    """
    Manage OCPP 1.6 JSON WebSocket interactions with the EV charger.
    """

    def __init__(self, cp_id, connection, manager=None, ha_bridge=None, event_logger=None):
        super().__init__(cp_id, connection)
        self.manager = manager
        self.ha_bridge = ha_bridge
        self.event_logger = event_logger
        # Track ongoing sessions: tx_id -> start info
        self._sessions: Dict[int, Dict[str, Any]] = {}
        self._tx_counter = 0

    async def start(self):
        """Initiate the BootNotification sequence and handle incoming messages."""
        # Send BootNotification to charger (as charge point)
        await self.call_boot_notification(
            charge_point_model='EVProxy', charge_point_vendor='OCPPProxy'
        )
        # Keep the listener alive
        while True:
            await asyncio.sleep(1)

    @on('BootNotification')
    async def on_boot_notification(self, charge_point_vendor, charge_point_model, **kwargs):
        """Handle BootNotification request from charger."""
        event = {
            'type': 'boot',
            'vendor': charge_point_vendor,
            'model': charge_point_model,
        }
        if self.manager:
            self.manager.broadcast_event(event)
        # Respond to charger
        return call_result.BootNotificationPayload(
            current_time=datetime.datetime.utcnow().isoformat(),
            interval=10,
            status=RegistrationStatus.accepted,
        )

    @on('Heartbeat')
    async def on_heartbeat(self):
        """Respond to Heartbeat request and notify subscribers."""
        now = datetime.datetime.utcnow().isoformat()
        event = {'type': 'heartbeat', 'current_time': now}
        if self.manager:
            self.manager.broadcast_event(event)
        return call_result.HeartbeatPayload(current_time=now)

    @on('StatusNotification')
    async def on_status_notification(self, connector_id, error_code, status, **kwargs):
        """Handle StatusNotification, broadcast and enforce safety on faults."""
        event = {
            'type': 'status',
            'connector_id': connector_id,
            'error_code': error_code,
            'status': status,
        }
        if self.manager:
            self.manager.broadcast_event(event)

        # If charger faults or is unavailable, revoke control and alert
        if status.lower() in ('faulted', 'unavailable') and self.manager:
            self.manager.release_control()
            if self.ha_bridge:
                await self.ha_bridge.send_notification(
                    'Charger Fault',
                    f'Status={status}, Error={error_code}'
                )
        return call_result.StatusNotificationPayload()

    @on('MeterValues')
    async def on_meter_values(self, connector_id, meter_value, **kwargs):
        """Handle MeterValues and broadcast meter readings."""
        event = {
            'type': 'meter',
            'connector_id': connector_id,
            'values': meter_value,
        }
        if self.manager:
            self.manager.broadcast_event(event)
        return call_result.MeterValuesPayload()

    @on('StartTransaction')
    async def on_start_transaction(self, connector_id, id_tag, meter_start, timestamp, **kwargs):
        """Handle transaction start: record session and broadcast."""
        # Assign a new transaction ID
        self._tx_counter += 1
        tx_id = self._tx_counter
        # Store session start info
        self._sessions[tx_id] = {
            'connector_id': connector_id,
            'id_tag': id_tag,
            'start_time': timestamp,
            'start_meter': meter_start,
        }
        # Notify subscribers
        if self.manager:
            self.manager.broadcast_event({
                'type': 'transaction_started',
                'transaction_id': tx_id,
                'connector_id': connector_id,
                'id_tag': id_tag,
                'meter_start': meter_start,
                'timestamp': timestamp,
            })
        # Accept start request
        return call_result.StartTransactionPayload(
            transaction_id=tx_id,
            id_tag_info={'status': AuthorizationStatus.accepted}
        )

    @on('StopTransaction')
    async def on_stop_transaction(self, transaction_id, meter_stop, timestamp, **kwargs):
        """Handle transaction stop: finalize session, log usage, and broadcast."""
        info = self._sessions.pop(transaction_id, None)
        # Broadcast stop event
        if self.manager:
            self.manager.broadcast_event({
                'type': 'transaction_stopped',
                'transaction_id': transaction_id,
                'meter_stop': meter_stop,
                'timestamp': timestamp,
            })
        # Compute and log session if we have start info
        if info and self.event_logger:
            # Parse timestamps
            try:
                t0 = datetime.datetime.fromisoformat(info['start_time'])
                t1 = datetime.datetime.fromisoformat(timestamp)
                duration = (t1 - t0).total_seconds()
            except Exception:
                duration = 0.0
            # Energy in kWh (meter values are Wh)
            energy = (meter_stop - info.get('start_meter', 0)) / 1000.0
            # Revenue calculation placeholder (configure in future)
            revenue = 0.0
            # Determine backend owner
            backend_id = self.manager._lock_owner if self.manager else ''
            self.event_logger.log_session(backend_id, duration, energy, revenue)
            if self.ha_bridge:
                await self.ha_bridge.send_notification(
                    'Charging session ended',
                    f"Provider={backend_id}, kWh={energy:.2f}, duration={duration:.0f}s"
                )
        # Accept stop request
        return call_result.StopTransactionPayload(
            id_tag_info={'status': AuthorizationStatus.accepted}
        )
