import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StreamSourceSpec:
    name: str
    source_type: str
    source_name: str
    host: str
    file: str
    service: str | None
    batch_size: int
    rate_per_second: float
    generator: Callable[[int], str]


def _linux_auth(index: int) -> str:
    host = "app-prod-01" if index % 2 == 0 else "app-prod-02"
    if index % 10 in {6, 7, 8, 9}:
        users = ["root", "admin", "deploy", "test"]
        src_ip = ["8.8.8.8", "45.91.22.10", "185.220.101.12"][index % 3]
        return (
            f"Jun  3 14:{index % 60:02d}:12 {host} sshd[{2300 + index}]: "
            f"Failed password for {users[index % len(users)]} from {src_ip} "
            f"port {52000 + index} ssh2"
        )
    return (
        f"Jun  3 14:{index % 60:02d}:01 {host} sshd[{1200 + index}]: "
        f"Accepted publickey for deploy from 10.0.0.{index % 50 + 1} "
        f"port {41000 + index} ssh2"
    )


def _linux_syslog(index: int) -> str:
    hosts = ["app-prod-01", "app-prod-02", "worker-prod-01", "db-prod-01"]
    host = hosts[index % len(hosts)]
    messages = [
        f"systemd[1]: Started session {index} of user app.",
        f"cron[{3000 + index}]: (root) CMD (/usr/local/bin/healthcheck)",
        f"systemd[1]: Started routine maintenance job {index}.",
        f"kernel: audit: type=1400 apparmor=ALLOWED operation=open profile=app-{index % 5}",
    ]
    return f"Jun  3 14:{index % 60:02d}:04 {host} {messages[index % len(messages)]}"


def _mysql_error(index: int) -> str:
    if index % 12 in {8, 9, 10, 11}:
        errors = [
            "Can't connect to local MySQL server through socket",
            "Connection refused while opening database socket",
            "Too many connections",
            "Access denied for user 'login_service'@'10.0.2.14'",
        ]
        return f"2026-06-03T14:{index % 60:02d}:02.123456Z 0 [ERROR] {errors[index % len(errors)]}"
    notes = [
        "[Server] mysqld: ready for connections.",
        "[InnoDB] Buffer pool load completed.",
        "[Server] Event Scheduler: Loaded 0 events.",
        "[Server] Plugin mysql_native_password reported ready.",
    ]
    return f"2026-06-03T14:{index % 60:02d}:02.123456Z 0 [Note] {notes[index % len(notes)]}"


def _mysql_slow_query(index: int) -> str:
    query_time = 0.04 + (index % 7) * 0.01
    if index % 15 in {12, 13, 14}:
        query_time = 4.5 + (index % 5)
    return (
        f"2026-06-03T14:{index % 60:02d}:33.000000Z Query_time: {query_time:.2f} "
        f"Lock_time: 0.00 Rows_sent: {index % 30} Rows_examined: {100 + index * 3} "
        f"SELECT * FROM orders WHERE user_id = {1000 + index};"
    )


def _app_login_service(index: int) -> str:
    if index % 12 in {7, 8, 9}:
        return f"2026-06-03T14:{index % 60:02d}:22Z login-service ERROR database connection refused"
    if index % 12 == 10:
        return (
            f"2026-06-03T14:{index % 60:02d}:23Z login-service ERROR "
            f"login failed for user user{index % 20} from 10.0.1.{index % 50 + 1}"
        )
    return (
        f"2026-06-03T14:{index % 60:02d}:20Z login-service INFO "
        f"login success for user user{index % 20} from 10.0.1.{index % 50 + 1}"
    )


def _app_payment_service(index: int) -> str:
    if index % 18 in {15, 16, 17}:
        return (
            f"2026-06-03T14:{index % 60:02d}:41Z payment-service ERROR "
            "database connection refused"
        )
    levels = ["INFO", "INFO", "WARN"]
    bodies = [
        f"payment authorized transaction=pay-{index}",
        f"payment captured transaction=pay-{index}",
        f"payment retry scheduled transaction=pay-{index}",
    ]
    return f"2026-06-03T14:{index % 60:02d}:40Z payment-service {levels[index % 3]} {bodies[index % 3]}"


def _app_order_service(index: int) -> str:
    if index % 20 == 18:
        return f"2026-06-03T14:{index % 60:02d}:51Z order-service ERROR login failed for user api-client"
    return (
        f"2026-06-03T14:{index % 60:02d}:50Z order-service INFO "
        f"order created order_id=ord-{10000 + index}"
    )


DEFAULT_SOURCE_SPECS: tuple[StreamSourceSpec, ...] = (
    StreamSourceSpec("linux-auth-prod", "linux", "auth.log", "app-prod-01", "linux_auth.log", None, 5, 10, _linux_auth),
    StreamSourceSpec("linux-syslog-prod", "linux", "syslog", "app-prod-01", "linux_syslog.log", None, 5, 20, _linux_syslog),
    StreamSourceSpec("mysql-error-prod", "mysql", "mysql-error.log", "db-prod-01", "mysql_error.log", "mysql", 5, 8, _mysql_error),
    StreamSourceSpec("mysql-slow-query-prod", "mysql", "mysql-slow.log", "db-prod-01", "mysql_slow_query.log", "mysql", 5, 6, _mysql_slow_query),
    StreamSourceSpec("app-login-service", "app_service", "login-service.log", "app-prod-01", "app_login_service.log", "login-service", 5, 10, _app_login_service),
    StreamSourceSpec("app-payment-service", "app_service", "payment-service.log", "app-prod-02", "app_payment_service.log", "payment-service", 5, 8, _app_payment_service),
    StreamSourceSpec("app-order-service", "app_service", "order-service.log", "app-prod-02", "app_order_service.log", "order-service", 5, 8, _app_order_service),
)


def _write_log_file(path: Path, spec: StreamSourceSpec, lines_per_source: int) -> None:
    path.write_text(
        "\n".join(spec.generator(index) for index in range(lines_per_source)) + "\n",
        encoding="utf-8",
    )


def _source_config(spec: StreamSourceSpec) -> dict[str, object]:
    source: dict[str, object] = {
        "name": spec.name,
        "source_type": spec.source_type,
        "source_name": spec.source_name,
        "host": spec.host,
        "file": spec.file,
        "batch_size": spec.batch_size,
        "rate_per_second": spec.rate_per_second,
    }
    if spec.service is not None:
        source["service"] = spec.service
    return source


def generate_stream_dataset(
    *,
    output_dir: Path,
    lines_per_source: int,
) -> Path:
    if lines_per_source < 1:
        raise ValueError("lines_per_source must be >= 1")

    output_dir.mkdir(parents=True, exist_ok=True)
    for spec in DEFAULT_SOURCE_SPECS:
        _write_log_file(output_dir / spec.file, spec, lines_per_source)

    config = {
        "batch_size": 5,
        "rate_per_second": 10,
        "sources": [_source_config(spec) for spec in DEFAULT_SOURCE_SPECS],
    }
    config_path = output_dir / "stream_sources.example.json"
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return config_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate per-source streaming log files.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("datasets/stream"),
    )
    parser.add_argument("--lines-per-source", type=int, default=200)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    config_path = generate_stream_dataset(
        output_dir=args.output_dir,
        lines_per_source=args.lines_per_source,
    )
    report = {
        "status": "generated",
        "config": str(config_path),
        "source_count": len(DEFAULT_SOURCE_SPECS),
        "lines_per_source": args.lines_per_source,
        "total_lines": len(DEFAULT_SOURCE_SPECS) * args.lines_per_source,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
