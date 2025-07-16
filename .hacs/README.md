# OCPP Proxy Home Assistant Add-on

Multi-version OCPP proxy for secure EV charger sharing with Home Assistant integration.

## About

This add-on provides a secure OCPP 1.6 and 2.0.1 proxy server that enables intelligent EV charger sharing. It sits between your EV charger and multiple backend services (energy providers, fleet management, charging networks), allowing multiple third-party services to use spare charger capacity while keeping you in full control.

## Features

- **Multi-Protocol Support**: OCPP 1.6 and 2.0.1 with automatic version detection
- **Homeowner Control**: Full control with manual override capabilities
- **Safety First**: Automatic fault handling and conflict prevention
- **Revenue Tracking**: Session logging and revenue tracking
- **Home Assistant Integration**: Native integration with sensors and controls

## Installation

1. Add this repository to HACS as a custom repository
2. Install the "OCPP Proxy" add-on
3. Configure the add-on options
4. Start the add-on

## Configuration

### Basic Options

| Option | Description | Default |
|--------|-------------|---------|
| `allow_shared_charging` | Enable backend sharing | `true` |
| `preferred_provider` | Preferred backend ID | `""` |
| `rate_limit_seconds` | Rate limiting interval | `10` |
| `ocpp_version` | Default OCPP version | `"1.6"` |
| `auto_detect_ocpp_version` | Auto-detect version | `true` |

### Home Assistant Integration

| Option | Description | Default |
|--------|-------------|---------|
| `presence_sensor` | Presence sensor entity | `""` |
| `override_input_boolean` | Override control entity | `""` |

### Provider Management

| Option | Description | Default |
|--------|-------------|---------|
| `allowed_providers` | Whitelist of providers | `[]` |
| `disallowed_providers` | Blacklist of providers | `[]` |

### OCPP Services

Configure outbound connections to OCPP services:

```yaml
ocpp_services:
  - id: "energy_provider"
    url: "ws://provider.com/ocpp"
    version: "1.6"
    auth_type: "basic"
    username: "user"
    password: "pass"
    enabled: true
```

## Usage

1. Connect your EV charger to the proxy at `ws://[HOST]:9000/charger`
2. Backend services can connect to `ws://[HOST]:9000/backend?id=backend_id`
3. Access the web interface at `http://[HOST]:9000`
4. Monitor sessions and status through Home Assistant

## Endpoints

- **WebSocket**: `/charger` (OCPP connection)
- **WebSocket**: `/backend?id=backend_id` (Backend services)
- **Web UI**: `/` (Status and documentation)
- **REST API**: `/sessions`, `/status`, `/override`

## Support

For issues and support, visit: https://github.com/openchargehub/ocpp-proxy