from pathlib import Path
from scripts.dataset_io import load_jsonl

from scripts.bootstrap_database import build_bootstrap_report
from scripts.seed_context_data import build_seed_records
from scripts.seed_knowledge_data import build_seed_records as build_knowledge_seed_records


def test_load_jsonl_reads_simulated_dataset():
    dataset = Path("datasets/simulated/ssh_bruteforce.jsonl")

    payloads = load_jsonl(dataset)

    assert len(payloads) == 3
    assert payloads[0]["source_type"] == "linux"
    assert "Failed password" in payloads[0]["logs"][0]


def test_build_seed_records_creates_context_records():
    dependency, deployment = build_seed_records()

    assert dependency.service == "login-service"
    assert dependency.dependency_service == "mysql"
    assert dependency.extra["critical"] is True
    assert deployment.service == "login-service"
    assert deployment.environment == "prod"
    assert len(deployment.deployment_id) <= 36


def test_build_knowledge_seed_records_creates_runbook_and_history():
    runbook, historical_incident = build_knowledge_seed_records()

    assert runbook.runbook_id == "runbook-mysql-unavailable"
    assert runbook.component == "mysql"
    assert "database" in runbook.tags
    assert historical_incident.historical_incident_id == "hist-login-mysql-outage"
    assert historical_incident.root_cause == "mysql_or_database_dependency_unavailable"


def test_build_bootstrap_report_summarizes_database_seed_results():
    report = build_bootstrap_report(
        init_status="ok",
        knowledge={"runbook_id": "runbook-mysql-unavailable"},
        context={"dependency_id": "dep-login-service-mysql"},
    )

    assert report == {
        "status": "ok",
        "database_initialized": True,
        "knowledge": {"runbook_id": "runbook-mysql-unavailable"},
        "context": {"dependency_id": "dep-login-service-mysql"},
    }


