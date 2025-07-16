import logging
from typing import Any

from aiohttp import ClientSession, ClientWebSocketResponse

_LOGGER = logging.getLogger(__name__)


class HABridge:
    """
    Communicate with Home Assistant API for states, services, and notifications.
    """

    def __init__(self, url: str, token: str) -> None:
        self._url = url.rstrip("/")
        self._token = token
        self._session: ClientSession | None = None
        self._ws: ClientWebSocketResponse | None = None

    async def _ensure_session(self) -> ClientSession:
        """Ensure the session exists, creating it if needed."""
        if self._session is None:
            self._session = ClientSession()
        return self._session

    async def connect(self) -> None:
        """Establish WebSocket connection and authenticate with Home Assistant."""
        ws_url = f"{self._url}/api/websocket"
        session = await self._ensure_session()
        self._ws = await session.ws_connect(
            ws_url, headers={"Authorization": f"Bearer {self._token}"}
        )
        # Auth handshake
        await self._ws.receive_json()
        await self._ws.send_json({"type": "auth", "access_token": self._token})
        auth_ok = await self._ws.receive_json()
        if auth_ok.get("type") != "auth_ok":
            _LOGGER.error("HA authentication failed: %s", auth_ok)
            raise RuntimeError("Home Assistant authentication failed")

    async def send_notification(self, title: str, message: str) -> dict[str, Any]:
        """Send a persistent notification via Home Assistant."""
        url = f"{self._url}/api/services/persistent_notification/create"
        data = {"title": title, "message": message}
        session = await self._ensure_session()
        async with session.post(
            url, json=data, headers={"Authorization": f"Bearer {self._token}"}
        ) as resp:
            result = await resp.json()
            return dict(result) if result is not None else {}

    async def get_state(self, entity_id: str) -> dict[str, Any]:
        """Retrieve state of a given entity from Home Assistant."""
        url = f"{self._url}/api/states/{entity_id}"
        session = await self._ensure_session()
        async with session.get(url, headers={"Authorization": f"Bearer {self._token}"}) as resp:
            result = await resp.json()
            return dict(result) if result is not None else {}

    async def close(self) -> None:
        """Close HA WebSocket and HTTP sessions."""
        if self._ws:
            await self._ws.close()
        if self._session:
            await self._session.close()
