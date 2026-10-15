from pathlib import Path

from crossst.domain.schemas.ingest import IngestLogsRequest
from scripts.benchmark_dataset import build_benchmark_report
from scripts.check_pipeline_counts import DATABASE_COUNT_MODELS
from scripts.generate_simulated_dataset import (
    build_dataset_metadata,
    build_scenario_payloads,
)
from scripts.e2e_smoke import build_e2e_smoke_report
from scripts.evaluate_simulated_dataset import (
    build_dataset_expectations,
    build_expectations_from_metadata,
    evaluate_payloads,
)
from scripts.dataset_io import load_jsonl


def test_build_e2e_smoke_report_marks_pipeline_ready_when_counts_increase():
    report = build_e2e_smoke_report(
        dataset="datasets/simulated/mixed_incident.jsonl",
        accepted_logs=5,
        before={
            "kafka_offsets": {
                "raw_logs": 10,
                "normalized_events": 20,
                "alerts": 3,
                "incidents": 1,
            },
            "redis": {
                "count": 2,
                "counters": {
                    "counter:login_failed:app-prod-01:8.8.8.8": "2",
                    "counter:mysql_connection_refused:db-prod-01": "1",
                },
            },
            "postgres": {
                "events": 20,
                "alerts": 3,
                "incidents": 1,
                "diagnoses": 0,
            },
        },
        after={
            "kafka_offsets": {
                "raw_logs": 15,
                "normalized_events": 25,
                "alerts": 5,
                "incidents": 2,
            },
            "redis": {
                "count": 3,
                "counters": {
                    "counter:login_failed:app-prod-01:8.8.8.8": "5",
                    "counter:mysql_connection_refused:db-prod-01": "2",
                    "counter:app_db_connection_error:login-service:app-prod-01": "2",
                },
            },
            "postgres": {
                "events": 25,
                "alerts": 5,
                "incidents": 2,
                "diagnoses": 1,
            },
        },
    )

    assert report["status"] == "ok"
    assert report["accepted_logs"] == 5
    assert report["deltas"]["kafka_offsets"]["raw_logs"] == 5
    assert report["deltas"]["postgres"]["events"] == 5
    assert report["deltas"]["redis"]["count"] == 1
    assert report["deltas"]["redis"]["counter_deltas"][
        "counter:login_failed:app-prod-01:8.8.8.8"
    ] == 3
    assert report["checks"]["raw_logs_accepted"] is True
    assert report["checks"]["normalized_events_progressed"] is True
    assert report["checks"]["alerts_progressed"] is True
    assert report["checks"]["incidents_progressed"] is True
    assert report["checks"]["redis_counters_progressed"] is True


def test_build_e2e_smoke_report_marks_degraded_when_alerts_do_not_progress():
    report = build_e2e_smoke_report(
        dataset="datasets/simulated/mixed_incident.jsonl",
        accepted_logs=5,
        before={
            "kafka_offsets": {"raw_logs": 10, "normalized_events": 20, "alerts": 3},
            "postgres": {"events": 20, "alerts": 3, "incidents": 1},
        },
        after={
            "kafka_offsets": {"raw_logs": 15, "normalized_events": 25, "alerts": 3},
            "postgres": {"events": 25, "alerts": 3, "incidents": 1},
        },
    )

    assert report["status"] == "degraded"
    assert report["checks"]["alerts_progressed"] is False


def test_pipeline_count_models_cover_major_mvp_tables():
    assert set(DATABASE_COUNT_MODELS) == {
        "events",
        "alerts",
        "incidents",
        "diagnoses",
        "tool_calls",
        "conversation_sessions",
        "conversation_messages",
        "conversation_summaries",
        "runbooks",
        "historical_incidents",
        "service_dependencies",
        "recent_deployments",
    }


