import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any

from scripts.check_pipeline_counts import collect_counts
from scripts.dataset_io import send_dataset


def _nested_delta(
    after: dict[str, Any],
    before: dict[str, Any],
    section: str,
    key: str,
) -> int:
    after_value = (after.get(section) or {}).get(key)
    before_value = (before.get(section) or {}).get(key)
    if after_value is None or before_value is None:
        return 0
    return int(after_value) - int(before_value)


def _int_value(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _build_redis_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_redis = before.get("redis") or {}
    after_redis = after.get("redis") or {}
    before_counters = before_redis.get("counters") or {}
    after_counters = after_redis.get("counters") or {}
    keys = sorted(set(before_counters) | set(after_counters))
    counter_deltas = {
        key: _int_value(after_counters.get(key)) - _int_value(before_counters.get(key))
        for key in keys
    }
    return {
        "count": _int_value(after_redis.get("count")) - _int_value(before_redis.get("count")),
        "counter_deltas": counter_deltas,
        "progressed": any(delta > 0 for delta in counter_deltas.values()),
    }


def build_e2e_smoke_report(
    *,
    dataset: str,
    accepted_logs: int,
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    kafka_keys = sorted(
        set((before.get("kafka_offsets") or {})) | set((after.get("kafka_offsets") or {}))
    )
    postgres_keys = sorted(
        set((before.get("postgres") or {})) | set((after.get("postgres") or {}))
    )
    deltas = {
        "kafka_offsets": {
            key: _nested_delta(after, before, "kafka_offsets", key)
            for key in kafka_keys
        },
        "postgres": {
            key: _nested_delta(after, before, "postgres", key)
            for key in postgres_keys
        },
    }
    deltas["redis"] = _build_redis_delta(before, after)
    checks = {
        "raw_logs_accepted": accepted_logs > 0,
        "raw_logs_progressed": deltas["kafka_offsets"].get("raw_logs", 0) >= accepted_logs,
        "redis_counters_progressed": deltas["redis"]["progressed"],
        "normalized_events_progressed": (
            deltas["kafka_offsets"].get("normalized_events", 0) > 0
            or deltas["postgres"].get("events", 0) > 0
        ),
        "alerts_progressed": (
            deltas["kafka_offsets"].get("alerts", 0) > 0
            or deltas["postgres"].get("alerts", 0) > 0
        ),
        "incidents_progressed": (
            deltas["kafka_offsets"].get("incidents", 0) > 0
            or deltas["postgres"].get("incidents", 0) > 0
        ),
    }
    return {
        "status": "ok" if all(checks.values()) else "degraded",
        "dataset": dataset,
        "accepted_logs": accepted_logs,
        "before": before,
        "after": after,
        "deltas": deltas,
        "checks": checks,
        "next_actions": [
            "If raw_logs did not progress, check log-ingest-service and Kafka producer.",
            "If normalized_events did not progress, start parser_worker and event_sink_worker.",
            "If alerts did not progress, start detection_worker and check Redis counters.",
            "If incidents did not progress, start correlation_worker.",
            "If diagnoses did not progress, start diagnosis_worker or trigger /incidents/{id}/diagnose.",
        ],
    }


async def run_e2e_smoke(
    *,
    dataset_path: Path,
    endpoint: str,
    delay_seconds: float,
    timeout: float,
    settle_seconds: float,
) -> dict[str, Any]:
    before = await collect_counts()
    responses = send_dataset(
        dataset_path=dataset_path,
        endpoint=endpoint,
        delay_seconds=delay_seconds,
        timeout=timeout,
    )
    if settle_seconds > 0:
        time.sleep(settle_seconds)
    after = await collect_counts()
    accepted_logs = sum(response.get("accepted", 0) for response in responses)
    return build_e2e_smoke_report(
        dataset=str(dataset_path),
        accepted_logs=accepted_logs,
        before=before,
        after=after,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an end-to-end MVP smoke check.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("datasets/simulated/mixed_incident.jsonl"),
        help="JSONL dataset to send through log-ingest-service /ingest/logs.",
    )
    parser.add_argument(
        "--endpoint",
        default="http://localhost:8100/ingest/logs",
        help="Standalone log ingest HTTP endpoint URL.",
    )
    parser.add_argument("--delay-seconds", type=float, default=0.0)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--settle-seconds",
        type=float,
        default=5.0,
        help="Seconds to wait for workers to consume messages.",
    )
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    report = asyncio.run(
        run_e2e_smoke(
            dataset_path=args.dataset,
            endpoint=args.endpoint,
            delay_seconds=args.delay_seconds,
            timeout=args.timeout,
            settle_seconds=args.settle_seconds,
        )
    )
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
    if report["status"] != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

