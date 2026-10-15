import pytest

from scripts.llm_smoke_test import (
    build_sample_inputs,
    build_safe_llm_config_payload,
    validate_llm_smoke_settings,
)
from scripts.llm_diagnosis_smoke_test import (
    build_safe_llm_diagnosis_config_payload,
    build_sample_diagnosis_state,
    validate_llm_diagnosis_smoke_settings,
)


class FakeSettings:
    llm_enabled = True
    diagnosis_llm_enabled = True
    llm_provider = "openai"
    llm_model = "gpt-4o-mini"
    llm_api_key = "secret-key"
    llm_base_url = "https://example.test/v1"
    llm_temperature = 0.1
    llm_max_tokens = 1200
    llm_timeout_seconds = 30


def test_build_safe_llm_config_payload_does_not_expose_secret():
    payload = build_safe_llm_config_payload(FakeSettings())

    assert payload["llm_enabled"] is True
    assert payload["llm_provider"] == "openai"
    assert payload["llm_model"] == "gpt-4o-mini"
    assert payload["llm_api_key"] == "set"
    assert "secret-key" not in str(payload)


def test_validate_llm_smoke_settings_reports_missing_required_config():
    class MissingSettings(FakeSettings):
        llm_enabled = False
        llm_model = ""
        llm_api_key = None

    errors = validate_llm_smoke_settings(MissingSettings())

    assert "LLM_ENABLED must be true" in errors
    assert "LLM_MODEL must be set" in errors
    assert "LLM_API_KEY is not set" in errors


def test_build_sample_inputs_contains_evidence_memory_and_rag():
    inputs = build_sample_inputs()

    assert inputs["question"]
    assert inputs["diagnosis"]["root_cause"]
    assert inputs["rag_context"]["references"]
    assert inputs["memory_context"]["recent_messages"]


def test_build_safe_llm_diagnosis_config_payload_does_not_expose_secret():
    payload = build_safe_llm_diagnosis_config_payload(FakeSettings())

    assert payload["llm_enabled"] is True
    assert payload["diagnosis_llm_enabled"] is True
    assert payload["llm_provider"] == "openai"
    assert payload["llm_model"] == "gpt-4o-mini"
    assert payload["llm_api_key"] == "set"
    assert "secret-key" not in str(payload)


def test_validate_llm_diagnosis_smoke_settings_reports_missing_required_config():
    class MissingSettings(FakeSettings):
        llm_enabled = False
        diagnosis_llm_enabled = False
        llm_model = ""
        llm_api_key = None

    errors = validate_llm_diagnosis_smoke_settings(MissingSettings())

    assert "LLM_ENABLED must be true" in errors
    assert "DIAGNOSIS_LLM_ENABLED must be true" in errors
    assert "LLM_MODEL must be set" in errors
    assert "LLM_API_KEY is not set" in errors


def test_build_sample_diagnosis_state_contains_cross_component_evidence():
    state = build_sample_diagnosis_state()

    assert state["incident_id"] == "smoke-incident-l4-diagnosis"
    assert "login_failed" in state["incident"]["event_types"]
    assert "mysql_connection_refused" in state["incident"]["event_types"]
    assert state["current_hypothesis"] == "mysql_unavailable"
    assert len(state["tool_results"]) == 2
    assert state["pending_tool_calls"]

