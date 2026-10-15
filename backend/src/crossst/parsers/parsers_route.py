from crossst.parsers.event_builder import build_event
from crossst.parsers.regex_app import parse_app_service_log
from crossst.parsers.regex_linux import parse_linux_log
from crossst.parsers.regex_mysql import parse_mysql_log
from crossst.domain.schemas.logs import NormalizedEvent, RawLogMessage


PARSERS = {
    "linux": parse_linux_log,
    "mysql": parse_mysql_log,
    "app_service": parse_app_service_log,
}


def parse_raw_log(raw: RawLogMessage) -> NormalizedEvent:
    parser = PARSERS[raw.source_type]
    event = parser(raw)

    if event is not None:
        return event

    return build_event(
        raw,
        component="unknown",
        event_type="unclassified_log",
        severity_hint="info",
        fields={},
        tags=["unclassified"],
    )