def test_evaluate_simulated_mixed_dataset_reports_expected_signals():
    payloads = load_jsonl(Path("datasets/simulated/mixed_incident.jsonl"))

    report = evaluate_payloads(
        payloads,
        expectations=build_dataset_expectations("mixed_incident.jsonl"),
    )

    assert report["status"] == "ok"
    assert report["raw_log_count"] == 6
    assert report["event_counts"]["mysql_connection_refused"] == 1
    assert report["event_counts"]["app_db_connection_error"] == 2
    assert report["event_counts"]["login_failed"] == 3
    assert "mysql_connection_refused" in report["alert_counts"]
    assert "app_db_connection_error_threshold" in report["alert_counts"]
    assert "ssh_login_failed_threshold" in report["alert_counts"]
    assert report["missing_expected_event_types"] == []
    assert report["missing_expected_alert_types"] == []


def test_generated_mysql_down_dataset_has_metadata_expectations():
    payloads = build_scenario_payloads("mysql_down", count=12)
    metadata = build_dataset_metadata("mysql_down", payloads)

    expectations = build_expectations_from_metadata(metadata)
    report = evaluate_payloads(payloads, expectations=expectations)

    assert metadata["scenario"] == "mysql_down"
    assert metadata["raw_log_count"] == 12
    assert metadata["expected"]["event_types"] == ["mysql_connection_refused"]
    assert metadata["expected"]["alert_types"] == ["mysql_connection_refused"]
    assert metadata["expected"]["incident_type"] == "database_dependency_unavailable"
    assert report["status"] == "ok"
    assert report["raw_log_count"] == 12


def test_generated_cross_component_payloads_match_ingest_schema():
    payloads = build_scenario_payloads("cross_component_incident", count=16)

    for payload in payloads:
        IngestLogsRequest.model_validate(payload)


def test_generated_ssh_bruteforce_dataset_reaches_threshold():
    payloads = build_scenario_payloads("ssh_bruteforce", count=5)
    metadata = build_dataset_metadata("ssh_bruteforce", payloads)

    report = evaluate_payloads(
        payloads,
        expectations=build_expectations_from_metadata(metadata),
    )

    assert report["status"] == "ok"
    assert report["alert_counts"]["ssh_login_failed_threshold"] >= 1


def test_generated_realistic_mix_contains_noise_and_incidents():
    payloads = build_scenario_payloads("realistic_mix", count=200)
    metadata = build_dataset_metadata("realistic_mix", payloads)

    report = evaluate_payloads(
        payloads,
        expectations=build_expectations_from_metadata(metadata),
    )

    assert metadata["scenario"] == "realistic_mix"
    assert metadata["expected"]["severity"] == "mixed"
    assert metadata["expected"]["incident_type"] == "mixed_operational_incidents"
    assert report["status"] == "ok"
    assert report["raw_log_count"] == 200
    assert report["event_counts"]["linux_systemd_event"] > 100
    assert report["alert_counts"]["mysql_connection_refused"] >= 1
    assert report["alert_counts"]["app_db_connection_error_threshold"] >= 1
    assert report["alert_counts"]["ssh_login_failed_threshold"] >= 1


def test_build_benchmark_report_calculates_detection_metrics():
    evaluation = {
        "status": "ok",
        "raw_log_count": 200,
        "event_counts": {
            "linux_systemd_event": 160,
            "mysql_connection_refused": 10,
            "app_db_connection_error": 10,
            "login_failed": 20,
        },
        "alert_counts": {
            "mysql_connection_refused": 10,
            "app_db_connection_error_threshold": 9,
            "ssh_login_failed_threshold": 18,
        },
        "expected_event_types": [
            "app_db_connection_error",
            "login_failed",
            "linux_systemd_event",
            "mysql_connection_refused",
        ],
        "expected_alert_types": [
            "app_db_connection_error_threshold",
            "mysql_connection_refused",
            "ssh_login_failed_threshold",
        ],
        "missing_expected_event_types": [],
        "missing_expected_alert_types": [],
    }

    report = build_benchmark_report(
        dataset="dataset.jsonl",
        evaluation=evaluation,
    )

    assert report["status"] == "ok"
    assert report["parser"]["event_type_recall"] == 1.0
    assert report["detection"]["alert_type_recall"] == 1.0
    assert report["detection"]["alert_count"] == 37
    assert report["noise"]["unclassified_ratio"] == 0.0

