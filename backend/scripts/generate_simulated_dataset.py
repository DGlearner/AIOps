import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any


SCENARIO_EXPECTATIONS: dict[str, dict[str, Any]] = {
    "normal_mixed": {
        "event_types": ["linux_systemd_event"],
        "alert_types": [],
        "incident_type": None,
        "severity": "none",
    },
    "ssh_bruteforce": {
        "event_types": ["login_failed"],
        "alert_types": ["ssh_login_failed_threshold"],
        "incident_type": "ssh_bruteforce",
        "severity": "medium",
    },
    "mysql_down": {
        "event_types": ["mysql_connection_refused"],
        "alert_types": ["mysql_connection_refused"],
        "incident_type": "database_dependency_unavailable",
        "severity": "high",
    },
    "app_db_error_spike": {
        "event_types": ["app_db_connection_error"],
        "alert_types": ["app_db_connection_error_threshold"],
        "incident_type": "app_database_error_spike",
        "severity": "high",
    },
    "cross_component_incident": {
        "event_types": [
            "mysql_connection_refused",
            "app_db_connection_error",
            "login_failed",
        ],
        "alert_types": [
            "mysql_connection_refused",
            "app_db_connection_error_threshold",
            "ssh_login_failed_threshold",
        ],
        "incident_type": "database_dependency_unavailable",
        "severity": "high",
    },
    "realistic_mix": {
        "event_types": [
            "linux_systemd_event",
            "mysql_connection_refused",
            "app_db_connection_error",
            "login_failed",
        ],
        "alert_types": [
            "mysql_connection_refused",
            "app_db_connection_error_threshold",
            "ssh_login_failed_threshold",
        ],
        "incident_type": "mixed_operational_incidents",
        "severity": "mixed",
    },
}


def _payload(
    *,
    source_type: str,
    source_name: str,
    log: str,
    host: str | None = None,
    service: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source_type": source_type,
        "source_name": source_name,
        "logs": [log],
    }
    if host is not None:
        payload["host"] = host
    if service is not None:
        payload["service"] = service
    return payload


def _linux_failed_password(index: int, *, host: str = "app-prod-01") -> dict[str, Any]:
    port = 52000 + index
    return _payload(
        source_type="linux",
        source_name="auth.log",
        host=host,
        log=(
            f"Jun  3 14:{index % 60:02d}:12 {host} sshd[{2300 + index}]: "
            f"Failed password for root from 8.8.8.8 port {port} ssh2"
        ),
    )


def _mysql_refused(index: int, *, host: str = "db-prod-01") -> dict[str, Any]:
    return _payload(
        source_type="mysql",
        source_name="mysql-error.log",
        host=host,
        log=(
            f"2026-06-03T14:{index % 60:02d}:02.123456Z 0 [ERROR] "
            "Can't connect to local MySQL server through socket"
        ),
    )


def _app_db_error(index: int, *, host: str = "app-prod-01") -> dict[str, Any]:
    return _payload(
        source_type="app_service",
        source_name="login-service.log",
        host=host,
        service="login-service",
        log=(
            f"2026-06-03T14:{index % 60:02d}:22Z login-service ERROR "
            "database connection refused"
        ),
    )


def _normal_log(index: int, *, host: str = "app-prod-01") -> dict[str, Any]:
    hosts = ["app-prod-01", "app-prod-02", "db-prod-01", "worker-prod-01"]
    host = hosts[index % len(hosts)]
    messages = [
        f"Started routine maintenance job {index}.",
        f"Accepted publickey for deploy from 10.0.0.{index % 50 + 1} port {41000 + index} ssh2",
        f"systemd[1]: Started session {index} of user app.",
        f"cron[{3000 + index}]: (root) CMD (/usr/local/bin/healthcheck)",
    ]
    return _payload(
        source_type="linux",
        source_name="syslog",
        host=host,
        log=(
            f"Jun  3 14:{index % 60:02d}:01 {host} systemd[1]: "
            f"{messages[index % len(messages)]}"
        ),
    )


def _cycle_generators(generators: list[Callable[[int], dict[str, Any]]], count: int) -> list[dict[str, Any]]:
    return [generators[index % len(generators)](index) for index in range(count)]


def _build_realistic_mix(count: int) -> list[dict[str, Any]]:
    payloads = [_normal_log(index) for index in range(count)]
    injections: list[Callable[[int], dict[str, Any]]] = []

    mysql_count = max(3, count // 20)
    app_error_count = max(3, count // 20)
    ssh_count = max(4, count // 25)
    injections.extend(_mysql_refused(10_000 + index) for index in range(mysql_count))
    injections.extend(_app_db_error(20_000 + index) for index in range(app_error_count))
    injections.extend(_linux_failed_password(30_000 + index) for index in range(ssh_count))

    start = max(0, count - len(injections))
    for offset, payload in enumerate(injections):
        payloads[start + offset] = payload

    return payloads


def build_scenario_payloads(scenario: str, *, count: int) -> list[dict[str, Any]]:
    if count < 1:
        raise ValueError("count must be >= 1")

    if scenario == "normal_mixed":
        return [_normal_log(index) for index in range(count)]
    if scenario == "ssh_bruteforce":
        return [_linux_failed_password(index) for index in range(count)]
    if scenario == "mysql_down":
        return [_mysql_refused(index) for index in range(count)]
    if scenario == "app_db_error_spike":
        return [_app_db_error(index) for index in range(count)]
    if scenario == "cross_component_incident":
        return _cycle_generators(
            [_mysql_refused, _app_db_error, _linux_failed_password, _normal_log],
            count,
        )
    if scenario == "realistic_mix":
        return _build_realistic_mix(count)

    raise ValueError(f"Unsupported scenario: {scenario}")


def build_dataset_metadata(
    scenario: str,
    payloads: list[dict[str, Any]],
) -> dict[str, Any]:
    expected = SCENARIO_EXPECTATIONS[scenario]
    return {
        "schema_version": 1,
        "scenario": scenario,
        "raw_log_count": sum(len(payload.get("logs") or []) for payload in payloads),
        "payload_count": len(payloads),
        "expected": expected,
    }


def write_jsonl(path: Path, payloads: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for payload in payloads:
            file.write(json.dumps(payload, ensure_ascii=False))
            file.write("\n")


def write_metadata(path: Path, metadata: dict[str, Any]) -> None:
    metadata_path = path.with_suffix(path.suffix + ".metadata.json")
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def generate_dataset(
    *,
    scenario: str,
    count: int,
    output: Path,
) -> dict[str, Any]:
    payloads = build_scenario_payloads(scenario, count=count)
    metadata = build_dataset_metadata(scenario, payloads)
    write_jsonl(output, payloads)
    write_metadata(output, metadata)
    return {
        "status": "generated",
        "dataset": str(output),
        "metadata": str(output.with_suffix(output.suffix + ".metadata.json")),
        **metadata,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate simulated AIOps JSONL datasets.")
    parser.add_argument(
        "scenario",
        choices=sorted(SCENARIO_EXPECTATIONS),
        help="Scenario to generate.",
    )
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSONL path. Defaults to datasets/simulated/generated_<scenario>.jsonl.",
    )
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    output = args.output or Path(f"datasets/simulated/generated_{args.scenario}.jsonl")
    report = generate_dataset(
        scenario=args.scenario,
        count=args.count,
        output=output,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()

