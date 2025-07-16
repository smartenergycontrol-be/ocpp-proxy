import datetime
import logging
from abc import ABC, abstractmethod
from typing import Any

_LOGGER = logging.getLogger(__name__)


class ChargePointBase(ABC):
    """
    Abstract base class for OCPP ChargePoint implementations.
    Provides version-agnostic interface for both OCPP 1.6 and 2.0.1.
    """

    def __init__(
        self,
        cp_id: str,
        connection: Any,
        manager: Any = None,
        ha_bridge: Any = None,
        event_logger: Any = None,
    ) -> None:
        self.cp_id = cp_id
        self.connection = connection
        self.manager = manager
        self.ha_bridge = ha_bridge
        self.event_logger = event_logger
        # Track ongoing sessions: tx_id -> start info
        self._sessions: dict[int, dict[str, Any]] = {}
        self._tx_counter = 0

    @property
    @abstractmethod
    def ocpp_version(self) -> str:
        """Return the OCPP version this implementation supports."""

    @abstractmethod
    async def start(self) -> None:
        """Start the ChargePoint and handle incoming messages."""

    @abstractmethod
    async def send_remote_start_transaction(self, connector_id: int, id_tag: str) -> bool:
        """Send RemoteStartTransaction command to charger."""

    @abstractmethod
    async def send_remote_stop_transaction(self, transaction_id: int) -> bool:
        """Send RemoteStopTransaction command to charger."""

    def _get_next_transaction_id(self) -> int:
        """Get the next transaction ID."""
        self._tx_counter += 1
        return self._tx_counter

    def _store_session(
        self, tx_id: int, connector_id: int, id_tag: str, timestamp: str, meter_start: int
    ) -> None:
        """Store session start information."""
        self._sessions[tx_id] = {
            "connector_id": connector_id,
            "id_tag": id_tag,
            "start_time": timestamp,
            "start_meter": meter_start,
        }

    def _finalize_session(
        self, tx_id: int, meter_stop: int, timestamp: str
    ) -> dict[str, Any] | None:
        """Finalize session and log usage."""
        info = self._sessions.pop(tx_id, None)
        if info and self.event_logger:
            # Parse timestamps
            try:
                t0 = datetime.datetime.fromisoformat(info["start_time"])
                t1 = datetime.datetime.fromisoformat(timestamp)
                duration = (t1 - t0).total_seconds()
            except Exception as e:
                _LOGGER.debug(f"Failed to parse session timestamps: {e}")
                duration = 0.0
            # Energy in kWh (meter values are Wh)
            energy = (meter_stop - info.get("start_meter", 0)) / 1000.0
            # Revenue calculation placeholder
            revenue = 0.0
            # Determine backend owner
            backend_id = getattr(self.manager, "_lock_owner", None) if self.manager else ""
            self.event_logger.log_session(backend_id, duration, energy, revenue)
        return info

    async def _broadcast_event(self, event: dict[str, Any]) -> None:
        """Broadcast event to all subscribers."""
        if self.manager:
            await self.manager.broadcast_event(event)

    async def _send_notification(self, title: str, message: str) -> None:
        """Send notification via Home Assistant."""
        if self.ha_bridge:
            await self.ha_bridge.send_notification(title, message)

    def _handle_charger_fault(self, status: str, error_code: str) -> None:
        """Handle charger fault conditions."""
        if status.lower() in ("faulted", "unavailable") and self.manager:
            self.manager.release_control()
