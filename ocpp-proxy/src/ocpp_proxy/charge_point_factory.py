import logging
from typing import Any

from .charge_point_base import ChargePointBase
from .charge_point_v16 import ChargePointV16
from .charge_point_v201 import ChargePointV201

_LOGGER = logging.getLogger(__name__)


class ChargePointFactory:
    """Factory for creating the appropriate ChargePoint implementation based on version."""

    @staticmethod
    def create_charge_point(
        cp_id: str,
        connection: Any,
        version: str | None = None,
        manager: Any = None,
        ha_bridge: Any = None,
        event_logger: Any = None,
        auto_detect: bool = True,
    ) -> ChargePointBase:
        """
        Create a ChargePoint instance based on the specified or detected OCPP version.

        Args:
            cp_id: Charge Point ID
            connection: WebSocket connection
            version: OCPP version ('1.6' or '2.0.1'). If None, will attempt auto-detection.
            manager: Backend manager instance
            ha_bridge: Home Assistant bridge instance
            event_logger: Event logger instance
            auto_detect: Whether to attempt version auto-detection

        Returns:
            ChargePointBase instance for the appropriate OCPP version

        Raises:
            ValueError: If version is unsupported or auto-detection fails
        """

        # If no version specified and auto-detect is enabled, try to detect version
        if version is None and auto_detect:
            version = ChargePointFactory._detect_version(connection)

        # Default to 1.6 if no version could be determined
        if version is None:
            version = "1.6"
            _LOGGER.warning(f"Could not determine OCPP version for {cp_id}, defaulting to 1.6")

        # Normalize version string
        version = version.strip()

        if version == "1.6":
            _LOGGER.info(f"Creating OCPP 1.6 ChargePoint for {cp_id}")
            return ChargePointV16(cp_id, connection, manager, ha_bridge, event_logger)
        if version == "2.0.1":
            _LOGGER.info(f"Creating OCPP 2.0.1 ChargePoint for {cp_id}")
            return ChargePointV201(cp_id, connection, manager, ha_bridge, event_logger)
        raise ValueError(f"Unsupported OCPP version: {version}")

    @staticmethod
    def _detect_version(connection: Any) -> str | None:
        """
        Attempt to detect OCPP version from WebSocket connection.

        Detection methods:
        1. WebSocket subprotocol inspection
        2. Connection headers analysis
        3. URL path analysis
        4. Request parameters
        """
        try:
            # Method 1: Check WebSocket subprotocol
            if hasattr(connection, "subprotocol"):
                subprotocol = connection.subprotocol
                if subprotocol:
                    subprotocol_lower = subprotocol.lower()
                    if "ocpp1.6" in subprotocol_lower:
                        _LOGGER.debug("Detected OCPP 1.6 from subprotocol")
                        return "1.6"
                    if "ocpp2.0.1" in subprotocol_lower:
                        _LOGGER.debug("Detected OCPP 2.0.1 from subprotocol")
                        return "2.0.1"
                    if "ocpp2.0" in subprotocol_lower:
                        _LOGGER.debug("Detected OCPP 2.0 from subprotocol, using 2.0.1")
                        return "2.0.1"

            # Method 2: Check connection headers
            if hasattr(connection, "headers"):
                headers = connection.headers
                if headers:
                    # Standard WebSocket protocol header
                    ws_protocol = headers.get("Sec-WebSocket-Protocol", "")
                    if "1.6" in ws_protocol:
                        _LOGGER.debug("Detected OCPP 1.6 from Sec-WebSocket-Protocol header")
                        return "1.6"
                    if "2.0.1" in ws_protocol or "2.0" in ws_protocol:
                        _LOGGER.debug("Detected OCPP 2.0.1 from Sec-WebSocket-Protocol header")
                        return "2.0.1"

                    # Custom version headers
                    ocpp_version = headers.get("X-OCPP-Version", headers.get("OCPP-Version", ""))
                    if ocpp_version:
                        if "1.6" in ocpp_version:
                            _LOGGER.debug("Detected OCPP 1.6 from custom header")
                            return "1.6"
                        if "2.0.1" in ocpp_version or "2.0" in ocpp_version:
                            _LOGGER.debug("Detected OCPP 2.0.1 from custom header")
                            return "2.0.1"

            # Method 3: Check URL path for version hints
            if hasattr(connection, "path"):
                path = connection.path.lower()
                if "v1.6" in path or "ocpp16" in path or "1.6" in path:
                    _LOGGER.debug("Detected OCPP 1.6 from URL path")
                    return "1.6"
                if "v2.0.1" in path or "ocpp201" in path or "2.0.1" in path:
                    _LOGGER.debug("Detected OCPP 2.0.1 from URL path")
                    return "2.0.1"
                if "v2.0" in path or "ocpp20" in path:
                    _LOGGER.debug("Detected OCPP 2.0 from URL path, using 2.0.1")
                    return "2.0.1"

            # Method 4: Check query parameters
            if hasattr(connection, "query"):
                query = connection.query
                version = query.get("version", query.get("ocpp_version", ""))
                if version:
                    if "1.6" in version:
                        _LOGGER.debug("Detected OCPP 1.6 from query parameters")
                        return "1.6"
                    if "2.0.1" in version or "2.0" in version:
                        _LOGGER.debug("Detected OCPP 2.0.1 from query parameters")
                        return "2.0.1"

            # Method 5: Check connection attributes (for aiohttp WebSocket)
            if hasattr(connection, "request"):
                request = connection.request
                if hasattr(request, "query"):
                    version = request.query.get("version", request.query.get("ocpp_version", ""))
                    if version:
                        if "1.6" in version:
                            _LOGGER.debug("Detected OCPP 1.6 from request query")
                            return "1.6"
                        if "2.0.1" in version or "2.0" in version:
                            _LOGGER.debug("Detected OCPP 2.0.1 from request query")
                            return "2.0.1"

            _LOGGER.debug("No OCPP version indicators found in connection")

        except Exception as e:
            _LOGGER.debug(f"Error during version detection: {e}")

        return None

    @staticmethod
    def get_supported_versions() -> list[str]:
        """Return list of supported OCPP versions."""
        return ["1.6", "2.0.1"]

    @staticmethod
    def is_version_supported(version: str) -> bool:
        """Check if a given OCPP version is supported."""
        return version in ChargePointFactory.get_supported_versions()


class OCPPServiceFactory:
    """Factory for creating OCPP service clients for outbound connections."""

    @staticmethod
    def create_service_client(
        service_id: str, connection: Any, version: str, manager: Any = None
    ) -> ChargePointBase:
        """
        Create an OCPP service client for outbound connections.

        Args:
            service_id: Service identifier
            connection: WebSocket connection
            version: OCPP version ('1.6' or '2.0.1')
            manager: Backend manager instance

        Returns:
            ChargePointBase instance configured as service client
        """
        # For service clients, we use the same ChargePoint classes but with different configuration
        if version == "1.6":
            return ChargePointV16(service_id, connection, manager)
        if version == "2.0.1":
            return ChargePointV201(service_id, connection, manager)
        raise ValueError(f"Unsupported OCPP version for service client: {version}")
