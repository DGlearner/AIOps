import argparse
import json
from time import perf_counter
from typing import Any

from crossst.application.agents.diagnosis_graph import build_initial_state, make_incident_context
from crossst.core.config import Settings, get_settings
from crossst.services.llm.diagnosis import (
    build_configured_langchain_diagnosis_provider,
)


def build_safe_llm_diagnosis_config_payload(settings: Settings) -> dict[str, Any]:
    return {
        "llm_enabled": settings.llm_enabled,
        "diagnosis_llm_enabled": settings.diagnosis_llm_enabled,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "llm_api_key": "set" if settings.llm_api_key else "missing",
        "llm_base_url": "set" if settings.llm_base_url else "missing",
        "llm_temperature": settings.llm_temperature,
        "llm_max_tokens": settings.llm_max_tokens,
        "llm_timeout_seconds": settings.llm_timeout_seconds,
    }


def validate_llm_diagnosis_smoke_settings(settings: Settings) -> list[str]:
    errors: list[str] = []
    if not settings.llm_enabled:
        errors.append("LLM_ENABLED must be true")
    if not settings.diagnosis_llm_enabled:
        errors.append("DIAGNOSIS_LLM_ENABLED must be true")
    if not settings.llm_provider:
        errors.append("LLM_PROVIDER must be set")
    if not settings.llm_model:
        errors.append("LLM_MODEL must be set")
    if not settings.llm_api_key:
        errors.append("LLM_API_KEY is not set")
    return errors


def build_sample_diagnosis_state() -> dict[str, Any]:
    incident = make_incident_context(
        incident_id="smoke-incident-l4-diagnosis",
        summary=(
            "login-service 在 5 分钟内出现大量登录失败，同时应用日志出现 DB "
            "connection error，MySQL error log 出现 connection refused。"
        ),
        event_types=[
            "login_failed",
            "app_db_connection_error",
            "mysql_connection_refused",
        ],
        affected_hosts=["app-prod-01", "db-prod-01"],
        affected_services=["login-service"],
        aggregate_key="service:login-service",
    )
    state = build_initial_state(incident=incident)
    state["hypotheses"] = [
        "credential_attack_or_bruteforce",
        "backend_dependency_failure_affecting_login",
        "mysql_unavailable",
    ]
    state["current_hypothesis"] = "mysql_unavailable"
    state["evidence_chain"] = [
        "backend_dependency_failure_affecting_login: query_events returned 12 related record(s).",
        "mysql_unavailable: query_events returned 7 related record(s).",
    ]
    state["ruled_out_hypotheses"] = []
    state["tool_results"] = [
        {
            "tool": "query_events",
            "count": 12,
            "events": [
                {
                    "event_type": "app_db_connection_error",
                    "source_type": "app",
                    "service": "login-service",
                    "host": "app-prod-01",
                    "message": "DB connection timeout while authenticating user",
                }
            ],
        },
        {
            "tool": "query_events",
            "count": 7,
            "events": [
                {
                    "event_type": "mysql_connection_refused",
                    "source_type": "mysql",
                    "host": "db-prod-01",
                    "message": "Can't connect to local MySQL server through socket",
                }
            ],
        },
    ]
    state["tool_call_summary"] = [
        {
            "tool": "query_events",
            "reason": "Check login-service DB connection errors.",
            "kwargs": {
                "service": "login-service",
                "event_type": "app_db_connection_error",
                "limit": 20,
            },
            "result_count": 12,
        },
        {
            "tool": "query_events",
            "reason": "Check MySQL availability errors near the incident window.",
            "kwargs": {
                "source_type": "mysql",
                "event_type": "mysql_connection_refused",
                "limit": 20,
            },
            "result_count": 7,
        },
    ]
    state["pending_tool_calls"] = [
        {
            "tool_call_id": "smoke-tool-call-app-db-errors",
            "tool_name": "query_events",
        },
        {
            "tool_call_id": "smoke-tool-call-mysql-errors",
            "tool_name": "query_events",
        },
    ]
    return state


def run_llm_diagnosis_smoke_test(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    config = build_safe_llm_diagnosis_config_payload(settings)
    errors = validate_llm_diagnosis_smoke_settings(settings)
    if errors:
        return {
            "status": "config_error",
            "config": config,
            "errors": errors,
        }

    provider, provider_error = build_configured_langchain_diagnosis_provider(settings)
    if provider is None:
        return {
            "status": "provider_error",
            "config": config,
            "error": provider_error,
        }

    state = build_sample_diagnosis_state()
    started_at = perf_counter()
    output = provider.analyze_state(state)
    duration_ms = int((perf_counter() - started_at) * 1000)

    return {
        "status": "ok",
        "config": config,
        "duration_ms": duration_ms,
        "diagnosis": output.model_dump(mode="json"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Call the configured LangChain model once for L4 diagnosis."
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )
    args = parser.parse_args()

    result = run_llm_diagnosis_smoke_test()
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2 if args.pretty else None,
        )
    )
    if result["status"] != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

