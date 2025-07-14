import os
import yaml


class Config:
    """
    Load configuration from Home Assistant add-on options or standalone YAML file.
    """
    def __init__(self, path: str = None):
        # Home Assistant add-on options are stored in /data/options.yaml by default
        default_path = os.getenv('ADDON_CONFIG_FILE', '/data/options.yaml')
        config_path = path or default_path
        try:
            with open(config_path, 'r') as f:
                self._cfg = yaml.safe_load(f) or {}
        except FileNotFoundError:
            self._cfg = {}

    @property
    def allow_shared_charging(self) -> bool:
        """Return whether shared charging is allowed."""
        return bool(self._cfg.get('allow_shared_charging', False))

    @property
    def preferred_provider(self) -> str:
        """Return the preferred provider ID."""
        return str(self._cfg.get('preferred_provider', ''))

    @property
    def disallowed_providers(self) -> list:
        """Return list of provider IDs that are always disallowed."""
        value = self._cfg.get('disallowed_providers', [])
        return list(value) if value is not None else []

    @property
    def allowed_providers(self) -> list:
        """Return whitelist of provider IDs; empty means no whitelist."""
        value = self._cfg.get('allowed_providers', [])
        return list(value) if value is not None else []

    @property
    def presence_sensor(self) -> str:
        """HA entity_id of presence sensor used to block charging when home."""
        return str(self._cfg.get('presence_sensor', ''))

    @property
    def override_input_boolean(self) -> str:
        """HA entity_id of input_boolean to allow shared charging override."""
        return str(self._cfg.get('override_input_boolean', ''))

    @property
    def rate_limit_seconds(self) -> int:
        """Minimum seconds between remote-control requests per backend."""
        return int(self._cfg.get('rate_limit_seconds', 10))

    @property
    def ocpp_services(self) -> list:
        """Return list of OCPP service configurations for outbound connections."""
        value = self._cfg.get('ocpp_services', [])
        return list(value) if value is not None else []
