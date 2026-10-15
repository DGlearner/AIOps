import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from crossst.domain.schemas.ingest import IngestLogsRequest, build_raw_log_messages
from crossst.parsers.parsers_route import parse_raw_log
from crossst.services.detection.rules import (
    DEFAULT_WINDOW_SECONDS,
    build_detection_context,
    evaluate_event,
)
from scripts.dataset_io import load_jsonl


DATASET_EXPECTATIONS: dict[str, dict[str, set[str]]] = {
    "ssh_bruteforce.jsonl": {
        "event_types": {"login_failed"},
        "alert_types": {"ssh_login_failed_threshold"},
    },
    "mysql_down.jsonl": {
        "event_types": {"mysql_connection_refused"},
        "alert_types": {"mysql_connection_refused"},
    },
    "app_db_error_spike.jsonl": {
        "event_types": {"app_db_connection_error"},
        "alert_types": {"app_db_connection_error_threshold"},
    },
    "mixed_incident.jsonl": {
        "event_types": {
            "mysql_connection_refused",
            "app_db_connection_error",
            "login_failed",
        },
        "alert_types": {
            "mysql_connection_refused",
            "app_db_connection_error_threshold",
            "ssh_login_failed_threshold",
        },
    },
    "normal_mixed.jsonl": {
        "event_types": {"unclassified_log"},
        "alert_types": set(),
    },
}


def build_dataset_expectations(dataset_name: str) -> dict[str, set[str]]:
    return DATASET_EXPECTATIONS.get(
        dataset_name,
        {
            "event_types": set(),
            "alert_types": set(),
        },
    )


def build_expectations_from_metadata(metadata: dict[str, Any]) -> dict[str, set[str]]:
    expected = metadata.get("expected") or {}
    return {
        "event_types": set(expected.get("event_types") or []),
        "alert_types": set(expected.get("alert_types") or []),
    }


def load_dataset_metadata(path: Path) -> dict[str, Any] | None:
    metadata_path = path.with_suffix(path.suffix + ".metadata.json")
    if not metadata_path.exists():
        return None
    with metadata_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def evaluate_payloads(
    payloads: list[dict[str, Any]],
    *,
    expectations: dict[str, set[str]] | None = None,
) -> dict[str, Any]:
    expectations = expectations or {"event_types": set(), "alert_types": set()}
    events = []
    alerts = []
    counters: dict[str, int] = {}

    for payload in payloads:
        request = IngestLogsRequest.model_validate(payload)
        for raw_log in build_raw_log_messages(request):
            event = parse_raw_log(raw_log)
            events.append(event)
            context = build_detection_context(event)
            if context is None:
                continue
            count = counters.get(context.counter_key, 0) + 1
            counters[context.counter_key] = count
            alert = evaluate_event(
                event,
                count=count,
                window_seconds=context.window_seconds or DEFAULT_WINDOW_SECONDS,
            )
            if alert is not None:
                alerts.append(alert)

    event_counts = Counter(event.event_type for event in events)
    alert_counts = Counter(alert.alert_type for alert in alerts)
    expected_events = expectations.get("event_types", set())
    expected_alerts = expectations.get("alert_types", set())
    missing_event_types = sorted(expected_events - set(event_counts))
    missing_alert_types = sorted(expected_alerts - set(alert_counts))

    return {
        "status": "ok" if not missing_event_types and not missing_alert_types else "degraded",
        "raw_log_count": len(events),
        "event_counts": dict(event_counts),
        "alert_counts": dict(alert_counts),
        "counter_count": len(counters),
        "expected_event_types": sorted(expected_events),
        "expected_alert_types": sorted(expected_alerts),
        "missing_expected_event_types": missing_event_types,
        "missing_expected_alert_types": missing_alert_types,
    }


def evaluate_dataset(path: Path) -> dict[str, Any]:
    payloads = load_jsonl(path)
    metadata = load_dataset_metadata(path)
    expectations = (
        build_expectations_from_metadata(metadata)
        if metadata is not None
        else build_dataset_expectations(path.name)
    )
    report = evaluate_payloads(
        payloads,
        expectations=expectations,
    )
    report["dataset"] = str(path)
    if metadata is not None:
        report["metadata"] = metadata
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate parser and detection coverage for simulated JSONL logs."
    )
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    report = evaluate_dataset(args.dataset)
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
    if report["status"] != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

