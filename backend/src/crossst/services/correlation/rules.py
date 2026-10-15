from datetime import datetime, timedelta, timezone

from crossst.domain.schemas.alerts import AlertMessage
from crossst.domain.schemas.incidents import IncidentMessage


WINDOW_SECONDS = 300

SEVERITY_RANK = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


def floor_time_window(dt: datetime, window_seconds: int = WINDOW_SECONDS) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    timestamp = int(dt.timestamp())
    floored = timestamp - (timestamp % window_seconds)
    return datetime.fromtimestamp(floored, tz=timezone.utc)


def build_aggregate_key(alert: AlertMessage) -> str:
    if alert.service:
        return f"service:{alert.service}"
    if alert.host:
        return f"host:{alert.host}"
    return f"component:{alert.component}"


def build_incident_cache_key(alert: AlertMessage) -> str:
    window_start = floor_time_window(alert.created_at)
    aggregate_key = build_aggregate_key(alert)
    return f"incident:{aggregate_key}:{int(window_start.timestamp())}"


def max_severity(severities: list[str]) -> str:
    return max(severities, key=lambda item: SEVERITY_RANK[item])


def build_incident_from_alerts(
    *,
    incident_id: str,
    aggregate_key: str,
    alerts: list[AlertMessage],
) -> IncidentMessage:
    window_start = floor_time_window(alerts[0].created_at)
    window_end = window_start + timedelta(seconds=WINDOW_SECONDS)

    severity = max_severity([alert.severity for alert in alerts])
    alert_ids = [alert.alert_id for alert in alerts]
    affected_hosts = sorted({alert.host for alert in alerts if alert.host})
    affected_services = sorted({alert.service for alert in alerts if alert.service})
    event_types = sorted({alert.event_type for alert in alerts})

    title = f"{severity.upper()} incident on {aggregate_key}"
    summary = (
        f"{len(alerts)} alert(s) grouped for {aggregate_key} "
        f"within {WINDOW_SECONDS}s. Event types: {', '.join(event_types)}."
    )

    return IncidentMessage(
        incident_id=incident_id,
        title=title,
        severity=severity,
        aggregate_key=aggregate_key,
        time_window_start=window_start,
        time_window_end=window_end,
        alert_ids=alert_ids,
        alert_count=len(alerts),
        affected_hosts=affected_hosts,
        affected_services=affected_services,
        event_types=event_types,
        summary=summary,
        fields={
            "alert_types": sorted({alert.alert_type for alert in alerts}),
            "fingerprints": sorted({alert.fingerprint for alert in alerts}),
        },
    )

