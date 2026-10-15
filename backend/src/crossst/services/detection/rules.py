from dataclasses import dataclass

from crossst.domain.schemas.alerts import AlertMessage
from crossst.domain.schemas.logs import NormalizedEvent


DEFAULT_WINDOW_SECONDS = 300


@dataclass(frozen=True)
class DetectionContext:
    counter_key: str
    window_seconds: int


def build_detection_context(event: NormalizedEvent) -> DetectionContext | None:
    if event.event_type == "login_failed":
        src_ip = event.fields.get("src_ip", "unknown")
        host = event.host or "unknown-host"
        return DetectionContext(
            counter_key=f"counter:login_failed:{host}:{src_ip}",
            window_seconds=DEFAULT_WINDOW_SECONDS,
        )

    if event.event_type == "app_db_connection_error":
        service = event.service or "unknown-service"
        host = event.host or "unknown-host"
        return DetectionContext(
            counter_key=f"counter:app_db_connection_error:{service}:{host}",
            window_seconds=DEFAULT_WINDOW_SECONDS,
        )

    if event.event_type in {
        "mysql_connection_refused",
        "mysql_too_many_connections",
        "mysql_access_denied",
    }:
        host = event.host or "unknown-host"
        return DetectionContext(
            counter_key=f"counter:{event.event_type}:{host}",
            window_seconds=DEFAULT_WINDOW_SECONDS,
        )

    return None


def evaluate_event(event: NormalizedEvent, *, count: int, window_seconds: int) -> AlertMessage | None:
    if event.event_type == "login_failed" and count >= 3:
        src_ip = event.fields.get("src_ip", "unknown")
        host = event.host or "unknown-host"
        fingerprint = f"login_failed:{host}:{src_ip}"

        return AlertMessage(
            event_id=event.event_id,
            raw_log_id=event.raw_log_id,
            alert_type="ssh_login_failed_threshold",
            event_type=event.event_type,
            severity="medium",
            source_type=event.source_type,
            component=event.component,
            host=event.host,
            service=event.service,
            message=event.message,
            summary=f"SSH login failed {count} times from {src_ip} on {host} within {window_seconds}s.",
            count=count,
            window_seconds=window_seconds,
            fingerprint=fingerprint,
            fields=event.fields,
            tags=event.tags,
        )

    if event.event_type == "mysql_connection_refused":
        host = event.host or "unknown-host"
        fingerprint = f"mysql_connection_refused:{host}"

        return AlertMessage(
            event_id=event.event_id,
            raw_log_id=event.raw_log_id,
            alert_type="mysql_connection_refused",
            event_type=event.event_type,
            severity="high",
            source_type=event.source_type,
            component=event.component,
            host=event.host,
            service=event.service,
            message=event.message,
            summary=f"MySQL connection refused on {host}.",
            count=count,
            window_seconds=window_seconds,
            fingerprint=fingerprint,
            fields=event.fields,
            tags=event.tags,
        )

    if event.event_type == "mysql_too_many_connections":
        host = event.host or "unknown-host"
        fingerprint = f"mysql_too_many_connections:{host}"

        return AlertMessage(
            event_id=event.event_id,
            raw_log_id=event.raw_log_id,
            alert_type="mysql_too_many_connections",
            event_type=event.event_type,
            severity="high",
            source_type=event.source_type,
            component=event.component,
            host=event.host,
            service=event.service,
            message=event.message,
            summary=f"MySQL has too many connections on {host}.",
            count=count,
            window_seconds=window_seconds,
            fingerprint=fingerprint,
            fields=event.fields,
            tags=event.tags,
        )

    if event.event_type == "app_db_connection_error" and count >= 2:
        service = event.service or "unknown-service"
        host = event.host or "unknown-host"
        fingerprint = f"app_db_connection_error:{service}:{host}"

        return AlertMessage(
            event_id=event.event_id,
            raw_log_id=event.raw_log_id,
            alert_type="app_db_connection_error_threshold",
            event_type=event.event_type,
            severity="medium",
            source_type=event.source_type,
            component=event.component,
            host=event.host,
            service=event.service,
            message=event.message,
            summary=f"{service} reported DB connection errors {count} times on {host} within {window_seconds}s.",
            count=count,
            window_seconds=window_seconds,
            fingerprint=fingerprint,
            fields=event.fields,
            tags=event.tags,
        )

    return None
