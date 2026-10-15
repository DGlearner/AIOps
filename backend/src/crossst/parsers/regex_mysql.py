import re

from crossst.parsers.event_builder import build_event
from crossst.domain.schemas.logs import NormalizedEvent, RawLogMessage


SLOW_QUERY_RE = re.compile(
    r"^(?P<time>\S+)\s+Query_time:\s+(?P<query_time>\d+(?:\.\d+)?)\s+"
    r"Lock_time:\s+(?P<lock_time>\d+(?:\.\d+)?)\s+"
    r"Rows_sent:\s+(?P<rows_sent>\d+)\s+"
    r"Rows_examined:\s+(?P<rows_examined>\d+)\s+"
    r"(?P<query>.*)$"
)


def parse_mysql_log(raw: RawLogMessage) -> NormalizedEvent | None:
    message_lower = raw.message.lower()

    slow_match = SLOW_QUERY_RE.search(raw.message)
    if slow_match:
        data = slow_match.groupdict()
        query_time = float(data["query_time"])
        rows_examined = int(data["rows_examined"])
        is_slow = query_time >= 1.0
        return build_event(
            raw,
            component="mysql",
            event_type="mysql_slow_query" if is_slow else "mysql_query_sample",
            severity_hint="medium" if is_slow else "info",
            fields={
                "log_time": data["time"],
                "query_time": query_time,
                "lock_time": float(data["lock_time"]),
                "rows_sent": int(data["rows_sent"]),
                "rows_examined": rows_examined,
                "query": data["query"],
            },
            tags=["mysql", "database", "query", "performance"],
        )

    if "too many connections" in message_lower:
        return build_event(
            raw,
            component="mysql",
            event_type="mysql_too_many_connections",
            severity_hint="high",
            fields={"reason": "too_many_connections"},
            tags=["mysql", "database", "availability"],
        )

    if "connection refused" in message_lower or "can't connect" in message_lower:
        return build_event(
            raw,
            component="mysql",
            event_type="mysql_connection_refused",
            severity_hint="high",
            fields={"reason": "connection_refused"},
            tags=["mysql", "database", "availability"],
        )

    if "access denied" in message_lower:
        return build_event(
            raw,
            component="mysql",
            event_type="mysql_access_denied",
            severity_hint="low",
            fields={"reason": "access_denied"},
            tags=["mysql", "database", "auth"],
        )

    if "ready for connections" in message_lower:
        return build_event(
            raw,
            component="mysql",
            event_type="mysql_ready",
            severity_hint="info",
            fields={"reason": "ready_for_connections"},
            tags=["mysql", "database", "lifecycle"],
        )

    if "buffer pool load completed" in message_lower:
        return build_event(
            raw,
            component="mysql",
            event_type="mysql_buffer_pool_loaded",
            severity_hint="info",
            fields={"reason": "buffer_pool_loaded"},
            tags=["mysql", "database", "lifecycle"],
        )

    if "event scheduler" in message_lower:
        return build_event(
            raw,
            component="mysql",
            event_type="mysql_event_scheduler",
            severity_hint="info",
            fields={"reason": "event_scheduler"},
            tags=["mysql", "database", "lifecycle"],
        )

    if "plugin" in message_lower and "ready" in message_lower:
        return build_event(
            raw,
            component="mysql",
            event_type="mysql_plugin_ready",
            severity_hint="info",
            fields={"reason": "plugin_ready"},
            tags=["mysql", "database", "lifecycle"],
        )

    return None
