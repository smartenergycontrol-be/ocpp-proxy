import asyncio
import datetime
import logging
from typing import Any

from aiohttp import web

from .config import Config

_LOGGER = logging.getLogger(__name__)


class BackendManager:
    """
    Track subscriber backends and manage single active control lock arbitration.
    """

    def __init__(
        self,
        config: Config,
        ha_bridge: Any = None,
        ocpp_service_manager: Any = None,
    ) -> None:
        # Configuration and HA bridge for enforcing policies
        self.config = config
        self.ha = ha_bridge
        self.ocpp_service_manager = ocpp_service_manager
        # Map backend_id → WS connection for event broadcasting
        self.subscribers: dict[str, web.WebSocketResponse] = {}
        self._lock_owner: str | None = None
        self._lock_timer: asyncio.Task[None] | None = None
        # Rate-limiting timestamps per backend
        self._last_request_time: dict[str, datetime.datetime] = {}
        # Reference to app for charge point access
        self._app = None

    def subscribe(self, backend_id: str, ws: web.WebSocketResponse) -> None:
        """Register a new backend subscriber with its WebSocket connection."""
        self.subscribers[backend_id] = ws

    def unsubscribe(self, backend_id: str) -> None:
        """Remove a backend subscriber and release control if it owned the lock."""
        self.subscribers.pop(backend_id, None)
        if self._lock_owner == backend_id:
            self.release_control()

    async def broadcast_event(self, event: Any) -> None:
        """Forward charger event to all subscribers via WebSocket and OCPP services."""
        # Broadcast to WebSocket subscribers
        for ws in list(self.subscribers.values()):
            # best-effort send; ignore failures
            try:
                await ws.send_json({"type": "event", **event})
            except Exception as e:
                _LOGGER.debug(f"Failed to send event to backend: {e}")
                continue

        # Broadcast to OCPP services
        if self.ocpp_service_manager:
            self.ocpp_service_manager.broadcast_event_to_services(event)

    async def request_control(self, backend_id: str) -> bool:
        """Attempt to acquire or preempt control for a backend, enforcing safety rules."""
        if not await self._check_rate_limit(backend_id):
            return False

        if not await self._check_safety_rules(backend_id):
            return False

        return self._try_acquire_control(backend_id)

    async def _check_rate_limit(self, backend_id: str) -> bool:
        """Check rate limiting for backend requests."""
        now = datetime.datetime.now(datetime.UTC)
        last = self._last_request_time.get(backend_id)
        if last and (now - last).total_seconds() < self.config.rate_limit_seconds:
            return False
        self._last_request_time[backend_id] = now
        return True

    async def _check_safety_rules(self, backend_id: str) -> bool:
        """Check all safety rules and policies."""
        # Global shared-charging toggle
        if not self.config.allow_shared_charging:
            return False

        # HA override boolean (must be ON to allow shared)
        if self.ha and self.config.override_input_boolean:
            try:
                state = await self.ha.get_state(self.config.override_input_boolean)
                if state.get("state") != "on":
                    return False
            except Exception as e:
                # Fail-safe: allow control if HA is unavailable
                _LOGGER.debug(f"HA override check failed: {e}")

        # Presence sensor (block if someone is home)
        if self.ha and self.config.presence_sensor:
            try:
                state = await self.ha.get_state(self.config.presence_sensor)
                if state.get("state") == "home":
                    return False
            except Exception as e:
                # Fail-safe: allow control if HA is unavailable
                _LOGGER.debug(f"HA presence check failed: {e}")

        # Provider filtering (skip for OCPP services)
        if not backend_id.startswith("ocpp_service_"):
            if backend_id in self.config.blocked_providers:
                return False
            if self.config.allowed_providers and backend_id not in self.config.allowed_providers:
                return False

        return True

    def _try_acquire_control(self, backend_id: str) -> bool:
        """Try to acquire control, handling preemption."""
        # Preferred-provider preemption
        if (
            self._lock_owner
            and backend_id == self.config.preferred_provider
            and backend_id != self._lock_owner
        ):
            self.release_control()

        # Grant if free
        if self._lock_owner is None:
            self._lock_owner = backend_id
            self._start_lock_timer()
            return True
        return False

    def release_control(self) -> None:
        """Release the active control lock."""
        self._lock_owner = None
        if self._lock_timer:
            self._lock_timer.cancel()
            self._lock_timer = None

    def _start_lock_timer(self, timeout: int = 60) -> None:
        """Schedule automatic release if control not used within timeout seconds."""
        if self._lock_timer:
            self._lock_timer.cancel()
        self._lock_timer = asyncio.create_task(self._lock_timeout(timeout))

    async def _lock_timeout(self, timeout: int) -> None:
        await asyncio.sleep(timeout)
        self.release_control()

    def set_app_reference(self, app: Any) -> None:
        """Set reference to the aiohttp app for charge point access."""
        self._app = app

    def get_backend_status(self) -> dict[str, Any]:
        """Get status of all backends including OCPP services."""
        status: dict[str, Any] = {
            "websocket_backends": list(self.subscribers.keys()),
            "lock_owner": self._lock_owner,
            "ocpp_services": {},
        }

        if self.ocpp_service_manager:
            status["ocpp_services"] = self.ocpp_service_manager.get_service_status()

        return status
