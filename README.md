 # OCPP Proxy - Home Assistant Add-on

 This add-on provides a secure, lightweight OCPP 1.6 JSON WebSocket proxy server for Home Assistant.
 It sits between a single EV charger and multiple backend services, allowing shared use while
 keeping the homeowner in control.

 ## Features
 - Accept a single charger connection (CSMS role) via WebSocket
 - Allow multiple backend services to subscribe to charger events and request control
 - Enforce single active control session with smart arbitration and user-defined rules
 - Integrate with Home Assistant for configuration, state monitoring, notifications, and overrides
 - Log usage sessions and revenue data, exportable as CSV or via REST API

 ## Installation

 ### Home Assistant Add-on
 1. Copy this repository into your Home Assistant add-ons directory.
 2. Configure options via the add-on UI:
    - `allow_shared_charging`: enable shared charging
    - `preferred_provider`: provider to prioritize when multiple requests arrive
 3. Start the add-on.

 ### Standalone (Docker Compose)
 ```yaml
 version: '3'
 services:
   ocpp_proxy:
     build: .
     environment:
       - HA_URL=http://homeassistant.local:8123
       - HA_TOKEN=YOUR_LONG_LIVED_ACCESS_TOKEN
     ports:
       - '9000:9000'
     volumes:
       - ./config:/config
 ```

 ## Configuration
 - For Home Assistant, options are set in the add-on UI and stored in `/data/options.yaml`.
 - For standalone mode, provide `config/config.yaml` alongside the container.

 ## Usage
 This add-on starts a WebSocket server on port 9000 by default:
 - `/charger` endpoint for the EV charger.
 - `/backend` endpoint for third-party backends.

 Connect your charger and backends to share the EV charging capacity securely.

 ## Development
 See the `src/ev_charger_proxy` directory for module structure:
 - `charge_point.py`: OCPP session management
 - `backend_manager.py`: subscriber tracking and control arbitration
 - `config.py`: policy and HA/standalone settings
 - `ha_bridge.py`: Home Assistant API integration
 - `logger.py`: session/event logging and CSV export
 - `main.py`: application entry point
