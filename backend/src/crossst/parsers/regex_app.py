import re

from crossst.parsers.event_builder import build_event
from crossst.domain.schemas.logs import NormalizedEvent, RawLogMessage


APP_LOG_RE = re.compile(
    r"^(?P<time>\S+)\s+(?P<service>[\w-]+)\s+"
    r"(?P<level>INFO|WARN|WARNING|ERROR|CRITICAL)\s+(?P<body>.*)$"
)

LOGIN_SUCCESS_RE = re.compile(
    r"login success for user (?P<user>\S+) from (?P<src_ip>\d+\.\d+\.\d+\.\d+)"
)

LOGIN_FAILED_RE = re.compile(
    r"login failed(?: for user (?P<user>\S+))?(?: from (?P<src_ip>\d+\.\d+\.\d+\.\d+))?"
)

PAYMENT_RE = re.compile(
    r"payment (?P<action>authorized|captured|retry scheduled)(?: transaction=(?P<transaction_id>\S+))?"
)

ORDER_CREATED_RE = re.compile(r"order created order_id=(?P<order_id>\S+)")


def parse_app_service_log(raw: RawLogMessage) -> NormalizedEvent | None:
    match = APP_LOG_RE.search(raw.message)
    if not match:
        return None

    data = match.groupdict()
    body_lower = data["body"].lower()
    service = raw.service or data["service"]

    if "db connection refused" in body_lower or "database connection refused" in body_lower:
        return build_event(
            raw,
            component="application",
            event_type="app_db_connection_error",
            severity_hint="medium",
            service=service,
            fields={
                "level": data["level"],
                "reason": "db_connection_refused",
                "log_time": data["time"],
            },
            tags=["application", "database", "availability"],
        )

    login_failed_match = LOGIN_FAILED_RE.search(body_lower)
    if login_failed_match:
        failed_data = login_failed_match.groupdict()
        return build_event(
            raw,
            component="application",
            event_type="app_login_failed",
            severity_hint="low",
            service=service,
            fields={
                "level": data["level"],
                "reason": "login_failed",
                "user": failed_data.get("user"),
                "src_ip": failed_data.get("src_ip"),
                "log_time": data["time"],
            },
            tags=["application", "auth", "login"],
        )

    login_success_match = LOGIN_SUCCESS_RE.search(body_lower)
    if login_success_match:
        success_data = login_success_match.groupdict()
        return build_event(
            raw,
            component="application",
            event_type="app_login_success",
            severity_hint="info",
            service=service,
            fields={
                "level": data["level"],
                "user": success_data["user"],
                "src_ip": success_data["src_ip"],
                "log_time": data["time"],
            },
            tags=["application", "auth", "login"],
        )

    payment_match = PAYMENT_RE.search(body_lower)
    if payment_match:
        payment_data = payment_match.groupdict()
        action = payment_data["action"].replace(" ", "_")
        return build_event(
            raw,
            component="application",
            event_type=f"app_payment_{action}",
            severity_hint="low" if data["level"] == "WARN" else "info",
            service=service,
            fields={
                "level": data["level"],
                "action": action,
                "transaction_id": payment_data.get("transaction_id"),
                "log_time": data["time"],
            },
            tags=["application", "payment"],
        )

    order_created_match = ORDER_CREATED_RE.search(body_lower)
    if order_created_match:
        order_data = order_created_match.groupdict()
        return build_event(
            raw,
            component="application",
            event_type="app_order_created",
            severity_hint="info",
            service=service,
            fields={
                "level": data["level"],
                "order_id": order_data["order_id"],
                "log_time": data["time"],
            },
            tags=["application", "order"],
        )

    return None
