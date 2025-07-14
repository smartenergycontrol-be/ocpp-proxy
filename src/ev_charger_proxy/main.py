import asyncio
import logging
import os

from aiohttp import web, WSCloseCode

import io
import csv

from .config import Config
from .charge_point import ChargePoint
from .backend_manager import BackendManager
from .ha_bridge import HABridge
from .logger import EventLogger
from .ocpp_service_manager import OCPPServiceManager

_LOGGER = logging.getLogger(__name__)


async def charger_handler(request: web.Request) -> web.WebSocketResponse:
    """Handle WebSocket connection from the EV charger (CSMS role)."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    cp = ChargePoint(
        'CP-1', ws,
        manager=request.app['backend_manager'],
        ha_bridge=request.app['ha_bridge'],
        event_logger=request.app['event_logger'],
    )
    # store active charge point for proxying control requests
    request.app['charge_point'] = cp
    _LOGGER.info('Charger connected')
    try:
        await cp.start()
    except Exception:
        _LOGGER.exception('Charger handler error')
    finally:
        await ws.close(code=WSCloseCode.GOING_AWAY)
    return ws


async def sessions_json(request: web.Request) -> web.Response:
    """Return all charging sessions as JSON."""
    sessions = request.app['event_logger'].get_sessions()
    return web.json_response(sessions)


async def sessions_csv(request: web.Request) -> web.Response:
    """Return all charging sessions as CSV."""
    sessions = request.app['event_logger'].get_sessions()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['timestamp', 'backend_id', 'duration_s', 'energy_kwh', 'revenue'])
    for s in sessions:
        writer.writerow([
            s['timestamp'], s['backend_id'], s['duration_s'],
            s['energy_kwh'], s['revenue']
        ])
    return web.Response(text=output.getvalue(), content_type='text/csv')


async def override_handler(request: web.Request) -> web.Response:
    """Manually override the active control owner."""
    try:
        data = await request.json()
    except ValueError:
        return web.Response(status=400, text='Invalid JSON')
    
    backend_id = data.get('backend_id')
    manager = request.app['backend_manager']
    manager.release_control()
    ok = await manager.request_control(backend_id)
    return web.json_response({'success': ok, 'owner': manager._lock_owner})


async def status_handler(request: web.Request) -> web.Response:
    """Get current control owner status and backend information."""
    backend_manager = request.app['backend_manager']
    status = backend_manager.get_backend_status()
    return web.json_response(status)


async def welcome_handler(request: web.Request) -> web.Response:
    """Serve a simple welcome page for browser access."""
    html_content = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>EV Charger Proxy</title>
    <link
      href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css"
      rel="stylesheet"
      integrity="sha384-ENjdO4Dr2bkBIFxQpeoL2m0U5p3YhN9j+S8E6eE/d2RH+8abtTE1Pi6jizoU3m1G"
      crossorigin="anonymous"
    />
</head>
<body class="bg-light">
  <div class="container py-5">
    <div class="text-center mb-4">
      <h1 class="display-4">EV Charger Proxy</h1>
      <p class="lead">Proxy your EV charger to multiple backends and log charging sessions.</p>
    </div>
    <div class="card">
      <div class="card-header">
        Available Endpoints
      </div>
      <ul class="list-group list-group-flush">
        <li class="list-group-item"><a href="/charger">/charger</a> (WebSocket for charger)</li>
        <li class="list-group-item"><a href="/backend?id=your_backend_id">/backend?id=your_backend_id</a> (WebSocket for backend)</li>
        <li class="list-group-item"><a href="/sessions">/sessions</a> (JSON session data)</li>
        <li class="list-group-item"><a href="/sessions.csv">/sessions.csv</a> (CSV session data)</li>
        <li class="list-group-item"><a href="/status">/status</a> (backend status and control owner)</li>
        <li class="list-group-item"><a href="/override">/override</a> (POST to override control owner)</li>
      </ul>
    </div>
  </div>
</body>
</html>
"""
    return web.Response(text=html_content, content_type='text/html')


async def backend_handler(request: web.Request) -> web.WebSocketResponse:
    """Handle WebSocket connections from backend service clients."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    backend_id = request.query.get('id', 'unknown')
    manager: BackendManager = request.app['backend_manager']
    manager.subscribe(backend_id, ws)
    _LOGGER.info('Backend %s connected', backend_id)
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                data = msg.json()
                action = data.get('action')
                cp: ChargePoint = request.app.get('charge_point')
                # Remote start request
                if action == 'RemoteStartTransaction' and cp:
                    allowed = await manager.request_control(backend_id)
                    if not allowed:
                        await ws.send_json({'error': 'control_locked'})
                        continue
                    req = await cp.call_remote_start_transaction(
                        connector_id=data.get('connector_id', 1),
                        id_tag=data.get('id_tag')
                    )
                    await ws.send_json({'action': 'RemoteStartTransaction', 'result': req})
                # Remote stop request
                elif action == 'RemoteStopTransaction' and cp:
                    req = await cp.call_remote_stop_transaction(
                        transaction_id=data.get('transaction_id')
                    )
                    await ws.send_json({'action': 'RemoteStopTransaction', 'result': req})
                else:
                    await ws.send_json({'error': 'unknown_action'})
    except asyncio.CancelledError:
        pass
    finally:
        manager.unsubscribe(backend_id)
        await ws.close(code=WSCloseCode.GOING_AWAY)
        _LOGGER.info('Backend %s disconnected', backend_id)
    return ws


async def init_app() -> web.Application:
    """Initialize application components and routes."""
    config = Config()
    ha_url = os.getenv('HA_URL')
    ha_token = os.getenv('HA_TOKEN')
    ha = HABridge(ha_url, ha_token) if ha_url and ha_token else None

    # Initialize OCPP service manager
    ocpp_service_manager = OCPPServiceManager(config)
    
    app = web.Application()
    app['config'] = config
    app['backend_manager'] = BackendManager(config, ha, ocpp_service_manager)
    app['ha_bridge'] = ha
    app['event_logger'] = EventLogger(db_path=os.getenv('LOG_DB_PATH', 'usage_log.db'))
    app['ocpp_service_manager'] = ocpp_service_manager
    
    # Set app reference for backend manager
    app['backend_manager'].set_app_reference(app)

    # Start OCPP service connections
    await ocpp_service_manager.start_services()

    app.add_routes([
        web.get('/', welcome_handler),
        web.get('/charger', charger_handler),
        web.get('/backend', backend_handler),
        web.get('/sessions', sessions_json),
        web.get('/sessions.csv', sessions_csv),
        web.get('/status', status_handler),
        web.post('/override', override_handler),
    ])
    return app


async def cleanup_app(app):
    """Cleanup function to properly close OCPP service connections."""
    if 'ocpp_service_manager' in app:
        await app['ocpp_service_manager'].stop_all_services()

def main() -> None:
    """Entrypoint for the proxy server."""
    logging.basicConfig(level=logging.INFO)
    app = asyncio.run(init_app())
    # Add cleanup handler
    app.on_cleanup.append(cleanup_app)
    web.run_app(app, port=int(os.getenv('PORT', 9000)))


if __name__ == '__main__':
    main()
