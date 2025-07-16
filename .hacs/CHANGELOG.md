# Changelog

All notable changes to this Home Assistant add-on will be documented in this file.

## [0.1.0] - 2024-01-XX

### Added
- Initial release of OCPP Proxy Home Assistant Add-on
- Support for OCPP 1.6 and 2.0.1 protocols
- Automatic OCPP version detection
- Multi-backend subscription and control arbitration
- Home Assistant API integration
- Session tracking and revenue logging
- WebSocket and REST API endpoints
- Provider whitelist/blacklist support
- Rate limiting and safety controls
- OCPP service client connections
- Web-based status interface

### Features
- Single charger, multiple backend support
- Smart control arbitration with user override
- Real-time event broadcasting
- SQLite session persistence
- Home Assistant sensor integration
- Presence-based charging control
- Manual override controls
- CSV export functionality

### Technical
- Built on python-ocpp library
- aiohttp WebSocket server
- SQLite database for session logging
- Poetry dependency management
- Comprehensive test suite (85% coverage)
- Docker containerization
- Multi-architecture support (amd64, armv7, aarch64, armhf)