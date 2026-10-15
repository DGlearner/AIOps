from datetime import timezone

from fastapi.middleware.cors import CORSMiddleware

from crossst.api.app import app
from crossst.api.routes.ops import build_ops_overview_payload, resolve_ops_window


def test_ops_router_is_registered():
    paths = {route.path for route in app.routes}

    assert "/ops/events" in paths
    assert "/ops/alerts" in paths
    assert "/ops/incidents" in paths
    assert "/ops/diagnoses" in paths
    assert "/ops/service-dependencies" in paths
    assert "/ops/recent-deployments" in paths
    assert "/ops/runbooks" in paths
    assert "/ops/historical-incidents" in paths
    assert "/ops/tool-calls" in paths
    assert "/ops/overview" in paths
    assert "/ops/alerts/{alert_id}/lifecycle" in paths
    assert "/ops/alerts/{alert_id}/diagnose" in paths
    assert "/incidents/{incident_id}/tool-calls" in paths
    assert "/chat/sessions" in paths
    assert "/chat/sessions/{session_id}/messages" in paths
    assert "/chat/sessions/{session_id}/context" in paths
    assert "/chat/sessions/{session_id}/rag-context" in paths
    assert "/ops/redis-counters" in paths


def test_resolve_ops_window_returns_utc_window():
    start, end = resolve_ops_window(5)

    assert start.tzinfo == timezone.utc
    assert end.tzinfo == timezone.utc
    assert int((end - start).total_seconds()) == 300


def test_build_ops_overview_payload_includes_pipeline_and_lifecycle_summary():
    start, end = resolve_ops_window(5)

    payload = build_ops_overview_payload(
        start=start,
        end=end,
        counts={
            "events": 12,
            "alerts": 3,
            "incidents": 2,
            "diagnoses": 1,
            "tool_calls": 4,
        },
        alert_summary={
            "total": 3,
            "by_status": {"open": 2, "acknowledged": 1},
            "by_severity": {"high": 1, "medium": 2},
        },
    )

    assert payload["status"] == "ok"
    assert payload["time_window"]["start"] == start.isoformat()
    assert payload["pipeline_counts"]["events"] == 12
    assert payload["alert_lifecycle"]["by_status"]["open"] == 2
    assert payload["next_actions"][0] == "Review open high/critical alerts first."


def test_app_allows_local_vite_frontend_origin():
    cors_middleware = next(
        middleware
        for middleware in app.user_middleware
        if middleware.cls is CORSMiddleware
    )

    assert "http://localhost:5173" in cors_middleware.kwargs["allow_origins"]
    assert "http://127.0.0.1:5173" in cors_middleware.kwargs["allow_origins"]

