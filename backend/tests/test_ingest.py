from crossst.api.app import app


def test_agent_backend_does_not_expose_raw_log_http_ingest():
    route_paths = {getattr(route, "path", None) for route in app.routes}

    assert "/ingest/logs" not in route_paths


def test_agent_backend_does_not_expose_raw_log_websocket_ingest():
    route_paths = {getattr(route, "path", None) for route in app.routes}

    assert "/ws/ingest/logs" not in route_paths
