import argparse
import json
from pathlib import Path
from typing import Any

from scripts.evaluate_simulated_dataset import evaluate_dataset


def _recall(expected: list[str], missing: list[str]) -> float:
    if not expected:
        return 1.0
    return round((len(expected) - len(missing)) / len(expected), 4)


def build_benchmark_report(
    *,
    dataset: str,
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    raw_log_count = int(evaluation.get("raw_log_count") or 0)
    event_counts = evaluation.get("event_counts") or {}
    alert_counts = evaluation.get("alert_counts") or {}
    expected_event_types = evaluation.get("expected_event_types") or []
    expected_alert_types = evaluation.get("expected_alert_types") or []
    missing_event_types = evaluation.get("missing_expected_event_types") or []
    missing_alert_types = evaluation.get("missing_expected_alert_types") or []
    unclassified_count = int(event_counts.get("unclassified_log") or 0)
    alert_count = sum(int(value) for value in alert_counts.values())

    return {
        "status": evaluation.get("status", "unknown"),
        "dataset": dataset,
        "raw_log_count": raw_log_count,
        "parser": {
            "event_type_recall": _recall(expected_event_types, missing_event_types),
            "expected_event_types": expected_event_types,
            "missing_event_types": missing_event_types,
            "event_counts": event_counts,
        },
        "detection": {
            "alert_type_recall": _recall(expected_alert_types, missing_alert_types),
            "expected_alert_types": expected_alert_types,
            "missing_alert_types": missing_alert_types,
            "alert_counts": alert_counts,
            "alert_count": alert_count,
        },
        "noise": {
            "unclassified_count": unclassified_count,
            "unclassified_ratio": round(unclassified_count / raw_log_count, 4)
            if raw_log_count
            else 0.0,
        },
        "metadata": evaluation.get("metadata"),
    }


def benchmark_dataset(path: Path) -> dict[str, Any]:
    evaluation = evaluate_dataset(path)
    return build_benchmark_report(
        dataset=str(path),
        evaluation=evaluation,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark parser and detection metrics for a simulated dataset."
    )
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    report = benchmark_dataset(args.dataset)
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
    if report["status"] != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
