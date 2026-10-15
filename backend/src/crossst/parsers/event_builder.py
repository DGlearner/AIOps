from crossst.domain.schemas.logs import NormalizedEvent, RawLogMessage

# 把解析后的日志输出成结构化信息

def build_event(
    raw: RawLogMessage,
    *,
    component: str,
    event_type: str,
    severity_hint: str,
    fields: dict,
    tags: list[str],
    host: str | None = None,
    service: str | None = None,
) -> NormalizedEvent:
    return NormalizedEvent(
        raw_log_id=raw.log_id,
        timestamp=raw.timestamp,
        source_type=raw.source_type,
        source_name=raw.source_name,
        host=host or raw.host,
        service=service or raw.service,
        component=component,
        event_type=event_type,
        message=raw.message,
        severity_hint=severity_hint,
        fields=fields,
        tags=tags,
    )
