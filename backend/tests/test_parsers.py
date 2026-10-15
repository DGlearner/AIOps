from pathlib import Path

from crossst.parsers.parsers_route import parse_raw_log
from crossst.domain.schemas.logs import RawLogMessage


def test_parse_linux_failed_password():
    raw = RawLogMessage(
        source_type="linux",
        source_name="auth.log",
        message=(
            "Jun  3 14:03:12 app-prod-01 sshd[2311]: "
            "Failed password for root from 1.2.3.4 port 52231 ssh2"
        ),
    )

    event = parse_raw_log(raw)

    assert event.event_type == "login_failed"
    assert event.component == "ssh"
    assert event.host == "app-prod-01"
    assert event.fields["user"] == "root"
    assert event.fields["src_ip"] == "1.2.3.4"
    assert event.fields["port"] == 52231


def test_parse_linux_accepted_publickey():
    raw = RawLogMessage(
        source_type="linux",
        source_name="auth.log",
        message=(
            "Jun  3 14:03:01 app-prod-01 sshd[1203]: "
            "Accepted publickey for deploy from 10.0.0.4 port 41003 ssh2"
        ),
    )

    event = parse_raw_log(raw)

    assert event.event_type == "login_success"
    assert event.component == "ssh"
    assert event.host == "app-prod-01"
    assert event.fields["user"] == "deploy"
    assert event.fields["src_ip"] == "10.0.0.4"


def test_parse_linux_cron_job():
    raw = RawLogMessage(
        source_type="linux",
        source_name="syslog",
        message="Jun  3 14:03:04 worker-prod-01 cron[3003]: (root) CMD (/usr/local/bin/healthcheck)",
    )

    event = parse_raw_log(raw)

    assert event.event_type == "linux_cron_job"
    assert event.component == "cron"
    assert event.host == "worker-prod-01"


def test_parse_mysql_connection_refused():
    raw = RawLogMessage(
        source_type="mysql",
        host="db-prod-01",
        source_name="mysql-error.log",
        message=(
            "2026-06-03T14:04:02.123456Z 0 [ERROR] "
            "Can't connect to local MySQL server through socket"
        ),
    )

    event = parse_raw_log(raw)

    assert event.event_type == "mysql_connection_refused"
    assert event.component == "mysql"
    assert event.host == "db-prod-01"
    assert event.severity_hint == "high"


def test_parse_mysql_ready_for_connections():
    raw = RawLogMessage(
        source_type="mysql",
        host="db-prod-01",
        source_name="mysql-error.log",
        message="2026-06-03T14:04:02.123456Z 0 [Note] [Server] mysqld: ready for connections.",
    )

    event = parse_raw_log(raw)

    assert event.event_type == "mysql_ready"
    assert event.severity_hint == "info"


def test_parse_mysql_slow_query_signal():
    raw = RawLogMessage(
        source_type="mysql",
        host="db-prod-01",
        source_name="mysql-slow.log",
        message=(
            "2026-06-03T14:14:33.000000Z Query_time: 8.50 "
            "Lock_time: 0.00 Rows_sent: 12 Rows_examined: 142 "
            "SELECT * FROM orders WHERE user_id = 1014;"
        ),
    )

    event = parse_raw_log(raw)

    assert event.event_type == "mysql_slow_query"
    assert event.severity_hint == "medium"
    assert event.fields["query_time"] == 8.5
    assert event.fields["rows_examined"] == 142


def test_parse_mysql_normal_query_sample():
    raw = RawLogMessage(
        source_type="mysql",
        host="db-prod-01",
        source_name="mysql-slow.log",
        message=(
            "2026-06-03T14:02:33.000000Z Query_time: 0.06 "
            "Lock_time: 0.00 Rows_sent: 2 Rows_examined: 106 "
            "SELECT * FROM orders WHERE user_id = 1002;"
        ),
    )

    event = parse_raw_log(raw)

    assert event.event_type == "mysql_query_sample"
    assert event.severity_hint == "info"


def test_parse_app_service_db_connection_error():
    raw = RawLogMessage(
        source_type="app_service",
        host="app-prod-01",
        message="2026-06-03T14:04:05 login-service ERROR DB connection refused",
    )

    event = parse_raw_log(raw)

    assert event.event_type == "app_db_connection_error"
    assert event.component == "application"
    assert event.service == "login-service"
    assert event.severity_hint == "medium"


def test_parse_app_login_success():
    raw = RawLogMessage(
        source_type="app_service",
        host="app-prod-01",
        message="2026-06-03T14:04:20Z login-service INFO login success for user user1 from 10.0.1.2",
    )

    event = parse_raw_log(raw)

    assert event.event_type == "app_login_success"
    assert event.severity_hint == "info"


def test_parse_app_payment_event():
    raw = RawLogMessage(
        source_type="app_service",
        host="app-prod-02",
        service="payment-service",
        message="2026-06-03T14:04:40Z payment-service INFO payment captured transaction=pay-4",
    )

    event = parse_raw_log(raw)

    assert event.event_type == "app_payment_captured"
    assert event.component == "application"
    assert event.service == "payment-service"


def test_parse_app_order_created():
    raw = RawLogMessage(
        source_type="app_service",
        host="app-prod-02",
        service="order-service",
        message="2026-06-03T14:04:50Z order-service INFO order created order_id=ord-10004",
    )

    event = parse_raw_log(raw)

    assert event.event_type == "app_order_created"
    assert event.fields["order_id"] == "ord-10004"


def test_stream_dataset_logs_are_mostly_classified():
    stream_dir = Path("../services/log_ingest/datasets/stream")
    source_map = {
        "linux_auth.log": ("linux", "auth.log", "app-prod-01", None),
        "linux_syslog.log": ("linux", "syslog", "app-prod-01", None),
        "mysql_error.log": ("mysql", "mysql-error.log", "db-prod-01", "mysql"),
        "mysql_slow_query.log": ("mysql", "mysql-slow.log", "db-prod-01", "mysql"),
        "app_login_service.log": ("app_service", "login-service.log", "app-prod-01", "login-service"),
        "app_payment_service.log": ("app_service", "payment-service.log", "app-prod-02", "payment-service"),
        "app_order_service.log": ("app_service", "order-service.log", "app-prod-02", "order-service"),
    }
    events = []
    total_lines = 0

    for file_name, (source_type, source_name, host, service) in source_map.items():
        for line in (stream_dir / file_name).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            total_lines += 1
            raw = RawLogMessage(
                source_type=source_type,
                source_name=source_name,
                host=host,
                service=service,
                message=line,
            )
            events.append(parse_raw_log(raw))

    event_types = {event.event_type for event in events}
    unclassified_count = sum(event.event_type == "unclassified_log" for event in events)
    manual_app_events = [
        event
        for event in events
        if "manual-app-login-001" in event.message
    ]

    assert len(events) == total_lines
    assert unclassified_count == 0
    assert [event.event_type for event in manual_app_events] == ["app_db_connection_error"]
    assert {
        "login_failed",
        "login_success",
        "linux_cron_job",
        "mysql_connection_refused",
        "mysql_too_many_connections",
        "mysql_access_denied",
        "mysql_slow_query",
        "app_db_connection_error",
        "app_login_success",
        "app_login_failed",
        "app_payment_captured",
        "app_order_created",
    }.issubset(event_types)
